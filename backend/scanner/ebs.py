"""EBS volumes (with attachment) and self-owned snapshots (with AMI references)."""

import boto3

from backend.scanner.aws_session import owner_team, service_of, tags_to_dict
from backend.scanner.models import Resource


def describe(session: boto3.Session, region: str, account_alias: str, account_id: str) -> list[Resource]:
    client = session.client("ec2", region_name=region)
    out: list[Resource] = []
    for page in client.get_paginator("describe_volumes").paginate():
        for v in page["Volumes"]:
            vid = v["VolumeId"]
            tags = tags_to_dict(v.get("Tags"))
            attached = [a["InstanceId"] for a in v.get("Attachments", []) if a.get("InstanceId")]
            out.append(Resource(
                id=vid, arn=f"arn:aws:ec2:{region}:{account_id}:volume/{vid}",
                account_alias=account_alias, region=region, type="ebs",
                name=tags.get("Name", vid), tags=tags, owner_team=owner_team(tags), service=service_of(tags),
                state=v["State"], volume_type=v.get("VolumeType"), size_gb=v.get("Size"),
                created_at=v.get("CreateTime"),
                attrs={"attached_to": attached[0] if attached else None,
                       "availability_zone": v.get("AvailabilityZone")},
            ))
    return out + describe_snapshots(session, region, account_alias, account_id)


def describe_snapshots(session: boto3.Session, region: str, account_alias: str, account_id: str) -> list[Resource]:
    client = session.client("ec2", region_name=region)
    ami_snaps: set[str] = set()
    for img in client.describe_images(Owners=["self"]).get("Images", []):
        for m in img.get("BlockDeviceMappings", []):
            if sid := m.get("Ebs", {}).get("SnapshotId"):
                ami_snaps.add(sid)
    out: list[Resource] = []
    for page in client.get_paginator("describe_snapshots").paginate(OwnerIds=["self"]):
        for s in page["Snapshots"]:
            sid = s["SnapshotId"]
            tags = tags_to_dict(s.get("Tags"))
            out.append(Resource(
                id=sid, arn=f"arn:aws:ec2:{region}:{account_id}:snapshot/{sid}",
                account_alias=account_alias, region=region, type="snapshot",
                name=tags.get("Name", sid), tags=tags, owner_team=owner_team(tags), service=service_of(tags),
                state=s.get("State", "completed"), size_gb=s.get("VolumeSize"), created_at=s.get("StartTime"),
                attrs={"source_volume": s.get("VolumeId"), "used_by_ami": sid in ami_snaps},
            ))
    return out
