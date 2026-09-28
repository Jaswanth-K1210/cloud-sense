"""Convert eval env resources (CloudResource dicts) into backend Resource models."""

from typing import Any

from backend.scanner.models import Resource, ResourceMetrics
from eval.cloudsense_env.models import CloudResource

TYPE_MAP = {
    "ec2": "ec2", "rds": "rds", "s3": "s3", "ebs": "ebs", "eip": "eip",
    "load_balancer": "lb", "kubernetes": "eks", "nat_gateway": "nat", "elasticsearch": "opensearch",
}
SPIKY_PATTERNS = ("batch", "seasonal", "spike")
DAYS = 14


def _metrics(r: CloudResource) -> ResourceMetrics:
    u = r.utilization
    cpu = u.get("cpu_percent")
    spiky = any(p in r.usage_pattern.lower() for p in SPIKY_PATTERNS)
    if cpu is None:
        series: list[float] = []
        cpu_max = p95 = None
    elif spiky:
        # low median with a couple of heavy days (month-end / nightly batch)
        series = [float(cpu)] * DAYS
        series[6] = series[13] = 95.0
        cpu_max, p95 = 95.0, 95.0
    else:
        series = [float(cpu)] * DAYS
        cpu_max, p95 = min(100.0, cpu * 1.5), min(100.0, cpu * 1.2)
    mb_day = u["network_mbps"] / 8 * 86400 if "network_mbps" in u else None
    return ResourceMetrics(
        cpu_avg=cpu, cpu_max=cpu_max, cpu_p95=p95,
        net_in_mb_per_day=mb_day / 2 if mb_day is not None else None,
        net_out_mb_per_day=mb_day / 2 if mb_day is not None else None,
        db_connections_max=u.get("connections"),
        daily_cpu_series=series,
    )


def _state(r: CloudResource) -> str:
    cfg = r.current_config
    if r.resource_type.value == "ebs":
        return "in-use" if cfg.get("attached") else "available"
    if r.resource_type.value == "eip":
        return "associated" if cfg.get("associated") else "unassociated"
    return "running" if r.usage_pattern != "unused" else "idle"


def to_resource(r: CloudResource | dict[str, Any], account_alias: str = "eval") -> Resource:
    if isinstance(r, dict):
        r = CloudResource(**r)
    cfg = r.current_config
    tags = {k: str(v) for k, v in r.tags.items()}
    attrs: dict[str, Any] = {"environment": r.environment.value, "monthly_cost": r.monthly_cost,
                             "usage_pattern": r.usage_pattern, "is_critical": r.is_critical}
    if "lifecycle_policy" in cfg:
        attrs["lifecycle_configured"] = bool(cfg["lifecycle_policy"])
    if cfg.get("in_asg") or cfg.get("asg_name"):
        attrs["asg"] = cfg.get("asg_name") or "asg"
    if cfg.get("role"):
        attrs["db_role"] = cfg["role"]
    return Resource(
        id=r.resource_id,
        arn=f"arn:aws:eval:{r.region}::{r.resource_id}",
        account_alias=account_alias,
        region=r.region,
        type=TYPE_MAP[r.resource_type.value],
        name=r.name,
        tags=tags,
        owner_team=tags.get("team") or tags.get("owner"),
        service=tags.get("service") or tags.get("project"),
        state=_state(r),
        instance_type=cfg.get("instance_type") if r.resource_type.value in ("ec2", "rds") else None,
        volume_type=cfg.get("volume_type"),
        size_gb=cfg.get("size_gb") or cfg.get("storage_gb"),
        metrics=_metrics(r),
        depends_on=list(r.dependencies),
        attrs=attrs,
    )


def to_resources(raw: list[dict[str, Any]], account_alias: str = "eval") -> list[Resource]:
    """Convert a whole account and fill `dependents` by inverting `depends_on`."""
    out = [to_resource(r, account_alias) for r in raw]
    by_id = {r.id: r for r in out}
    for r in out:
        for dep in r.depends_on:
            if dep in by_id:
                by_id[dep].dependents.append(r.id)
    return out
