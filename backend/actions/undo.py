"""Undo an executed action using its undo_handle."""

from typing import Any

from sqlalchemy.orm import Session

from backend.actions.executor import ExecutionError, call, run_calls
from backend.scanner import aws_session
from backend.store import repo
from backend.store.models import Account, ActionRow, CandidateRow, CandidateStatus, ResourceRow, Scan


def undo_plan(a: ActionRow) -> list[dict[str, Any]]:
    h, r = a.undo_handle, a.undo_handle.get("region", "us-east-1")
    rid = h.get("resource_id")
    if a.kind == "stop_ec2":
        return [call("ec2", "StartInstances", r, InstanceIds=[rid])]
    if a.kind == "rightsize_ec2":
        return [call("ec2", "StopInstances", r, wait="instance_stopped", InstanceIds=[rid]),
                call("ec2", "ModifyInstanceAttribute", r, InstanceId=rid,
                     InstanceType={"Value": h["old_instance_type"]}),
                call("ec2", "StartInstances", r, InstanceIds=[rid])]
    if a.kind == "delete_ebs":
        snaps = h.get("snapshot_ids") or []
        if not snaps or not h.get("availability_zone"):
            raise ExecutionError("no snapshot/AZ recorded; cannot restore")
        return [call("ec2", "CreateVolume", r, SnapshotId=snaps[0], AvailabilityZone=h["availability_zone"],
                     VolumeType=h.get("volume_type") or "gp3",
                     TagSpecifications=[{"ResourceType": "volume", "Tags": [
                         {"Key": "cloudsense:restored-from", "Value": rid}]}])]
    if a.kind == "stop_rds":
        return [call("rds", "StartDBInstance", r, DBInstanceIdentifier=rid)]
    raise ExecutionError(f"{a.kind} has no undo")


def undo(s: Session, a: ActionRow, actor: str, session_for=aws_session.assume_role) -> ActionRow:
    if a.status != "done":
        raise ExecutionError(f"action is {a.status}; only executed actions can be undone")
    cand = s.get(CandidateRow, a.candidate_id)
    row = s.get(ResourceRow, cand.resource_id)
    acct = s.get(Account, row.account_id) if row.account_id else None
    if acct is None or not acct.action_role_arn:
        raise ExecutionError("no action role connected for this account")
    calls = undo_plan(a)
    results = run_calls(session_for(acct.action_role_arn, acct.external_id, "cloudsense-undo"), calls)
    note = {}
    if a.kind == "delete_ebs":
        note = {"note": "Volume restored from snapshot; re-attach it to the instance manually.",
                "results": results}
    u = repo.record_action(s, candidate_id=cand.id, kind=f"undo:{a.kind}", api_calls_json=calls, status="done",
                           undo_handle=note)
    a.status = "undone"
    cand.status = CandidateStatus.approved
    repo.log_audit(s, s.get(Scan, cand.scan_id).org_id, actor, "action_undone", {"action_id": a.id,
                                                                                "undo_action_id": u.id})
    s.commit()
    return u
