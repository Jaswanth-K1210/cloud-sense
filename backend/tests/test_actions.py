from dataclasses import dataclass, field

import boto3
import pytest
from moto import mock_aws
from sqlalchemy.orm import Session, sessionmaker

from backend.actions.executor import ExecutionError, execute
from backend.actions.undo import undo
from backend.scanner.aws_session import assume_role
from backend.scanner.models import Resource
from backend.scanner.scan import scan_account
from backend.store.db import init_db, make_engine
from backend.store.models import Account, AuditLog, CandidateRow, CandidateStatus, ResourceRow, Scan
from backend.store.seed_demo import seed

REGION = "us-east-1"


@dataclass
class Acct:
    alias: str = "sandbox"
    aws_account_id: str = "123456789012"
    role_arn: str = "local"
    external_id: str = "x"
    regions: list = field(default_factory=lambda: [REGION])


class CallCounter:
    def __init__(self) -> None:
        self.n = 0

    def __call__(self, *a, **kw):
        self.n += 1
        return assume_role("local", "x")


@pytest.fixture
def env():
    with mock_aws():
        ec2 = boto3.client("ec2", region_name=REGION)
        ami = ec2.describe_images(Owners=["amazon"])["Images"][0]["ImageId"]
        inst = ec2.run_instances(ImageId=ami, MinCount=1, MaxCount=1, InstanceType="t3.large",
                                 TagSpecifications=[{"ResourceType": "instance",
                                                     "Tags": [{"Key": "Name", "Value": "dev-sandbox-3"}]}])
        iid = inst["Instances"][0]["InstanceId"]
        az = inst["Instances"][0]["Placement"]["AvailabilityZone"]
        vol = ec2.create_volume(AvailabilityZone=az, Size=8, VolumeType="gp3")["VolumeId"]
        ec2.attach_volume(VolumeId=vol, InstanceId=iid, Device="/dev/sdf")
        loose = ec2.create_volume(AvailabilityZone=az, Size=4, VolumeType="gp2")["VolumeId"]

        engine = make_engine("sqlite://")
        init_db(engine)
        s = sessionmaker(bind=engine, expire_on_commit=False)()
        seed(s)
        s.get(Account, "acct-sandbox").action_role_arn = "local"
        s.add(Scan(id="scan1", org_id="acme", status="done"))
        for r in scan_account(Acct()):
            s.add(ResourceRow(id=f"row-{r.id}", scan_id="scan1", account_id="acct-sandbox", aws_id=r.id, type=r.type,
                              name=r.display_name, data_json=r.model_dump(mode="json")))
        s.commit()
        yield {"s": s, "ec2": ec2, "iid": iid, "vol": vol, "loose": loose}
        s.close()


def cand(s: Session, aws_id: str, action: str, status=CandidateStatus.approved, cid: str = "c1") -> CandidateRow:
    c = CandidateRow(id=cid, scan_id="scan1", resource_id=f"row-{aws_id}", rule_id="R1", action=action,
                     status=status)
    s.add(c)
    s.commit()
    return c


def state(ec2, iid: str) -> str:
    return ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0]["State"]["Name"]


def test_approved_stop_snapshots_stops_tags_and_undo_restarts(env) -> None:
    s, ec2, iid = env["s"], env["ec2"], env["iid"]
    c = cand(s, iid, "stop")
    a = execute(s, c, actor="u-reviewer", dry_run=False)
    assert a.status == "done" and c.status == CandidateStatus.executed
    snaps = ec2.describe_snapshots(OwnerIds=["self"])["Snapshots"]
    assert {sn["VolumeId"] for sn in snaps} >= {env["vol"]}
    assert a.pre_snapshot_ids
    assert state(ec2, iid) == "stopped"
    tags = {t["Key"]: t["Value"] for t in ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]
            ["Instances"][0]["Tags"]}
    assert tags["cloudsense:stopped-by"] == "u-reviewer" and tags["cloudsense:candidate"] == "c1"
    assert s.query(AuditLog).filter_by(event="action_executed").count() == 1

    u = undo(s, a, actor="u-reviewer")
    assert u.kind == "undo:stop_ec2" and a.status == "undone"
    assert state(ec2, iid) in ("pending", "running")
    assert c.status == CandidateStatus.approved


def test_dry_run_makes_zero_aws_calls(env) -> None:
    s = env["s"]
    counter = CallCounter()
    a = execute(s, cand(s, env["iid"], "stop"), actor="u", dry_run=True, session_for=counter)
    assert counter.n == 0
    assert a.status == "dry_run"
    ops = [c["op"] for c in a.api_calls_json]
    assert ops == ["CreateSnapshot"] * 2 + ["StopInstances", "CreateTags"]  # root + attached volume first
    assert state(env["ec2"], env["iid"]) == "running"


def test_unapproved_candidate_is_refused(env) -> None:
    s = env["s"]
    with pytest.raises(ExecutionError, match="only approved"):
        execute(s, cand(s, env["iid"], "stop", status=CandidateStatus.pending), actor="u", dry_run=False)


def test_iac_managed_returns_diff_and_makes_no_calls(env) -> None:
    s = env["s"]
    row = s.get(ResourceRow, f"row-{env['iid']}")
    res = Resource.model_validate(row.data_json)
    res.tags["created_by"] = "terraform"
    row.data_json = res.model_dump(mode="json")
    s.commit()
    counter = CallCounter()
    a = execute(s, cand(s, env["iid"], "rightsize"), actor="u", dry_run=False, session_for=counter)
    assert counter.n == 0 and a.kind == "iac_diff"
    diff = a.undo_handle["terraform_diff"]
    assert '-  instance_type = "t3.large"' in diff and '+  instance_type = "t3.medium"' in diff
    assert state(env["ec2"], env["iid"]) == "running"


def test_delete_ebs_snapshots_first_and_undo_restores(env) -> None:
    s, ec2 = env["s"], env["ec2"]
    a = execute(s, cand(s, env["loose"], "snapshot_delete"), actor="u", dry_run=False)
    assert [c["op"] for c in a.api_calls_json] == ["CreateSnapshot", "CreateTags", "DeleteVolume"]
    assert env["loose"] not in {v["VolumeId"] for v in ec2.describe_volumes()["Volumes"]}
    u = undo(s, a, actor="u")
    assert "re-attach" in u.undo_handle["note"]
    restored = [v for v in ec2.describe_volumes()["Volumes"]
                if {"Key": "cloudsense:restored-from", "Value": env["loose"]} in v.get("Tags", [])]
    assert len(restored) == 1


def test_refuses_without_action_role(env) -> None:
    s = env["s"]
    s.get(Account, "acct-sandbox").action_role_arn = None
    s.commit()
    with pytest.raises(ExecutionError, match="action role"):
        execute(s, cand(s, env["iid"], "stop"), actor="u", dry_run=False)


def test_irreversible_actions_are_recommend_only(env) -> None:
    s = env["s"]
    with pytest.raises(ExecutionError, match="recommend-only"):
        execute(s, cand(s, env["iid"], "release"), actor="u", dry_run=True)
