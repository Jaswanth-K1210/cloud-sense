"""Safe execution (BUILD_DOC section 9): approved only, snapshot first, dry run by default, audited, undoable."""

from datetime import UTC, datetime, timedelta
from typing import Any

from botocore import xform_name
from sqlalchemy.orm import Session

from backend.actions.iac import terraform_diff
from backend.candidates.pricing import one_size_down
from backend.config import settings
from backend.scanner import aws_session
from backend.scanner.models import Resource
from backend.store import repo
from backend.store.models import Account, ActionRow, CandidateRow, CandidateStatus, ResourceRow, Scan

GP3_COOLDOWN = timedelta(hours=6)
RDS_AUTO_RESTART = timedelta(days=7)
WAITER = {"Delay": 5, "MaxAttempts": 120}


class ExecutionError(Exception):
    pass


def call(service: str, op: str, region: str, wait: str | None = None, **params: Any) -> dict[str, Any]:
    return {"service": service, "op": op, "region": region, "params": params, **({"wait": wait} if wait else {})}


def _tags(cand: CandidateRow, actor: str) -> list[dict[str, str]]:
    return [{"Key": "cloudsense:stopped-by", "Value": actor}, {"Key": "cloudsense:candidate", "Value": cand.id}]


def plan(cand: CandidateRow, res: Resource, actor: str) -> tuple[str, list[dict[str, Any]]]:
    """Exact AWS calls, in order. Snapshot steps always come first."""
    r, desc = res.region, f"cloudsense pre-action snapshot for candidate {cand.id}"
    if res.type == "ec2" and cand.action == "stop":
        snaps = [call("ec2", "CreateSnapshot", r, VolumeId=v, Description=desc) for v in res.attrs.get("volumes", [])]
        return "stop_ec2", [*snaps, call("ec2", "StopInstances", r, InstanceIds=[res.id]),
                            call("ec2", "CreateTags", r, Resources=[res.id], Tags=_tags(cand, actor))]
    if res.type == "ec2" and cand.action == "rightsize":
        new = one_size_down(res.instance_type or "")
        if not new:
            raise ExecutionError(f"no smaller size for {res.instance_type}")
        return "rightsize_ec2", [
            call("ec2", "StopInstances", r, wait="instance_stopped", InstanceIds=[res.id]),
            call("ec2", "ModifyInstanceAttribute", r, InstanceId=res.id, InstanceType={"Value": new}),
            call("ec2", "StartInstances", r, InstanceIds=[res.id]),
            call("ec2", "CreateTags", r, Resources=[res.id], Tags=_tags(cand, actor))]
    if res.type == "ebs" and cand.action == "modify_gp3":
        return "modify_gp3", [call("ec2", "ModifyVolume", r, VolumeId=res.id, VolumeType="gp3"),
                              call("ec2", "CreateTags", r, Resources=[res.id], Tags=_tags(cand, actor))]
    if res.type == "ebs" and cand.action == "snapshot_delete":
        return "delete_ebs", [
            call("ec2", "CreateSnapshot", r, wait="snapshot_completed", VolumeId=res.id, Description=desc),
            # the action role only allows DeleteVolume on volumes tagged cloudsense:approved=true
            call("ec2", "CreateTags", r, Resources=[res.id], Tags=[{"Key": "cloudsense:approved", "Value": "true"}]),
            call("ec2", "DeleteVolume", r, VolumeId=res.id)]
    if res.type == "rds" and cand.action == "stop":
        snap_id = f"cloudsense-{cand.id[:12]}"
        return "stop_rds", [
            call("rds", "CreateDBSnapshot", r, DBSnapshotIdentifier=snap_id, DBInstanceIdentifier=res.id),
            call("rds", "StopDBInstance", r, DBInstanceIdentifier=res.id),
            call("rds", "AddTagsToResource", r, ResourceName=res.arn, Tags=_tags(cand, actor))]
    raise ExecutionError(f"{cand.action} on {res.type} is recommend-only in v1 (irreversible or not automated)")


