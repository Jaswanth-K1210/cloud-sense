"""Deterministic waste rules R1–R8 (BUILD_DOC 6.4). No LLM, no directives: those filter later."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field

from backend.candidates.pricing import one_size_down, saving_for
from backend.graph.blast_radius import blast_radius
from backend.scanner.models import Resource

# R1 idle EC2
IDLE_CPU_AVG = 5.0
IDLE_CPU_MAX = 20.0
IDLE_NET_MB_PER_DAY = 5.0
# R2 oversized EC2
OVERSIZED_CPU_P95 = 40.0
# R3 unattached EBS
UNATTACHED_MIN_AGE = timedelta(days=7)
# R5 old snapshot
SNAPSHOT_MIN_AGE = timedelta(days=90)
# R8 S3 without lifecycle
S3_MIN_SIZE_GB = 1.0

SKIP_STATES = {"terminated", "deleting", "deleted", "shutting-down"}


class BlastRadius(BaseModel):
    count: int = 0
    names: list[str] = Field(default_factory=list)


class Candidate(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    resource_id: str
    rule_id: str
    action: str
    monthly_saving: float | None
    signals_text: str
    blast_radius: BlastRadius = Field(default_factory=BlastRadius)
    reversible: bool
    warnings: list[str] = Field(default_factory=list)


def _age(r: Resource) -> timedelta | None:
    return datetime.now(UTC) - r.created_at if r.created_at else None


def _cand(r: Resource, rule: str, action: str, signals: str, reversible: bool, *warnings: str) -> Candidate:
    return Candidate(resource_id=r.id, rule_id=rule, action=action, monthly_saving=saving_for(action, r),
                     signals_text=signals, reversible=reversible, warnings=list(warnings))


def r1_idle_ec2(r: Resource) -> Candidate | None:
    m = r.metrics
    if r.type != "ec2" or r.state != "running" or None in (m.cpu_avg, m.cpu_max):
        return None
    net = (m.net_in_mb_per_day or 0) + (m.net_out_mb_per_day or 0)
    if m.cpu_avg < IDLE_CPU_AVG and m.cpu_max < IDLE_CPU_MAX and net < IDLE_NET_MB_PER_DAY:
        return _cand(r, "R1", "stop",
                     f"14-day CPU avg {m.cpu_avg:.1f}%, max {m.cpu_max:.1f}%, network {net:.1f} MB/day", True,
                     "attached EBS volumes are snapshotted first")
    return None


def r2_oversized_ec2(r: Resource) -> Candidate | None:
    m = r.metrics
    if r.type != "ec2" or r.state != "running" or m.cpu_p95 is None or not r.instance_type:
        return None
    target = one_size_down(r.instance_type)
    if m.cpu_p95 < OVERSIZED_CPU_P95 and target:
        return _cand(r, "R2", "rightsize",
                     f"14-day CPU p95 {m.cpu_p95:.1f}% on {r.instance_type}; proposed {target}", True,
                     "memory utilization unknown (no CloudWatch agent)", "requires a stop/start")
    return None


def r3_unattached_ebs(r: Resource) -> Candidate | None:
    if r.type != "ebs" or r.state != "available":
        return None
    age = _age(r)
    if age is not None and age <= UNATTACHED_MIN_AGE:
        return None
    age_txt = f"{age.days} days old" if age else "age unknown"
    return _cand(r, "R3", "snapshot_delete", f"unattached (state=available), {r.size_gb} GB {r.volume_type}, {age_txt}",
                 True, "snapshot is taken and must complete before delete")


def r4_gp2(r: Resource) -> Candidate | None:
    if r.type == "ebs" and r.volume_type == "gp2":
        return _cand(r, "R4", "modify_gp3", f"{r.size_gb} GB gp2 volume; gp3 is cheaper at equal baseline", True,
                     "gp3 modify cooldown 6h: one modification per volume per 6 hours")
    return None


def r5_old_snapshot(r: Resource) -> Candidate | None:
    age = _age(r)
    if r.type != "snapshot" or r.attrs.get("used_by_ami") or age is None or age <= SNAPSHOT_MIN_AGE:
        return None
    return _cand(r, "R5", "delete_snapshot", f"snapshot {age.days} days old, not referenced by any AMI", False,
                 "irreversible: needs approval and a second confirmation")


def r6_idle_eip(r: Resource) -> Candidate | None:
    if r.type == "eip" and r.state == "unassociated":
        return _cand(r, "R6", "release", "Elastic IP not associated with any instance or ENI", False,
                     "the address is lost on release")
    return None


def r7_idle_rds(r: Resource) -> Candidate | None:
    if r.type != "rds" or r.state != "available" or r.metrics.db_connections_max is None:
        return None
    if r.metrics.db_connections_max == 0:
        warnings = ["RDS auto-restarts after 7 days; consider snapshot + delete for truly dead databases"]
        if r.attrs.get("replica_source"):
            warnings.append("read replicas cannot be stopped; only deleted")
        return _cand(r, "R7", "stop", "14-day max DatabaseConnections = 0", True, *warnings)
    return None


def r8_s3_lifecycle(r: Resource) -> Candidate | None:
    if r.type != "s3" or r.attrs.get("lifecycle_configured") or r.size_gb is None or r.size_gb <= S3_MIN_SIZE_GB:
        return None
    return _cand(r, "R8", "s3_lifecycle", f"{r.size_gb:.1f} GB bucket with no lifecycle configuration", True,
                 "recommend-only: add an Intelligent-Tiering rule")


RULES: list[Callable[[Resource], Candidate | None]] = [
    r1_idle_ec2, r2_oversized_ec2, r3_unattached_ebs, r4_gp2, r5_old_snapshot, r6_idle_eip, r7_idle_rds,
    r8_s3_lifecycle,
]


def generate_candidates(resources: list[Resource], graph: dict[str, list[str]]) -> list[Candidate]:
    names = {r.id: r.display_name for r in resources}
    best: dict[str, Candidate] = {}
    for r in resources:
        if r.state in SKIP_STATES:
            continue
        for rule in RULES:
            c = rule(r)
            if c is None:
                continue
            prev = best.get(r.id)
            # one action per resource: keep the highest saving
            if prev is None or (c.monthly_saving or 0) > (prev.monthly_saving or 0):
                best[r.id] = c
    for c in best.values():
        ids = blast_radius(graph, c.resource_id)
        c.blast_radius = BlastRadius(count=len(ids), names=[names.get(i, i) for i in ids])
    return list(best.values())
