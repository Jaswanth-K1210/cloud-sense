from backend.graph.blast_radius import blast_radius
from backend.graph.build import annotate, blast_radius_names, build_graph
from backend.scanner.models import Resource, ResourceMetrics

LB = "arn:aws:elasticloadbalancing:us-east-1:1:loadbalancer/app/orders-lb/abc"
TG = "arn:aws:elasticloadbalancing:us-east-1:1:targetgroup/orders-tg/def"


def fixture() -> list[Resource]:
    tg = [{"arn": TG, "name": "orders-tg", "load_balancer_arns": [LB]}]
    return [
        Resource(id="i-api1", type="ec2", name="orders-api-1", attrs={"target_groups": tg, "asg": "orders-asg"}),
        Resource(id="i-api2", type="ec2", name="orders-api-2", attrs={"target_groups": tg}),
        Resource(id="vol-1", type="ebs", name="api1-root", attrs={"attached_to": "i-api1"}),
        Resource(id="orders-db", type="rds", name="orders-db", tags={"depends-on": ""}),
        Resource(id="orders-db-standby", type="rds", name="orders-db-standby",
                 attrs={"replica_source": "orders-db"},
                 metrics=ResourceMetrics(cpu_avg=0.1, cpu_max=0.3, db_connections_max=0,
                                         daily_cpu_series=[0.1] * 14)),
        Resource(id="i-pay", type="ec2", name="payroll-batch-worker", tags={"depends-on": "orders-db"},
                 metrics=ResourceMetrics(daily_cpu_series=[3.0] * 12 + [90.0, 85.0])),
        Resource(id="i-tf", type="ec2", name="svc", tags={"created_by": "terraform"}),
    ]


def test_standby_hints() -> None:
    res = fixture()
    annotate(res)
    sb = next(r for r in res if r.id == "orders-db-standby")
    assert "replica_of:orders-db" in sb.role_hints
    assert "standby" in sb.role_hints
    assert "flat_zero" in sb.role_hints
    assert "no_dependents" in sb.role_hints
    assert sb.depends_on_names == ["orders-db"]


def test_lb_blast_radius_includes_all_targets() -> None:
    res = fixture()
    graph = build_graph(res)
    names = {r.id: r.display_name for r in res}
    assert set(blast_radius(graph, LB)) >= {TG, "i-api1", "i-api2", "vol-1"}
    assert set(blast_radius_names(graph, LB, names)) >= {"orders-tg", "orders-api-1", "orders-api-2"}
    assert "orders-db-standby" in blast_radius(graph, "orders-db")
    assert blast_radius(graph, "orders-db-standby") == []


def test_security_group_reference_edge() -> None:
    res = [
        Resource(id="db", type="rds", name="db", attrs={"security_groups": ["sg-db"], "sg_refs": ["sg-app"]}),
        Resource(id="app", type="ec2", name="app", attrs={"security_groups": ["sg-app"]}),
    ]
    graph = build_graph(res)
    assert blast_radius(graph, "db") == ["app"]


def test_other_hints() -> None:
    res = fixture()
    annotate(res)
    by = {r.id: r for r in res}
    assert {"in_asg", "behind_lb"} <= set(by["i-api1"].role_hints)
    assert {"payroll", "batch", "periodic_spikes"} <= set(by["i-pay"].role_hints)
    assert "iac_managed" in by["i-tf"].role_hints
    assert "has_dependents:2" in by["orders-db"].role_hints  # standby + depends-on tag
    assert "asg:orders-asg" in by
