from datetime import UTC, datetime, timedelta

import pytest

from backend.candidates import rules
from backend.candidates.pricing import monthly_cost, one_size_down, saving_for
from backend.graph.build import build_graph
from backend.scanner.models import Resource, ResourceMetrics

OLD = datetime.now(UTC) - timedelta(days=200)
NEW = datetime.now(UTC) - timedelta(days=1)


def ec2(**m) -> Resource:
    return Resource(id="i-1", type="ec2", name="web", state="running", instance_type="t3.large",
                    metrics=ResourceMetrics(**m))


IDLE = {"cpu_avg": 1, "cpu_max": 3, "cpu_p95": 2, "net_in_mb_per_day": 1, "net_out_mb_per_day": 1}
BUSY = {"cpu_avg": 50, "cpu_max": 95, "cpu_p95": 80, "net_in_mb_per_day": 500, "net_out_mb_per_day": 500}

CASES = [
    (rules.r1_idle_ec2, ec2(**IDLE), ec2(**{**IDLE, "cpu_max": 40})),
    (rules.r2_oversized_ec2, ec2(**{**BUSY, "cpu_p95": 20}), ec2(**BUSY)),
    (rules.r3_unattached_ebs,
     Resource(id="v", type="ebs", state="available", size_gb=100, volume_type="gp3", created_at=OLD),
     Resource(id="v", type="ebs", state="available", size_gb=100, volume_type="gp3", created_at=NEW)),
    (rules.r4_gp2, Resource(id="v", type="ebs", state="in-use", size_gb=100, volume_type="gp2"),
     Resource(id="v", type="ebs", state="in-use", size_gb=100, volume_type="gp3")),
    (rules.r5_old_snapshot, Resource(id="s", type="snapshot", size_gb=50, created_at=OLD),
     Resource(id="s", type="snapshot", size_gb=50, created_at=OLD, attrs={"used_by_ami": True})),
    (rules.r6_idle_eip, Resource(id="e", type="eip", state="unassociated"),
     Resource(id="e", type="eip", state="associated")),
    (rules.r7_idle_rds,
     Resource(id="d", type="rds", state="available", instance_type="db.t3.medium",
              metrics=ResourceMetrics(db_connections_max=0)),
     Resource(id="d", type="rds", state="available", instance_type="db.t3.medium",
              metrics=ResourceMetrics(db_connections_max=4))),
    (rules.r8_s3_lifecycle, Resource(id="b", type="s3", size_gb=500, attrs={"lifecycle_configured": False}),
     Resource(id="b", type="s3", size_gb=500, attrs={"lifecycle_configured": True})),
]


@pytest.mark.parametrize(("rule", "pos", "neg"), CASES, ids=[c[0].__name__ for c in CASES])
def test_rule_positive_and_negative(rule, pos, neg) -> None:
    c = rule(pos)
    assert c is not None
    assert c.rule_id == rule.__name__[:2].upper()
    assert c.signals_text
    assert rule(neg) is None


def test_pricing_exact() -> None:
    r = ec2(**BUSY)
    assert one_size_down("t3.large") == "t3.medium"
    assert one_size_down("t3.nano") is None
    assert saving_for("rightsize", r) == pytest.approx(60.74 - 30.37)
    assert saving_for("stop", r) == 60.74
    assert saving_for("modify_gp3", Resource(id="v", type="ebs", size_gb=100, volume_type="gp2")) == 2.0
    assert saving_for("release", Resource(id="e", type="eip")) == 3.65
    assert monthly_cost(Resource(id="x", type="ec2", instance_type="z9.huge")) is None
    assert saving_for("rightsize", Resource(id="x", type="ec2", instance_type="m5.large")) is None  # no m5.medium


def test_rds_and_gp3_warnings() -> None:
    rds = CASES[6][1]
    assert any("7 days" in w for w in rules.r7_idle_rds(rds).warnings)
    assert any("6h" in w for w in rules.r4_gp2(CASES[3][1]).warnings)


def test_do_not_terminate_still_produces_candidate() -> None:
    r = ec2(**IDLE)
    r.tags = {"do_not_terminate": "true"}
    assert rules.generate_candidates([r], {}) != []


def test_one_action_per_resource_keeps_highest_saving() -> None:
    r = ec2(**IDLE)  # both R1 (stop, 60.74) and R2 (rightsize, 30.37) match
    (c,) = rules.generate_candidates([r], {})
    assert c.rule_id == "R1"


def test_skips_terminated_and_fills_blast_radius() -> None:
    dead = Resource(id="e2", type="eip", state="deleting")
    eip = Resource(id="e", type="eip", state="unassociated")
    vol = Resource(id="v", type="ebs", state="in-use", size_gb=10, volume_type="gp2")
    inst = Resource(id="i", type="ec2", name="app", state="stopped")
    vol.attrs = {"attached_to": "i"}
    res = [dead, eip, vol, inst]
    graph = build_graph(res)
    cands = {c.resource_id: c for c in rules.generate_candidates(res, graph)}
    assert "e2" not in cands
    assert cands["v"].blast_radius.count == 0
    assert set(cands) == {"e", "v"}
