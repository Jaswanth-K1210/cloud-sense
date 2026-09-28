"""RDS DB instances, including read-replica source."""

import boto3

from backend.scanner.aws_session import owner_team, service_of, tags_to_dict
from backend.scanner.models import Resource


def describe(session: boto3.Session, region: str, account_alias: str, account_id: str) -> list[Resource]:
    client = session.client("rds", region_name=region)
    out: list[Resource] = []
    for page in client.get_paginator("describe_db_instances").paginate():
        for db in page["DBInstances"]:
            ident = db["DBInstanceIdentifier"]
            arn = db.get("DBInstanceArn", f"arn:aws:rds:{region}:{account_id}:db:{ident}")
            tag_list = db.get("TagList")
            if tag_list is None:
                tag_list = client.list_tags_for_resource(ResourceName=arn).get("TagList", [])
            tags = tags_to_dict(tag_list)
            source = db.get("ReadReplicaSourceDBInstanceIdentifier")
            out.append(Resource(
                id=ident, arn=arn, account_alias=account_alias, region=region, type="rds",
                name=ident, tags=tags, owner_team=owner_team(tags), service=service_of(tags),
                state=db.get("DBInstanceStatus", "unknown"), instance_type=db.get("DBInstanceClass"),
                size_gb=db.get("AllocatedStorage"), created_at=db.get("InstanceCreateTime"),
                attrs={
                    "engine": db.get("Engine"),
                    "multi_az": db.get("MultiAZ", False),
                    # source may be an ARN for cross-region replicas; keep the identifier
                    "replica_source": source.split(":")[-1] if source else None,
                    "security_groups": [g["VpcSecurityGroupId"] for g in db.get("VpcSecurityGroups", [])],
                },
            ))
    return out
