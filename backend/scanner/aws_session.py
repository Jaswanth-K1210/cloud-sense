"""The one place boto3 sessions are created. Tests patch/fake this with moto."""

import threading
from datetime import UTC, datetime, timedelta

import boto3

REFRESH_MARGIN = timedelta(minutes=5)
_cache: dict[tuple[str, str], tuple[boto3.Session, datetime]] = {}
_lock = threading.Lock()


def assume_role(role_arn: str, external_id: str, session_name: str = "cloudsense") -> boto3.Session:
    """Session for the customer role. role_arn == "local" uses the default profile (dev only)."""
    if role_arn == "local":
        return boto3.Session()
    key = (role_arn, external_id)
    with _lock:
        hit = _cache.get(key)
        if hit and hit[1] - REFRESH_MARGIN > datetime.now(UTC):
            return hit[0]
        creds = boto3.client("sts").assume_role(
            RoleArn=role_arn, RoleSessionName=session_name, ExternalId=external_id
        )["Credentials"]
        session = boto3.Session(
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )
        _cache[key] = (session, creds["Expiration"])
        return session


def tags_to_dict(tags: list[dict[str, str]] | None) -> dict[str, str]:
    return {t["Key"]: t["Value"] for t in tags or []}


def owner_team(tags: dict[str, str]) -> str | None:
    return tags.get("team") or tags.get("owner") or tags.get("Team")


def service_of(tags: dict[str, str]) -> str | None:
    return tags.get("service") or tags.get("app")
