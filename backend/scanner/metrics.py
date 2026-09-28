"""CloudWatch metrics via batched GetMetricData (<= 500 queries per call)."""

import statistics
from collections import defaultdict
from datetime import UTC, datetime, timedelta

import boto3

from backend.config import settings
from backend.scanner.models import Resource, ResourceMetrics

MAX_QUERIES = 500
PERIOD_S = 3600
DEFAULT_LOOKBACK = timedelta(days=14)

# (resource type, metric name, namespace, dimension, stat, field)
SPECS = [
    ("ec2", "CPUUtilization", "AWS/EC2", "InstanceId", "Average", "cpu"),
    ("ec2", "NetworkIn", "AWS/EC2", "InstanceId", "Sum", "net_in"),
    ("ec2", "NetworkOut", "AWS/EC2", "InstanceId", "Sum", "net_out"),
    ("rds", "CPUUtilization", "AWS/RDS", "DBInstanceIdentifier", "Average", "cpu"),
    ("rds", "DatabaseConnections", "AWS/RDS", "DBInstanceIdentifier", "Maximum", "conns"),
]


def lookback() -> timedelta:
    return timedelta(hours=settings.DEMO_LOOKBACK_HOURS) if settings.DEMO_LOOKBACK_HOURS else DEFAULT_LOOKBACK


def build_queries(resources: list[Resource]) -> tuple[list[dict], dict[str, tuple[str, str]]]:
    queries: list[dict] = []
    index: dict[str, tuple[str, str]] = {}  # query id -> (resource id, field)
    for r in resources:
        for rtype, metric, ns, dim, stat, field in SPECS:
            if r.type != rtype:
                continue
            qid = f"q{len(queries)}"
            index[qid] = (r.id, field)
            queries.append({"Id": qid, "ReturnData": True, "MetricStat": {
                "Metric": {"Namespace": ns, "MetricName": metric, "Dimensions": [{"Name": dim, "Value": r.id}]},
                "Period": PERIOD_S, "Stat": stat}})
        if r.type == "s3":
            qid = f"q{len(queries)}"
            index[qid] = (r.id, "s3_bytes")
            queries.append({"Id": qid, "ReturnData": True, "MetricStat": {
                "Metric": {"Namespace": "AWS/S3", "MetricName": "BucketSizeBytes", "Dimensions": [
                    {"Name": "BucketName", "Value": r.id}, {"Name": "StorageType", "Value": "StandardStorage"}]},
                "Period": 86400, "Stat": "Average"}})
    return queries, index


def fetch(client, queries: list[dict], start: datetime, end: datetime) -> dict[str, list[tuple[datetime, float]]]:
    """One GetMetricData call per chunk of 500 queries (following NextToken)."""
    out: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    for i in range(0, len(queries), MAX_QUERIES):
        kw: dict = {"MetricDataQueries": queries[i:i + MAX_QUERIES], "StartTime": start, "EndTime": end}
        while True:
            resp = client.get_metric_data(**kw)
            for res in resp["MetricDataResults"]:
                out[res["Id"]].extend(zip(res.get("Timestamps", []), res.get("Values", []), strict=False))
            if not resp.get("NextToken"):
                break
            kw["NextToken"] = resp["NextToken"]
    return out


def p95(values: list[float]) -> float:
    if len(values) < 2:
        return values[0]
    return statistics.quantiles(values, n=20, method="inclusive")[-1]


def daily(points: list[tuple[datetime, float]], agg=statistics.fmean) -> list[float]:
    by_day: dict = defaultdict(list)
    for ts, v in points:
        by_day[ts.date()].append(v)
    return [agg(by_day[d]) for d in sorted(by_day)]


def aggregate(series: dict[str, list[tuple[datetime, float]]], days: float) -> ResourceMetrics:
    m = ResourceMetrics()
    if cpu := series.get("cpu"):
        vals = [v for _, v in cpu]
        m.cpu_avg, m.cpu_max, m.cpu_p95 = statistics.fmean(vals), max(vals), p95(vals)
        m.daily_cpu_series = daily(cpu)
    if pts := series.get("net_in"):
        m.net_in_mb_per_day = sum(v for _, v in pts) / 1e6 / days
    if pts := series.get("net_out"):
        m.net_out_mb_per_day = sum(v for _, v in pts) / 1e6 / days
    if pts := series.get("conns"):
        m.db_connections_max = max(v for _, v in pts)
    return m


def attach_metrics(session: boto3.Session, region: str, resources: list[Resource]) -> None:
    """Fill `metrics` (and S3 size_gb) in place for resources in this region."""
    queries, index = build_queries(resources)
    if not queries:
        return
    end = datetime.now(UTC)
    span = lookback()
    raw = fetch(session.client("cloudwatch", region_name=region), queries, end - span, end)
    per_res: dict[str, dict[str, list]] = defaultdict(dict)
    for qid, pts in raw.items():
        rid, field = index[qid]
        per_res[rid][field] = pts
    days = span.total_seconds() / 86400
    for r in resources:
        series = per_res.get(r.id, {})
        if r.type == "s3":
            if pts := series.get("s3_bytes"):
                r.size_gb = max(pts)[1] / 1e9  # latest datapoint
        elif series:
            r.metrics = aggregate(series, days)
