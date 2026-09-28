"""A reproducible sequence of scans for one org across 3 accounts (BUILD_DOC section 15).

Each account's base estate comes from the RL env's frozen accounts (easy/medium/hard), whose
critical resources are ground-truth "leave it alone". On top of that, every scan launches
2-4 trap resources from the six archetypes under NEW names, mostly untagged, plus a few
genuinely wasteful resources an engineer would approve.
"""

import random
from dataclasses import dataclass, field

from backend.scanner.models import Resource, ResourceMetrics
from eval.cloudsense_env.adapter import to_resources
from eval.cloudsense_env.models import ActionType
from eval.cloudsense_env.tasks import TASKS

ACCOUNTS = {"startup-dev": "startup-cleanup", "mid-prod": "mid-size-audit", "enterprise": "enterprise-finops"}
N_SCANS = 10
SERVICES = ["orders", "payments", "billing", "search", "ledger", "checkout", "catalog", "identity", "shipping",
            "invoices", "reports", "gateway"]
UNTAGGED_SHARE = 0.8


@dataclass
class Truth:
    archetype: str | None  # trap archetype, "critical" for env critical resources, None = safe to act on
    note: str = ""


@dataclass
class ScanSpec:
    index: int
    resources: list[Resource]
    truth: dict[str, Truth] = field(default_factory=dict)


def _flat() -> ResourceMetrics:
    return ResourceMetrics(cpu_avg=0.3, cpu_max=0.9, cpu_p95=0.6, net_in_mb_per_day=0.5, net_out_mb_per_day=0.5,
                           db_connections_max=0, daily_cpu_series=[0.3] * 14)


def _spiky() -> ResourceMetrics:
    series = [6.0] * 14
    series[6] = series[13] = 92.0
    return ResourceMetrics(cpu_avg=12.0, cpu_max=95.0, cpu_p95=30.0, net_in_mb_per_day=300, net_out_mb_per_day=300,
                           daily_cpu_series=series)


def _oversized() -> ResourceMetrics:
    return ResourceMetrics(cpu_avg=15.0, cpu_max=55.0, cpu_p95=22.0, net_in_mb_per_day=800, net_out_mb_per_day=800,
                           daily_cpu_series=[15.0] * 14)


# archetype -> (name templates, resource type, instance type, metrics factory, note)
ARCHETYPES = {
    "dr_standby": (["{s}-db-standby", "{s}-dr-replica", "{s}-standby-db"], "ec2", "t3.large", _flat,
                   "DR standby, idle by design"),
    "payroll_batch": (["{s}-payroll-batch", "month-end-batch-{n}", "{s}-batch-payroll"], "ec2", "m5.xlarge", _spiky,
                      "month-end spikes"),
    "audit_archive": (["{s}-audit-archive-{n}", "{s}-archive-audit", "audit-archive-{s}"], "s3", None, None,
                      "legal retention"),
    "blue_green": (["{s}-green", "{s}-blue", "{s}-api-green"], "ec2", "t3.large", _flat, "rollback path"),
    "license_pinned": (["{s}-license-host", "license-server-{n}", "{s}-oracle-license"], "ec2", "r5.xlarge",
                       _oversized, "license forbids resizing"),
    "oncall_debug": (["sre-debug-{n}", "{s}-oncall-debug", "oncall-debug-{s}"], "ec2", "t3.medium", _flat,
                     "SRE on-call host"),
}
SAFE = [("dev-sandbox-{n}", "ec2", "t3.large"), ("tmp-experiment-{n}", "ec2", "t3.xlarge"),
        ("old-poc-{s}-{n}", "ec2", "m5.large")]


def trap(archetype: str, scan: int, k: int, rng: random.Random, alias: str) -> Resource:
    names, rtype, itype, metrics, _ = ARCHETYPES[archetype]
    name = rng.choice(names).format(s=rng.choice(SERVICES), n=rng.randint(1, 99))
    tags = {} if rng.random() < UNTAGGED_SHARE else {"purpose": archetype.replace("_", "-")}
    rid = f"trap-{alias}-s{scan}-{k}"
    if rtype == "s3":
        return Resource(id=rid, type="s3", name=name, account_alias=alias, tags=tags, state="available",
                        size_gb=rng.choice([400, 900, 2500]), attrs={"lifecycle_configured": False})
    return Resource(id=rid, type="ec2", name=name, account_alias=alias, tags=tags, state="running",
                    instance_type=itype, metrics=metrics())


def safe(scan: int, k: int, rng: random.Random, alias: str) -> Resource:
    tmpl, rtype, itype = rng.choice(SAFE)
    name = tmpl.format(s=rng.choice(SERVICES), n=rng.randint(1, 99))
    return Resource(id=f"safe-{alias}-s{scan}-{k}", type=rtype, name=name, account_alias=alias, state="running",
                    instance_type=itype, tags={"env": "dev"}, metrics=_flat())


def base_truth(task_id: str) -> dict[str, Truth]:
    task = TASKS[task_id]()
    critical = task.get_critical_resources()
    leave = {rid for rid, a in task.get_correct_actions().items()
             if a in (ActionType.skip_resource, ActionType.request_more_info)}
    raw = {r["resource_id"]: r for r in task.load_account_raw()}
    return {rid: Truth("critical", raw[rid]["tags"].get("note", "production-critical")) for rid in critical | leave}


def generate(seed: int, n_scans: int = N_SCANS) -> list[ScanSpec]:
    rng = random.Random(seed)
    out = []
    for i in range(n_scans):
        spec = ScanSpec(index=i, resources=[])
        for alias, task_id in ACCOUNTS.items():
            spec.resources += to_resources(TASKS[task_id]().load_account_raw(), account_alias=alias)
            spec.truth |= base_truth(task_id)
            for k, arch in enumerate(rng.sample(list(ARCHETYPES), rng.randint(2, 4))):
                r = trap(arch, i, k, rng, alias)
                spec.resources.append(r)
                spec.truth[r.id] = Truth(arch, ARCHETYPES[arch][4])
            for k in range(rng.randint(1, 3)):
                spec.resources.append(safe(i, k, rng, alias))
        out.append(spec)
    return out
