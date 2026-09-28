"""Verdict logic shared by the REST API and the Slack app."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from backend.candidates.rules import BlastRadius, Candidate
from backend.deps import Services
from backend.memory.fake import tokens
from backend.scanner.models import Resource
from backend.store import repo
from backend.store.models import (
    CandidateRow,
    CandidateStatus,
    Decision,
    Org,
    ResourceRow,
    Role,
    Scan,
    Scope,
    User,
    Verdict,
)

log = logging.getLogger(__name__)
SNOOZE_DAYS = 30
STATUS_FOR = {Decision.approve: CandidateStatus.approved, Decision.reject: CandidateStatus.rejected,
              Decision.snooze: CandidateStatus.snoozed}


class VerdictError(ValueError):
    pass


def candidate_model(row: CandidateRow, res_row: ResourceRow) -> Candidate:
    return Candidate(id=row.id, resource_id=res_row.aws_id, rule_id=row.rule_id, action=row.action,
                     monthly_saving=row.monthly_saving, signals_text=row.signals_text,
                     blast_radius=BlastRadius(**(row.blast_radius or {})),
                     reversible=row.extra_json.get("reversible", True), warnings=row.extra_json.get("warnings", []))


def resource_model(res_row: ResourceRow) -> Resource:
    return Resource.model_validate(res_row.data_json)


async def submit_verdict(s: Session, svc: Services, cand: CandidateRow, user: User, decision: Decision,
                         reason: str = "", scope: Scope = Scope.this_resource,
                         until_date: datetime | None = None) -> Verdict:
    if user.role not in (Role.reviewer, Role.admin):
        raise VerdictError("only reviewers and admins can submit verdicts")
    if decision == Decision.reject and not reason.strip():
        raise VerdictError("a reason is required to reject")
    if cand.status == CandidateStatus.executed:
        raise VerdictError("candidate already executed")
    if decision == Decision.snooze and until_date is None:
        until_date = datetime.now(UTC) + timedelta(days=SNOOZE_DAYS)

    verdict = repo.record_verdict(s, candidate_id=cand.id, reviewer_id=user.id, decision=decision,
                                  reason=reason.strip(), scope=scope, until_date=until_date)
    cand.status = STATUS_FOR[decision]
    scan = s.get(Scan, cand.scan_id)
    org = s.get(Org, scan.org_id)
    repo.log_audit(s, org.id, user.id, "verdict", {"candidate_id": cand.id, "decision": decision.value,
                                                   "reason": verdict.reason, "scope": scope.value})
    s.commit()

    res_row = s.get(ResourceRow, cand.resource_id)
    try:
        verdict.retained_op_id = await svc.memory.retain_verdict(
            org, scan.id, candidate_model(cand, res_row), resource_model(res_row), verdict, user)
    except Exception as e:  # never lose the verdict because memory is down
        log.warning("retain failed for verdict %s: %s", verdict.id, e)
        verdict.learning_status = "error"
    s.commit()
    return verdict


async def learn(svc: Services, verdict_id: str, timeout_s: float = 90) -> None:
    """Background: wait for consolidation, then record the best-matching learned rule on the verdict."""
    with svc.session_factory() as s:
        v = s.get(Verdict, verdict_id)
        if v is None or v.learning_status == "error":
            return
        org = s.get(Org, s.get(Scan, s.get(CandidateRow, v.candidate_id).scan_id).org_id)
        try:
            done = await svc.memory.wait_for_consolidation(org, timeout_s=timeout_s)
            v.learning_status = "learned" if done else "timeout"
            if done and v.reason:
                rules = await svc.memory.list_rules(org)
                want = tokens(v.reason)
                best = max(rules, key=lambda r: len(want & tokens(r.text)), default=None)
                if best and want & tokens(best.text):
                    v.learned_rule_json = {"id": best.id, "text": best.text, "proof_count": best.proof_count}
        except Exception as e:
            log.warning("learning status failed for %s: %s", verdict_id, e)
            v.learning_status = "error"
        s.commit()
