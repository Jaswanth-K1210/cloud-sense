"""REST API (BUILD_DOC section 11), plus a few read endpoints the dashboard needs.

Auth is demo-grade: the X-User-Id header names a row in `users`. Replace with SSO before production.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import settings
from backend.deps import services
from backend.graph.blast_radius import blast_radius
from backend.memory.templates import TEMPLATES, seed_accepted
from backend.pipeline import run_scan
from backend.review.service import VerdictError, learn, submit_verdict
from backend.scanner.aws_session import assume_role
from backend.store import repo
from backend.store.db import get_session
from backend.store.models import (
    Account,
    ActionRow,
    AuditLog,
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

router = APIRouter()
DB = Annotated[Session, Depends(get_session)]


# ---------- auth ----------

def current_user(s: DB, x_user_id: Annotated[str | None, Header()] = None) -> User:
    user = s.get(User, x_user_id) if x_user_id else None
    if user is None:
        raise HTTPException(401, "unknown or missing X-User-Id")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def need(user: User, *roles: Role) -> None:
    if user.role not in roles:
        raise HTTPException(403, f"requires role {' or '.join(r.value for r in roles)}")


def org_for(s: Session, org_id: str, user: User) -> Org:
    org = s.get(Org, org_id)
    if org is None or user.org_id != org.id:  # never trust the path without the auth check
        raise HTTPException(404, "org not found")
    return org


def candidate_for(s: Session, cand_id: str, user: User) -> CandidateRow:
    cand = s.get(CandidateRow, cand_id)
    if cand is None or s.get(Scan, cand.scan_id).org_id != user.org_id:
        raise HTTPException(404, "candidate not found")
    return cand


# ---------- serializers ----------

def cand_json(c: CandidateRow, r: ResourceRow) -> dict[str, Any]:
    return {"id": c.id, "scan_id": c.scan_id, "rule_id": c.rule_id, "action": c.action,
            "monthly_saving": c.monthly_saving, "signals_text": c.signals_text, "blast_radius": c.blast_radius,
            "status": c.status.value, "agent": c.agent_decision_json, **c.extra_json,
            "resource": {"id": r.aws_id, "name": r.name, "type": r.type, "tags": r.tags_json,
                         "account": r.data_json.get("account_alias"),
                         "owner_team": r.owner_team, "role_hints": r.role_hints_json,
                         "iac_managed": r.data_json.get("iac_managed", False), "region": r.data_json.get("region")}}


def verdict_json(v: Verdict) -> dict[str, Any]:
    return {"id": v.id, "candidate_id": v.candidate_id, "reviewer_id": v.reviewer_id, "decision": v.decision.value,
            "reason": v.reason, "scope": v.scope.value, "until_date": v.until_date, "at": v.at,
            "learning_status": v.learning_status, "learned_rule": v.learned_rule_json or None}


# ---------- org, users, accounts ----------

@router.get("/orgs/{org_id}/users")
def list_users(org_id: str, s: DB) -> list[dict[str, Any]]:
    """Unauthenticated on purpose: feeds the demo user picker."""
    return [{"id": u.id, "name": u.name, "role": u.role.value}
            for u in s.scalars(select(User).where(User.org_id == org_id))]


@router.get("/orgs/{org_id}")
def get_org(org_id: str, s: DB, user: CurrentUser) -> dict[str, Any]:
    org = org_for(s, org_id, user)
    accounts = s.scalars(select(Account).where(Account.org_id == org.id))
    return {"id": org.id, "name": org.name, "hard_rules": org.hard_rules, "external_id": org.external_id,
            "principal_arn": settings.CLOUDSENSE_PRINCIPAL_ARN, "dry_run": settings.DRY_RUN,
            "accounts": [{"id": a.id, "alias": a.alias, "aws_account_id": a.aws_account_id, "role_arn": a.role_arn,
                          "regions": a.regions, "action_role_arn": a.action_role_arn} for a in accounts]}


class AccountIn(BaseModel):
    alias: str
    aws_account_id: str
    role_arn: str
    external_id: str | None = None
    regions: list[str] = Field(default_factory=lambda: ["us-east-1"])
    action_role_arn: str | None = None


@router.post("/orgs/{org_id}/accounts", status_code=201)
def connect_account(org_id: str, body: AccountIn, s: DB, user: CurrentUser) -> dict[str, Any]:
    org = org_for(s, org_id, user)
    need(user, Role.admin)
    external_id = body.external_id or org.external_id
    if body.role_arn != "local":
        try:
            assume_role(body.role_arn, external_id).client("sts").get_caller_identity()
        except Exception as e:
            raise HTTPException(400, f"cannot assume role with this ExternalId: {e}") from e
    acct = repo.add_account(s, org.id, **{**body.model_dump(), "external_id": external_id})
    repo.log_audit(s, org.id, user.id, "account_connected", {"alias": acct.alias})
    s.commit()
    return {"id": acct.id, "alias": acct.alias}


class HardRulesIn(BaseModel):
    rules: list[str]


@router.put("/orgs/{org_id}/hard_rules")
async def set_hard_rules(org_id: str, body: HardRulesIn, s: DB, user: CurrentUser) -> dict[str, Any]:
    org = org_for(s, org_id, user)
    need(user, Role.admin)
    org.hard_rules = [r.strip() for r in body.rules if r.strip()]
    repo.log_audit(s, org.id, user.id, "hard_rules_updated", {"rules": org.hard_rules})
    s.commit()
    await services.memory.ensure_bank(org)  # directives
    return {"hard_rules": org.hard_rules}


@router.get("/templates")
def list_templates() -> dict[str, str]:
    return TEMPLATES


class TemplatesIn(BaseModel):
    rule_ids: list[str]


@router.post("/orgs/{org_id}/templates")
async def accept_templates(org_id: str, body: TemplatesIn, s: DB, user: CurrentUser) -> dict[str, Any]:
    org = org_for(s, org_id, user)
    need(user, Role.admin)
    await services.memory.ensure_bank(org)
    accepted = await seed_accepted(services.memory, org, body.rule_ids)
    repo.log_audit(s, org.id, user.id, "templates_accepted", {"rule_ids": accepted})
    s.commit()
    return {"accepted": accepted}


# ---------- scans ----------

class ScanIn(BaseModel):
    account_ids: list[str] | None = None


@router.post("/orgs/{org_id}/scans", status_code=202)
def start_scan(org_id: str, s: DB, user: CurrentUser, bg: BackgroundTasks, body: ScanIn | None = None
               ) -> dict[str, str]:
    org = org_for(s, org_id, user)
    need(user, Role.reviewer, Role.admin)
    scan = repo.create_scan(s, org.id)
    s.commit()
    bg.add_task(run_scan, services, scan.id, body.account_ids if body else None)
    return {"scan_id": scan.id, "status": scan.status}


@router.get("/orgs/{org_id}/scans")
def list_scans(org_id: str, s: DB, user: CurrentUser) -> list[dict[str, Any]]:
    org = org_for(s, org_id, user)
    return [{"id": x.id, "status": x.status, "started_at": x.started_at, "finished_at": x.finished_at,
             "resource_count": x.resource_count, "candidate_count": x.candidate_count}
            for x in s.scalars(select(Scan).where(Scan.org_id == org.id).order_by(Scan.started_at.desc()))]


@router.get("/orgs/{org_id}/scans/{scan_id}")
def get_scan(org_id: str, scan_id: str, s: DB, user: CurrentUser) -> dict[str, Any]:
    org = org_for(s, org_id, user)
    scan = s.get(Scan, scan_id)
    if scan is None or scan.org_id != org.id:
        raise HTTPException(404, "scan not found")
    rows = s.execute(select(CandidateRow, ResourceRow).join(ResourceRow, CandidateRow.resource_id == ResourceRow.id)
                     .where(CandidateRow.scan_id == scan.id)).all()
    cands = [cand_json(c, r) for c, r in rows]
    return {"id": scan.id, "status": scan.status, "started_at": scan.started_at, "finished_at": scan.finished_at,
            "resource_count": scan.resource_count, "candidate_count": scan.candidate_count, "errors": scan.errors,
            "recommended": [c for c in cands if c["status"] == "pending"],
            "asked": [c for c in cands if c["status"] == "asked"],
            "suppressed": [c for c in cands if c["status"] == "suppressed"],
            "reviewed": [c for c in cands if c["status"] not in ("pending", "asked", "suppressed")]}


# ---------- verdicts ----------

class VerdictIn(BaseModel):
    decision: Decision
    reason: str = ""
    scope: Scope = Scope.this_resource
    until_date: datetime | None = None


@router.post("/candidates/{cand_id}/verdict", status_code=201)
async def post_verdict(cand_id: str, body: VerdictIn, s: DB, user: CurrentUser, bg: BackgroundTasks
                       ) -> dict[str, Any]:
    cand = candidate_for(s, cand_id, user)
    try:
        v = await submit_verdict(s, services, cand, user, body.decision, body.reason, body.scope, body.until_date)
    except VerdictError as e:
        raise HTTPException(403 if "reviewers" in str(e) else 400, str(e)) from e
    bg.add_task(learn, services, v.id)
    return verdict_json(v)


@router.get("/verdicts/{verdict_id}")
def get_verdict(verdict_id: str, s: DB, user: CurrentUser) -> dict[str, Any]:
    v = s.get(Verdict, verdict_id)
    if v is None:
        raise HTTPException(404, "verdict not found")
    candidate_for(s, v.candidate_id, user)
    return verdict_json(v)


@router.post("/candidates/{cand_id}/why")
async def why(cand_id: str, s: DB, user: CurrentUser) -> dict[str, Any]:
    cand = candidate_for(s, cand_id, user)
    res = s.get(ResourceRow, cand.resource_id)
    org = s.get(Org, user.org_id)
    ans = await services.memory.reflect(
        org, f"Why should or shouldn't we {cand.action} {res.name} ({res.type})? Cite past decisions.")
    return {"text": ans.text, "based_on": [h.model_dump() for h in ans.based_on],
            "agent": cand.agent_decision_json}


# ---------- actions ----------

@router.post("/candidates/{cand_id}/execute")
def execute_candidate(cand_id: str, s: DB, user: CurrentUser) -> dict[str, Any]:
    from backend.actions.executor import ExecutionError, action_json, execute

    cand = candidate_for(s, cand_id, user)
    need(user, Role.reviewer, Role.admin)
    try:
        return action_json(execute(s, cand, actor=user.id))
    except ExecutionError as e:
        raise HTTPException(409, str(e)) from e


@router.post("/actions/{action_id}/undo")
def undo_action(action_id: str, s: DB, user: CurrentUser) -> dict[str, Any]:
    from backend.actions.executor import ExecutionError, action_json
    from backend.actions.undo import undo

    act = s.get(ActionRow, action_id)
    if act is None:
        raise HTTPException(404, "action not found")
    candidate_for(s, act.candidate_id, user)
    need(user, Role.reviewer, Role.admin)
    try:
        return action_json(undo(s, act, actor=user.id))
    except ExecutionError as e:
        raise HTTPException(409, str(e)) from e


# ---------- memory ----------

@router.get("/orgs/{org_id}/rules")
async def rules(org_id: str, s: DB, user: CurrentUser) -> list[dict[str, Any]]:
    org = org_for(s, org_id, user)
    return [r.model_dump() for r in await services.memory.list_rules(org)]


@router.delete("/orgs/{org_id}/rules/{memory_id}", status_code=204)
async def delete_rule(org_id: str, memory_id: str, s: DB, user: CurrentUser) -> None:
    org = org_for(s, org_id, user)
    need(user, Role.admin)
    await services.memory.delete_rule(org, memory_id, reason=f"removed by admin {user.name}")
    repo.log_audit(s, org.id, user.id, "rule_deleted", {"memory_id": memory_id})
    s.commit()


@router.get("/orgs/{org_id}/playbook")
async def playbook(org_id: str, s: DB, user: CurrentUser) -> dict[str, Any]:
    org = org_for(s, org_id, user)
    current = await services.memory.get_playbook(org)
    history = await services.memory.playbook_history(org)
    return {"current": current.model_dump(), "history": [h.model_dump() for h in history]}


class AskIn(BaseModel):
    question: str


@router.post("/orgs/{org_id}/ask")
async def ask(org_id: str, body: AskIn, s: DB, user: CurrentUser) -> dict[str, Any]:
    org = org_for(s, org_id, user)
    ans = await services.memory.reflect(org, body.question)
    return ans.model_dump()


# ---------- activity ----------

@router.get("/orgs/{org_id}/activity")
def activity(org_id: str, s: DB, user: CurrentUser, limit: int = 200) -> list[dict[str, Any]]:
    org = org_for(s, org_id, user)
    names = {u.id: u.name for u in s.scalars(select(User).where(User.org_id == org.id))}
    rows = s.scalars(select(AuditLog).where(AuditLog.org_id == org.id).order_by(AuditLog.at.desc()).limit(limit))
    return [{"id": a.id, "at": a.at, "actor": names.get(a.actor, a.actor), "event": a.event, "details": a.payload_json}
            for a in rows]


# ---------- metrics + graph ----------

SHOWN = {CandidateStatus.pending, CandidateStatus.asked, CandidateStatus.approved, CandidateStatus.rejected,
         CandidateStatus.snoozed, CandidateStatus.executed}
APPROVED = {CandidateStatus.approved, CandidateStatus.executed}


@router.get("/orgs/{org_id}/metrics")
def metrics(org_id: str, s: DB, user: CurrentUser) -> dict[str, Any]:
    org = org_for(s, org_id, user)
    scans = list(s.scalars(select(Scan).where(Scan.org_id == org.id).order_by(Scan.started_at)))
    series, found, approved, executed = [], 0.0, 0.0, 0.0
    n_approved = n_executed = 0
    for scan in scans:
        cands = list(s.scalars(select(CandidateRow).where(CandidateRow.scan_id == scan.id)))
        n_app = sum(c.status in APPROVED for c in cands)
        n_rej = sum(c.status == CandidateStatus.rejected for c in cands)
        shown = sum(c.status in SHOWN for c in cands)
        learned = s.scalar(select(func.count()).select_from(Verdict).where(
            Verdict.candidate_id.in_([c.id for c in cands]), Verdict.learning_status == "learned",
            Verdict.decision == Decision.reject)) if cands else 0
        series.append({"scan_id": scan.id, "started_at": scan.started_at, "approved": n_app, "rejected": n_rej,
                       "shown": shown, "suppressed": sum(c.status == CandidateStatus.suppressed for c in cands),
                       "acceptance_rate": n_app / (n_app + n_rej) if n_app + n_rej else None,
                       "false_alarm_rate": n_rej / shown if shown else None,
                       "found": round(sum(c.monthly_saving or 0 for c in cands
                                          if c.status != CandidateStatus.suppressed), 2),
                       "rules_learned": learned})
        approved += sum(c.monthly_saving or 0 for c in cands if c.status in APPROVED)
        executed += sum(c.monthly_saving or 0 for c in cands if c.status == CandidateStatus.executed)
        n_approved += n_app
        n_executed += sum(c.status == CandidateStatus.executed for c in cands)
    if scans:
        last = s.scalars(select(CandidateRow).where(CandidateRow.scan_id == scans[-1].id))
        found = sum(c.monthly_saving or 0 for c in last if c.status != CandidateStatus.suppressed)
    return {"series": series, "savings": {"found": round(found, 2), "approved": round(approved, 2),
                                          "executed": round(executed, 2), "approved_count": n_approved,
                                          "executed_count": n_executed}}


@router.get("/graph/{scan_id}")
def graph(scan_id: str, s: DB, user: CurrentUser) -> dict[str, Any]:
    scan = s.get(Scan, scan_id)
    if scan is None or scan.org_id != user.org_id:
        raise HTTPException(404, "scan not found")
    rows = list(s.scalars(select(ResourceRow).where(ResourceRow.scan_id == scan_id)))
    cands = {c.resource_id: c for c in s.scalars(select(CandidateRow).where(CandidateRow.scan_id == scan_id))}
    g = {r.aws_id: list(r.dependents_json) for r in rows}
    nodes = []
    for r in rows:
        c = cands.get(r.id)
        br = blast_radius(g, r.aws_id)
        nodes.append({"id": r.aws_id, "type": r.type, "name": r.name, "status": c.status.value if c else None,
                      "candidate_id": c.id if c else None, "action": c.action if c else None,
                      "role_hints": r.role_hints_json, "blast_radius": {"count": len(br), "ids": br}})
    edges = [{"source": r.aws_id, "target": dep} for r in rows for dep in r.depends_on_json if dep in g]
    return {"nodes": nodes, "edges": edges}
