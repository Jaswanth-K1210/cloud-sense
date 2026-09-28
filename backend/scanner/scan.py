"""Scan one AWS account across its regions."""

from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from backend.scanner import ebs, ec2, eip, metrics, rds, s3
from backend.scanner.aws_session import assume_role
from backend.scanner.models import Resource

REGIONAL = (ec2.describe, ebs.describe, rds.describe, eip.describe)


class AccountLike(Protocol):
    alias: str
    aws_account_id: str
    role_arn: str
    external_id: str
    regions: list


def scan_account(account: AccountLike) -> list[Resource]:
    session = assume_role(account.role_arn, account.external_id)
    regions = list(account.regions) or ["us-east-1"]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fn, session, region, account.alias, account.aws_account_id)
                   for region in regions for fn in REGIONAL]
        futures.append(pool.submit(s3.describe, session, account.alias))
        sg_futures = {region: pool.submit(ec2.sg_references, session, region) for region in regions}
        resources = [r for f in futures for r in f.result()]

        by_region: dict[str, list[Resource]] = {}
        for r in resources:
            by_region.setdefault(r.region, []).append(r)
            if sgs := r.attrs.get("security_groups"):
                refs = sg_futures[r.region].result() if r.region in sg_futures else {}
                r.attrs["sg_refs"] = sorted({x for sg in sgs for x in refs.get(sg, [])})
        list(pool.map(lambda kv: metrics.attach_metrics(session, kv[0], kv[1]), by_region.items()))
    return resources
