import pytest
from sqlalchemy.orm import Session, sessionmaker

from backend.store import repo
from backend.store.db import init_db, make_engine
from backend.store.models import (
    ActionRow,
    AuditLog,
    CandidateRow,
    CandidateStatus,
    Decision,
    ResourceRow,
    Role,
    Scope,
    User,
    Verdict,
)
from backend.store.seed_demo import seed


@pytest.fixture
def s() -> Session:
    eng = make_engine("sqlite://")
    init_db(eng)
    with sessionmaker(bind=eng)() as session:
        yield session


def _scan_with_resource(s: Session):
    org = repo.create_org(s, "Acme")
    acct = repo.add_account(s, org.id, alias="prod", aws_account_id="1", role_arn="r", external_id="x")
    scan = repo.create_scan(s, org.id)
    (res,) = repo.save_resources(s, [ResourceRow(scan_id=scan.id, account_id=acct.id, aws_id="i-1", type="ec2")])
    return org, acct, scan, res


def test_org_account_scan_crud(s: Session) -> None:
    org, acct, scan, _ = _scan_with_resource(s)
    assert org.hindsight_bank == f"org-{org.id}"
    acct.regions = ["us-east-1"]
    scan.status = "done"
    s.commit()
    s.expire_all()
    assert s.get(type(acct), acct.id).regions == ["us-east-1"]
    assert s.get(type(scan), scan.id).status == "done"


def test_resource_and_candidate_crud(s: Session) -> None:
    _, _, scan, res = _scan_with_resource(s)
    res.tags_json = {"team": "payments"}
    (c,) = repo.save_candidates(s, [CandidateRow(scan_id=scan.id, resource_id=res.id, rule_id="R1", action="stop",
                                                 monthly_saving=12.5)])
    c.status = CandidateStatus.approved
    s.commit()
    s.expire_all()
    assert s.get(ResourceRow, res.id).tags_json == {"team": "payments"}
    assert s.get(CandidateRow, c.id).status is CandidateStatus.approved


def test_verdict_action_user_audit_crud(s: Session) -> None:
    org, _, scan, res = _scan_with_resource(s)
    user = User(org_id=org.id, name="R", role=Role.reviewer)
    s.add(user)
    (c,) = repo.save_candidates(s, [CandidateRow(scan_id=scan.id, resource_id=res.id, rule_id="R1", action="stop")])
    v = repo.record_verdict(s, candidate_id=c.id, reviewer_id=user.id, decision=Decision.reject,
                            reason="DR standby", scope=Scope.similar)
    a = repo.record_action(s, candidate_id=c.id, kind="stop", api_calls_json=[{"op": "StopInstances"}])
    log = repo.log_audit(s, org.id, user.id, "verdict", {"id": v.id})
    v.reason = "DR standby, idle on purpose"
    a.status = "done"
    user.role = Role.admin
    s.commit()
    s.expire_all()
    assert s.get(Verdict, v.id).reason == "DR standby, idle on purpose"
    assert s.get(Verdict, v.id).scope is Scope.similar
    assert s.get(ActionRow, a.id).status == "done"
    assert s.get(User, user.id).role is Role.admin
    assert s.get(AuditLog, log.id).payload_json == {"id": v.id}


def test_list_candidates_filters_by_status(s: Session) -> None:
    _, _, scan, res = _scan_with_resource(s)
    repo.save_candidates(s, [
        CandidateRow(scan_id=scan.id, resource_id=res.id, rule_id="R1", action="stop"),
        CandidateRow(scan_id=scan.id, resource_id=res.id, rule_id="R2", action="rightsize",
                     status=CandidateStatus.suppressed),
    ])
    assert len(repo.list_candidates(s, scan.id)) == 2
    (only,) = repo.list_candidates(s, scan.id, CandidateStatus.suppressed)
    assert only.rule_id == "R2"


def test_seed_is_idempotent(s: Session) -> None:
    seed(s)
    seed(s)
    assert s.query(User).count() == 2
