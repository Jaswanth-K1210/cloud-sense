"""Elastic IPs."""

import boto3

from backend.scanner.aws_session import owner_team, service_of, tags_to_dict
from backend.scanner.models import Resource


def describe(session: boto3.Session, region: str, account_alias: str, account_id: str) -> list[Resource]:
    client = session.client("ec2", region_name=region)
    out: list[Resource] = []
    for a in client.describe_addresses().get("Addresses", []):
        aid = a.get("AllocationId") or a["PublicIp"]
        tags = tags_to_dict(a.get("Tags"))
        target = a.get("InstanceId") or a.get("NetworkInterfaceId")
        out.append(Resource(
            id=aid, arn=f"arn:aws:ec2:{region}:{account_id}:elastic-ip/{aid}",
            account_alias=account_alias, region=region, type="eip",
            name=tags.get("Name", a["PublicIp"]), tags=tags, owner_team=owner_team(tags), service=service_of(tags),
            state="associated" if target else "unassociated",
            attrs={"associated_to": target, "public_ip": a["PublicIp"]},
        ))
    return out
