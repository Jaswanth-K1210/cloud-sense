"""Dependency graph + role hints (BUILD_DOC 6.5, 6.6).

Edges follow the spec: "A -> B" means A depends on B (EBS -> EC2, EC2 -> target group -> LB,
EC2 -> ASG, replica -> source, EIP -> instance, snapshot -> volume). graph[x] = ids that depend
on x, so blast_radius(graph, x) is everything affected when x goes away.
"""

import re
import statistics

from backend.graph.blast_radius import blast_radius
from backend.scanner.models import Resource

NAME_TOKENS = ("standby", "replica", "dr", "backup", "batch", "payroll", "archive", "audit", "bastion", "runner",
               "nat", "blue", "green", "license", "debug", "oncall")
FLAT_ZERO_CPU = 1.0  # % max CPU
SPIKE_FACTOR = 3.0  # a spike day is >= 3x the median day
MAX_SPIKE_DAYS = 4  # "a few" high days


def _node(nodes: dict[str, Resource], rid: str, rtype: str, name: str, like: Resource) -> None:
    if rid not in nodes:
        nodes[rid] = Resource(id=rid, type=rtype, name=name, account_alias=like.account_alias, region=like.region)


def build_graph(resources: list[Resource]) -> dict[str, list[str]]:
    """Add synthetic ASG / target group / LB nodes, fill depends_on/dependents/names, return the graph.

    Synthetic nodes are appended to `resources` in place so callers can render them.
    """
    nodes = {r.id: r for r in resources}
    by_name = {r.name: r.id for r in resources if r.name}
    edges: set[tuple[str, str]] = set()  # (dependent, dependency)

    for r in list(resources):
        a = r.attrs
        if r.type == "ebs" and a.get("attached_to"):
            edges.add((r.id, a["attached_to"]))
        if r.type == "snapshot" and a.get("source_volume") in nodes:
            edges.add((r.id, a["source_volume"]))
        if r.type == "eip" and a.get("associated_to") in nodes:
            edges.add((r.id, a["associated_to"]))
        if r.type == "rds" and a.get("replica_source"):
            src = a["replica_source"]
            if src in nodes:
                edges.add((r.id, src))
        if r.type == "ec2":
            if asg := a.get("asg"):
                asg_id = f"asg:{asg}"
                _node(nodes, asg_id, "asg", asg, r)
                edges.add((r.id, asg_id))
            for tg in a.get("target_groups", []):
                _node(nodes, tg["arn"], "target_group", tg["name"], r)
                edges.add((r.id, tg["arn"]))
                for lb_arn in tg.get("load_balancer_arns", []):
                    _node(nodes, lb_arn, "lb", lb_arn.split("/")[-2] if "/" in lb_arn else lb_arn, r)
                    edges.add((tg["arn"], lb_arn))
        for dep in re.split(r"[,\s]+", r.tags.get("depends-on", "")):
            if dep:
                target = dep if dep in nodes else by_name.get(dep)
                if target:
                    edges.add((r.id, target))

    # Security-group references: if A's SG allows inbound from SG x (attrs["sg_refs"]),
    # then every resource in x talks to A, i.e. depends on A.
    sg_members: dict[str, list[str]] = {}
    for r in nodes.values():
        for sg in r.attrs.get("security_groups", []):
            sg_members.setdefault(sg, []).append(r.id)
    for r in nodes.values():
        for sg in r.attrs.get("sg_refs", []):
            for client in sg_members.get(sg, []):
                edges.add((client, r.id))

    # keep explicit depends_on from producers (eval adapter)
    for r in nodes.values():
        for dep in r.depends_on:
            if dep in nodes:
                edges.add((r.id, dep))

    for r in nodes.values():
        r.depends_on, r.dependents = [], []
    for dependent, dependency in sorted(edges):
        if dependency == dependent:
            continue
        nodes[dependent].depends_on.append(dependency)
        nodes[dependency].dependents.append(dependent)
    for r in nodes.values():
        r.depends_on_names = [nodes[x].display_name for x in r.depends_on]
        r.dependent_names = [nodes[x].display_name for x in r.dependents]

    resources.extend(n for rid, n in nodes.items() if rid not in {r.id for r in resources})
    return {rid: list(n.dependents) for rid, n in nodes.items()}


def _traffic_shape(r: Resource) -> list[str]:
    m = r.metrics
    out: list[str] = []
    if m.cpu_max is not None and m.cpu_max < FLAT_ZERO_CPU and (m.db_connections_max or 0) == 0:
        out.append("flat_zero")
    series = m.daily_cpu_series
    if len(series) >= 5:
        med = statistics.median(series)
        high = [v for v in series if v >= max(med * SPIKE_FACTOR, med + 20)]
        if 0 < len(high) <= MAX_SPIKE_DAYS:
            out.append("periodic_spikes")
    return out


def role_hints(resource: Resource, graph: dict[str, list[str]], names: dict[str, str] | None = None) -> list[str]:
    names = names or {}
    hints: list[str] = []
    tokens = set(re.split(r"[^a-z0-9]+", resource.name.lower()))
    hints += [t for t in NAME_TOKENS if t in tokens]
    if src := resource.attrs.get("replica_source"):
        hints.append(f"replica_of:{names.get(src, src)}")
    if resource.attrs.get("asg"):
        hints.append("in_asg")
    if resource.attrs.get("target_groups"):
        hints.append("behind_lb")
    n = len(graph.get(resource.id, []))
    hints.append(f"has_dependents:{n}" if n else "no_dependents")
    hints += _traffic_shape(resource)
    if resource.iac_managed:
        hints.append("iac_managed")
    return hints


def annotate(resources: list[Resource]) -> dict[str, list[str]]:
    """build_graph + role_hints for every resource. Returns the graph."""
    graph = build_graph(resources)
    names = {r.id: r.display_name for r in resources}
    for r in resources:
        r.role_hints = role_hints(r, graph, names)
    return graph


def blast_radius_names(graph: dict[str, list[str]], start_id: str, names: dict[str, str]) -> list[str]:
    return [names.get(x, x) for x in blast_radius(graph, start_id)]
