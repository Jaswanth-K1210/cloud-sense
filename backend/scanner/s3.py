"""S3 buckets (global list; region, tags and lifecycle per bucket). Size comes from metrics."""

import boto3
from botocore.exceptions import ClientError

from backend.scanner.aws_session import owner_team, service_of, tags_to_dict
from backend.scanner.models import Resource


def _call(fn, missing_code: str, **kw):
    try:
        return fn(**kw)
    except ClientError as e:
        if e.response["Error"]["Code"] == missing_code:
            return None
        raise


def describe(session: boto3.Session, account_alias: str) -> list[Resource]:
    client = session.client("s3")
    out: list[Resource] = []
    for b in client.list_buckets().get("Buckets", []):
        name = b["Name"]
        region = client.get_bucket_location(Bucket=name).get("LocationConstraint") or "us-east-1"
        tagging = _call(client.get_bucket_tagging, "NoSuchTagSet", Bucket=name)
        lifecycle = _call(client.get_bucket_lifecycle_configuration, "NoSuchLifecycleConfiguration", Bucket=name)
        tags = tags_to_dict(tagging["TagSet"] if tagging else [])
        out.append(Resource(
            id=name, arn=f"arn:aws:s3:::{name}", account_alias=account_alias, region=region, type="s3",
            name=name, tags=tags, owner_team=owner_team(tags), service=service_of(tags),
            state="available", created_at=b.get("CreationDate"),
            attrs={"lifecycle_configured": bool(lifecycle and lifecycle.get("Rules"))},
        ))
    return out
