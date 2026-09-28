"""Monthly prices (us-east-1) from aws_pricing.json. Exact lookups only; unknown -> None."""

import json
from functools import cache

from backend.candidates import PRICING_FILE
from backend.scanner.models import Resource

SIZES = ["nano", "micro", "small", "medium", "large", "xlarge", "2xlarge", "4xlarge", "8xlarge"]


@cache
def prices() -> dict:
    return json.loads(PRICING_FILE.read_text())


def one_size_down(instance_type: str) -> str | None:
    """t3.large -> t3.medium; db.r5.xlarge -> db.r5.large. Same family only."""
    family, _, size = instance_type.rpartition(".")
    if size not in SIZES or SIZES.index(size) == 0:
        return None
    return f"{family}.{SIZES[SIZES.index(size) - 1]}"


def _instance_price(r: Resource, itype: str | None = None) -> float | None:
    itype = itype or r.instance_type
    table = {"ec2": "ec2", "rds": "rds"}.get(r.type)
    return prices()[table].get(itype) if table and itype else None


def _per_gb(key: str, size: float | None) -> float | None:
    rate = prices()["ebs"].get(key)
    return round(rate * size, 2) if rate is not None and size is not None else None


def monthly_cost(r: Resource) -> float | None:
    if r.type in ("ec2", "rds"):
        return _instance_price(r)
    if r.type == "ebs":
        return _per_gb(f"{r.volume_type}_per_gb", r.size_gb)
    if r.type == "snapshot":
        return _per_gb("snapshot_per_gb", r.size_gb)
    if r.type == "eip":
        return prices()["eip"]["unused_monthly"] if r.state == "unassociated" else 0.0
    if r.type == "s3" and r.size_gb is not None:
        return round(prices()["s3"]["standard_per_gb"] * r.size_gb, 2)
    return None


def saving_for(action: str, r: Resource) -> float | None:
    if action == "stop":  # compute stops billing; storage keeps billing
        return _instance_price(r)
    if action == "rightsize":
        target = one_size_down(r.instance_type or "")
        old, new = _instance_price(r), _instance_price(r, target) if target else None
        return round(old - new, 2) if old is not None and new is not None else None
    if action == "modify_gp3":
        g2, g3 = _per_gb("gp2_per_gb", r.size_gb), _per_gb("gp3_per_gb", r.size_gb)
        return round(g2 - g3, 2) if g2 is not None and g3 is not None else None
    if action == "snapshot_delete":  # volume goes away, the snapshot we keep costs money
        vol, snap = monthly_cost(r), _per_gb("snapshot_per_gb", r.size_gb)
        return round(vol - snap, 2) if vol is not None and snap is not None else None
    if action == "delete_snapshot":
        return monthly_cost(r)
    if action == "release":
        return prices()["eip"]["unused_monthly"]
    if action == "s3_lifecycle" and r.size_gb is not None:
        s3 = prices()["s3"]
        return round((s3["standard_per_gb"] - s3["intelligent_tiering_ia_per_gb"]) * r.size_gb, 2)
    return None