def run_calls(session: Any, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Execute planned calls; returns [{op, result}] with the response fields we need for undo."""
    results = []
    for c in calls:
        client = session.client(c["service"], region_name=c["region"])
        resp = getattr(client, xform_name(c["op"]))(**c["params"])
        if c.get("wait") == "snapshot_completed":
            client.get_waiter("snapshot_completed").wait(SnapshotIds=[resp["SnapshotId"]], WaiterConfig=WAITER)
        elif c.get("wait") == "instance_stopped":
            client.get_waiter("instance_stopped").wait(InstanceIds=c["params"]["InstanceIds"], WaiterConfig=WAITER)
        results.append({"op": c["op"], "snapshot_id": resp.get("SnapshotId") or
                        resp.get("DBSnapshot", {}).get("DBSnapshotIdentifier")})
    return results


def check_gp3_cooldown(session: Any, res: Resource) -> None:
    ec2 = session.client("ec2", region_name=res.region)
    mods = ec2.describe_volumes_modifications(VolumeIds=[res.id]).get("VolumesModifications", [])
    recent = [m for m in mods if m.get("StartTime") and datetime.now(UTC) - m["StartTime"] < GP3_COOLDOWN]
    if recent:
        raise ExecutionError("gp3 modify cooldown: this volume was modified in the last 6 hours")


def action_json(a: ActionRow) -> dict[str, Any]:
    return {"id": a.id, "candidate_id": a.candidate_id, "kind": a.kind, "status": a.status,
            "api_calls": a.api_calls_json, "pre_snapshot_ids": a.pre_snapshot_ids, "undo_handle": a.undo_handle,
            "at": a.at}


def execute(s: Session, cand: CandidateRow, actor: str, dry_run: bool | None = None,
            session_for=aws_session.assume_role) -> ActionRow:
    dry_run = settings.DRY_RUN if dry_run is None else dry_run
    if cand.status != CandidateStatus.approved:
        raise ExecutionError(f"candidate is {cand.status.value}; only approved candidates can be executed")
    row = s.get(ResourceRow, cand.resource_id)
    res = Resource.model_validate(row.data_json)
    org_id = s.get(Scan, cand.scan_id).org_id

    if res.iac_managed:  # never call AWS
        a = repo.record_action(s, candidate_id=cand.id, kind="iac_diff", status="diff",
                               undo_handle={"terraform_diff": terraform_diff(cand.action, res)})
        repo.log_audit(s, org_id, actor, "iac_diff", {"candidate_id": cand.id})
        s.commit()
        return a

    kind, calls = plan(cand, res, actor)
    undo: dict[str, Any] = {"resource_id": res.id, "region": res.region, "type": res.type}
    if kind == "rightsize_ec2":
        undo["old_instance_type"] = res.instance_type
    if kind == "delete_ebs":
        undo |= {"availability_zone": res.attrs.get("availability_zone"), "volume_type": res.volume_type,
                 "size_gb": res.size_gb}

    if dry_run:
        a = repo.record_action(s, candidate_id=cand.id, kind=kind, api_calls_json=calls, status="dry_run",
                               undo_handle=undo)
        repo.log_audit(s, org_id, actor, "action_dry_run", {"candidate_id": cand.id, "kind": kind})
        s.commit()
        return a

    acct = s.get(Account, row.account_id) if row.account_id else None
    if acct is None or not acct.action_role_arn:
        raise ExecutionError("no action role connected for this account (opt-in CloudSenseActionRole)")
    session = session_for(acct.action_role_arn, acct.external_id, "cloudsense-action")
    if kind == "modify_gp3":
        check_gp3_cooldown(session, res)
    results = run_calls(session, calls)
    snaps = [r["snapshot_id"] for r in results if r["snapshot_id"]]
    undo["snapshot_ids"] = snaps
    a = repo.record_action(s, candidate_id=cand.id, kind=kind, api_calls_json=calls, pre_snapshot_ids=snaps,
                           status="done", undo_handle=undo)
    cand.status = CandidateStatus.executed
    repo.log_audit(s, org_id, actor, "action_executed", {"candidate_id": cand.id, "action_id": a.id, "kind": kind,
                                                         "snapshot_ids": snaps})
    if kind == "stop_rds":
        due = datetime.now(UTC) + RDS_AUTO_RESTART
        repo.log_audit(s, org_id, "cloudsense", "reminder", {
            "action_id": a.id, "due_at": due.isoformat(),
            "text": f"AWS restarts {res.id} automatically after 7 days; re-stop it or snapshot + delete."})
    s.commit()
    return a
