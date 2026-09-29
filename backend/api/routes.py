"""REST API (BUILD_DOC section 11), plus auth, onboarding and the read endpoints the dashboard needs.

Auth: email + password, bearer-token sessions (backend/auth.py). X-User-Id is accepted only when
ALLOW_USER_HEADER is set (tests and simulations).
"""

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend import auth
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
log = logging.getLogger(__name__)
DB = Annotated[Session, Depends(get_session)]


# ---------- auth ----------

def bearer(authorization: Annotated[str | None, Header()] = None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def current_user(s: DB, token: Annotated[str | None, Depends(bearer)],
                 x_user_id: Annotated[str | None, Header()] = None) -> User:
    user = auth.user_for_token(s, token) if token else None
    if user is None and x_user_id and settings.ALLOW_USER_HEADER:
        user = s.get(User, x_user_id)
    if user is None:
        raise HTTPException(401, "Please log in.")
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
                         "iac_managed": r.data_json.get("iac_managed", False), "region": r.data_json.get("region"),
                         "instance_type": r.data_json.get("instance_type") or r.data_json.get("volume_type"),
                         "size_gb": r.data_json.get("size_gb"), "created_at": r.data_json.get("created_at"),
                         "metrics": r.data_json.get("metrics") or {}, "state": r.data_json.get("state")}}


def verdict_json(v: Verdict) -> dict[str, Any]:
    return {"id": v.id, "candidate_id": v.candidate_id, "reviewer_id": v.reviewer_id, "decision": v.decision.value,
            "reason": v.reason, "scope": v.scope.value, "until_date": v.until_date, "at": v.at,
            "learning_status": v.learning_status, "learned_rule": v.learned_rule_json or None}


# ---------- auth + profile ----------

EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(pattern=EMAIL_RE, max_length=300)
    password: str = Field(min_length=auth.MIN_PASSWORD, max_length=200)


class LoginIn(BaseModel):
    email: str
    password: str


def _company_from_email(email: str) -> str:
    domain = email.split("@")[1].split(".")[0]
    return domain.capitalize() if domain not in ("gmail", "outlook", "yahoo", "hotmail", "icloud") else "My workspace"


def me_json(s: Session, user: User) -> dict[str, Any]:
    org = s.get(Org, user.org_id)
    return {"user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role.value,
                     "slack_id": user.slack_id},
            "org": {"id": org.id, "name": org.name, "settings": org.settings_json or {}}}


@router.post("/auth/signup", status_code=201)
def signup(body: SignupIn, s: DB) -> dict[str, Any]:
    email = body.email.strip().lower()
    if s.scalars(select(User).where(func.lower(User.email) == email)).first():
        raise HTTPException(409, "An account with this email already exists. Log in instead.")
    org = repo.create_org(s, _company_from_email(email))
    org.settings_json = {"onboarding_step": 1}
    user = User(org_id=org.id, name=body.name.strip(), email=email, role=Role.admin,
                password_hash=auth.hash_password(body.password))
    s.add(user)
    s.flush()
    repo.log_audit(s, org.id, user.id, "signed_up", {"email": email})
    token = auth.new_session(s, user)
    s.commit()
    return {"token": token, **me_json(s, user)}


@router.post("/auth/login")
def login(body: LoginIn, s: DB) -> dict[str, Any]:
    user = s.scalars(select(User).where(func.lower(User.email) == body.email.strip().lower())).first()
    if user is None or not auth.check_password(body.password, user.password_hash):
        raise HTTPException(401, "Email or password is incorrect.")
    token = auth.new_session(s, user)
    s.commit()
    return {"token": token, **me_json(s, user)}


@router.post("/auth/logout", status_code=204)
def logout(s: DB, token: Annotated[str | None, Depends(bearer)]) -> None:
    if token:
        auth.end_session(s, token)
        s.commit()


@router.get("/auth/me")
def me(s: DB, user: CurrentUser) -> dict[str, Any]:
    return me_json(s, user)


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(pattern=EMAIL_RE, max_length=300)


@router.put("/me")
def update_profile(body: ProfileIn, s: DB, user: CurrentUser) -> dict[str, Any]:
    email = body.email.strip().lower()
    clash = s.scalars(select(User).where(func.lower(User.email) == email, User.id != user.id)).first()
    if clash:
        raise HTTPException(409, "Another account already uses this email.")
    user.name, user.email = body.name.strip(), email
    s.commit()
    return me_json(s, user)


class PasswordIn(BaseModel):
    current: str
    new: str = Field(min_length=auth.MIN_PASSWORD, max_length=200)


@router.post("/me/password", status_code=204)
def change_password(body: PasswordIn, s: DB, user: CurrentUser,
                    token: Annotated[str | None, Depends(bearer)]) -> None:
    if not auth.check_password(body.current, user.password_hash):
        raise HTTPException(400, "Your current password is incorrect.")
    user.password_hash = auth.hash_password(body.new)
    auth.end_all_sessions(s, user, keep=token)  # sign out other devices
    repo.log_audit(s, user.org_id, user.id, "password_changed", {})
    s.commit()


# ---------- org, team, accounts ----------

@router.get("/orgs/{org_id}/users")
def list_users(org_id: str, s: DB, user: CurrentUser) -> list[dict[str, Any]]:
    org = org_for(s, org_id, user)
    return [{"id": u.id, "name": u.name, "email": u.email, "role": u.role.value, "slack_id": u.slack_id}
            for u in s.scalars(select(User).where(User.org_id == org.id).order_by(User.name))]


class MemberIn(BaseModel):
    role: Role | None = None
    slack_id: str | None = None


@router.patch("/orgs/{org_id}/users/{user_id}")
def update_member(org_id: str, user_id: str, body: MemberIn, s: DB, user: CurrentUser) -> dict[str, Any]:
    org = org_for(s, org_id, user)
    need(user, Role.admin)
    member = s.get(User, user_id)
    if member is None or member.org_id != org.id:
        raise HTTPException(404, "member not found")
    if body.role is not None:
        if member.id == user.id and body.role != Role.admin:
            raise HTTPException(400, "You can't remove your own admin role.")
        member.role = body.role
    if body.slack_id is not None:
        member.slack_id = body.slack_id.strip() or None
    repo.log_audit(s, org.id, user.id, "member_updated", {"member": member.name, **body.model_dump(mode="json",
                                                                                                   exclude_none=True)})
    s.commit()
    return {"id": member.id, "role": member.role.value, "slack_id": member.slack_id}


def effective_dry_run(org: Org) -> bool:
    return (org.settings_json or {}).get("safety", {}).get("dry_run", settings.DRY_RUN)


@router.get("/orgs/{org_id}")
def get_org(org_id: str, s: DB, user: CurrentUser) -> dict[str, Any]:
    org = org_for(s, org_id, user)
    accounts = s.scalars(select(Account).where(Account.org_id == org.id))
    return {"id": org.id, "name": org.name, "hard_rules": org.hard_rules, "external_id": org.external_id,
            "principal_arn": settings.CLOUDSENSE_PRINCIPAL_ARN, "dry_run": effective_dry_run(org),
            "settings": org.settings_json or {},
            "accounts": [{"id": a.id, "alias": a.alias, "aws_account_id": a.aws_account_id, "role_arn": a.role_arn,
                          "regions": a.regions, "action_role_arn": a.action_role_arn} for a in accounts]}


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: str | None = None
    team_size: str | None = None
    spend: str | None = None


@router.put("/orgs/{org_id}/workspace")
async def update_workspace(org_id: str, body: WorkspaceIn, s: DB, user: CurrentUser) -> dict[str, Any]:
    """Company details (onboarding step 1 and Settings). Also creates the org's private memory bank."""
    org = org_for(s, org_id, user)
    need(user, Role.admin)
    org.name = body.name.strip()
    org.settings_json = {**(org.settings_json or {}), "profile": body.model_dump(exclude={"name"})}
    repo.log_audit(s, org.id, user.id, "workspace_updated", {"name": org.name})
    s.commit()
    memory_ready = True
    try:
        await services.memory.ensure_bank(org)
    except Exception as e:  # memory can be set up later; never block onboarding
        log.warning("ensure_bank failed for %s: %s", org.id, e)
        memory_ready = False
    return {"name": org.name, "settings": org.settings_json, "memory_ready": memory_ready}


SETTING_KEYS = {"services", "schedule", "slack", "safety", "onboarding_step", "onboarded"}


@router.put("/orgs/{org_id}/settings")
def update_settings(org_id: str, body: dict[str, Any], s: DB, user: CurrentUser) -> dict[str, Any]:
    org = org_for(s, org_id, user)
    need(user, Role.admin)
    unknown = set(body) - SETTING_KEYS
    if unknown:
        raise HTTPException(400, f"unknown settings: {', '.join(sorted(unknown))}")
    org.settings_json = {**(org.settings_json or {}), **body}
    if set(body) - {"onboarding_step"}:
        repo.log_audit(s, org.id, user.id, "settings_updated", body)
    s.commit()
    return {"settings": org.settings_json, "dry_run": effective_dry_run(org)}


class AccountIn(BaseModel):
    alias: str
    aws_account_id: str = ""
    role_arn: str
    external_id: str | None = None
    regions: list[str] | None = None
    action_role_arn: str | None = None


def explain_aws_error(e: Exception) -> str:
    """Turn an AWS error into the exact fix (UI_WORKFLOW step 2)."""
    code = getattr(e, "response", {}).get("Error", {}).get("Code", "") if hasattr(e, "response") else ""
    msg = str(e)
    if code == "AccessDenied" and "AssumeRole" in msg:
        return ("The role's trust policy doesn't include your External ID (or CloudSense's principal). "
                "Fix: re-run Launch Stack from this page, or add the External ID to the role's trust policy.")
    if code in ("NoSuchEntity", "InvalidClientTokenId") or "does not exist" in msg:
        return "Role not found. Check the Role ARN from the stack's Outputs tab."
    if code in ("UnauthorizedOperation", "AccessDenied", "AccessDeniedException"):
        op = msg.split("perform: ")[-1].split(" ")[0] if "perform: " in msg else "a describe call"
        return f"Missing permission {op}. Fix: update the stack to the latest CloudSense template."
    if "Unable to locate credentials" in msg or "NoCredentials" in type(e).__name__:
        return "CloudSense itself has no AWS credentials to assume your role. Set them on the server first."
    return f"AWS said: {msg}"


def probe_regions(session: Any) -> tuple[str, dict[str, int]]:
    """Account id + resource counts per region (EC2 instances + EBS volumes), in parallel."""
    from concurrent.futures import ThreadPoolExecutor

    account_id = session.client("sts").get_caller_identity()["Account"]
    session.client("ec2", region_name="us-east-1").describe_instances(MaxResults=5)  # permission check
    regions = [r["RegionName"] for r in session.client("ec2", region_name="us-east-1").describe_regions()["Regions"]]

    def count(region: str) -> tuple[str, int]:
        try:
            ec2 = session.client("ec2", region_name=region)
            n = sum(len(r["Instances"]) for r in ec2.describe_instances(MaxResults=50)["Reservations"])
            return region, n + len(ec2.describe_volumes(MaxResults=50)["Volumes"])
        except Exception:
            return region, 0

    with ThreadPoolExecutor(max_workers=16) as pool:
        found = dict(pool.map(count, regions))
    return account_id, {r: n for r, n in found.items() if n}


@router.post("/orgs/{org_id}/accounts", status_code=201)
def connect_account(org_id: str, body: AccountIn, s: DB, user: CurrentUser) -> dict[str, Any]:
    org = org_for(s, org_id, user)
    need(user, Role.admin)
    external_id = body.external_id or org.external_id
    aws_account_id, found = body.aws_account_id, {}
    if settings.APP_ENV != "offline":  # offline mode scans the eval accounts, not AWS
        try:  # role_arn "local" = this server's own AWS credentials (developer setup)
            aws_account_id, found = probe_regions(assume_role(body.role_arn, external_id))
        except Exception as e:
            raise HTTPException(400, explain_aws_error(e)) from e
    regions = body.regions or sorted(found, key=lambda r: -found[r]) or ["us-east-1"]
    acct = repo.add_account(s, org.id, alias=body.alias,
                            aws_account_id=aws_account_id or ("local" if body.role_arn == "local" else "unknown"),
                            role_arn=body.role_arn, external_id=external_id, regions=regions,
                            action_role_arn=body.action_role_arn)
    repo.log_audit(s, org.id, user.id, "account_connected", {"alias": acct.alias})
    s.commit()
    return {"id": acct.id, "alias": acct.alias, "aws_account_id": acct.aws_account_id, "regions": acct.regions,
            "resources_by_region": found, "resource_count": sum(found.values())}


class AccountPatch(BaseModel):
    alias: str | None = None
    regions: list[str] | None = None
    action_role_arn: str | None = None


@router.patch("/accounts/{account_id}")
def update_account(account_id: str, body: AccountPatch, s: DB, user: CurrentUser) -> dict[str, Any]:
    acct = s.get(Account, account_id)
    if acct is None or acct.org_id != user.org_id:
        raise HTTPException(404, "account not found")
    need(user, Role.admin)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(acct, k, v)
    repo.log_audit(s, acct.org_id, user.id, "account_updated", {"alias": acct.alias})
    s.commit()
    return {"id": acct.id, "alias": acct.alias, "regions": acct.regions, "action_role_arn": acct.action_role_arn}


@router.delete("/accounts/{account_id}", status_code=204)
def remove_account(account_id: str, s: DB, user: CurrentUser) -> None:
    acct = s.get(Account, account_id)
    if acct is None or acct.org_id != user.org_id:
        raise HTTPException(404, "account not found")
    need(user, Role.admin)
    if s.scalars(select(ResourceRow).where(ResourceRow.account_id == acct.id)).first():
        raise HTTPException(409, "This account already has scan history; it can't be removed.")
    s.delete(acct)
    repo.log_audit(s, user.org_id, user.id, "account_removed", {"alias": acct.alias})
    s.commit()


@router.get("/slack/status")
def slack_status(user: CurrentUser) -> dict[str, Any]:
    """Whether the server has a Slack bot token, and which workspace it belongs to (tokens are never returned)."""
    if not settings.SLACK_BOT_TOKEN:
        return {"connected": False, "reason": "SLACK_BOT_TOKEN is not set on the server."}
    try:
        from slack_sdk import WebClient

        r = WebClient(token=settings.SLACK_BOT_TOKEN).auth_test()
        return {"connected": True, "team": r.get("team"), "url": r.get("url"), "bot": r.get("user"),
                "socket_mode": bool(settings.SLACK_APP_TOKEN), "listening": "slack_socket" in services.extra}
    except Exception as e:
        return {"connected": False, "reason": f"Slack rejected the token: {e}"}


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
    repo.log_audit(s, org.id, user.id, "scan_started", {"scan_id": scan.id, "trigger": "manual"})
    s.commit()
    bg.add_task(run_scan, services, scan.id, body.account_ids if body else None)
    return {"scan_id": scan.id, "status": scan.status}


@router.get("/orgs/{org_id}/scans")
def list_scans(org_id: str, s: DB, user: CurrentUser) -> list[dict[str, Any]]:
    org = org_for(s, org_id, user)
    return [{"id": x.id, "status": x.status, "started_at": x.started_at, "finished_at": x.finished_at,
             "resource_count": x.resource_count, "candidate_count": x.candidate_count, "progress": x.progress or {}}
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
            "progress": scan.progress or {},
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


STEP_TEXT = {
    "CreateSnapshot": lambda p: f"Create snapshot of {p.get('VolumeId')}",
    "StopInstances": lambda p: f"Stop instance {', '.join(p.get('InstanceIds', []))}",
    "StartInstances": lambda p: f"Start instance {', '.join(p.get('InstanceIds', []))}",
    "CreateTags": lambda p: "Tag " + ", ".join(f"{t['Key']}={t['Value']}" for t in p.get("Tags", [])),
    "ModifyInstanceAttribute": lambda p: f"Change instance type to {p.get('InstanceType', {}).get('Value')}",
    "ModifyVolume": lambda p: f"Change volume {p.get('VolumeId')} to {p.get('VolumeType')}",
    "DeleteVolume": lambda p: f"Delete volume {p.get('VolumeId')}",
    "CreateDBSnapshot": lambda p: f"Create database snapshot {p.get('DBSnapshotIdentifier')}",
    "StopDBInstance": lambda p: f"Stop database {p.get('DBInstanceIdentifier')}",
    "AddTagsToResource": lambda p: "Tag " + ", ".join(f"{t['Key']}={t['Value']}" for t in p.get("Tags", [])),
}
UNDO_TEXT = {"stop_ec2": "Start the instance (snapshots are kept)",
             "rightsize_ec2": "Change back to the old instance type",
             "delete_ebs": "Restore the volume from its snapshot", "stop_rds": "Start the database",
             "modify_gp3": "Not needed: gp3 matches gp2 performance"}


def step_text(call: dict[str, Any]) -> str:
    fn = STEP_TEXT.get(call["op"])
    return fn(call["params"]) if fn else call["op"]


@router.get("/candidates/{cand_id}")
def candidate_detail(cand_id: str, s: DB, user: CurrentUser) -> dict[str, Any]:
    """Everything the Execute screen needs: the candidate, the resource, and the exact plan."""
    from backend.actions.executor import ExecutionError, action_json, plan
    from backend.actions.iac import terraform_diff
    from backend.scanner.models import Resource

    cand = candidate_for(s, cand_id, user)
    row = s.get(ResourceRow, cand.resource_id)
    res = Resource.model_validate(row.data_json)
    actor = user.name.split()[0].lower() if user.name else user.id
    plan_json: dict[str, Any]
    if res.iac_managed:
        plan_json = {"kind": "iac_diff", "steps": [], "terraform_diff": terraform_diff(cand.action, res),
                     "undo": "Revert the pull request"}
    else:
        try:
            kind, calls = plan(cand, res, actor)
            plan_json = {"kind": kind, "undo": UNDO_TEXT.get(kind, ""), "steps": [
                {"service": c["service"], "op": c["op"], "text": step_text(c)} for c in calls]}
        except ExecutionError as e:
            plan_json = {"kind": None, "steps": [], "error": str(e)}
    actions = s.scalars(select(ActionRow).where(ActionRow.candidate_id == cand.id).order_by(ActionRow.at.desc()))
    return {"candidate": cand_json(cand, row), "resource": row.data_json, "plan": plan_json,
            "actions": [action_json(a) for a in actions]}


@router.post("/candidates/{cand_id}/override")
def override_skip(cand_id: str, s: DB, user: CurrentUser) -> dict[str, Any]:
    """Recommend a skipped candidate anyway."""
    cand = candidate_for(s, cand_id, user)
    need(user, Role.reviewer, Role.admin)
    if cand.status != CandidateStatus.suppressed:
        raise HTTPException(409, "Only skipped recommendations can be overridden.")
    cand.status = CandidateStatus.pending
    repo.log_audit(s, user.org_id, user.id, "override", {"candidate_id": cand.id,
                                                          "resource": s.get(ResourceRow, cand.resource_id).name})
    s.commit()
    return cand_json(cand, s.get(ResourceRow, cand.resource_id))


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
    org = s.get(Org, user.org_id)
    if (org.settings_json or {}).get("safety", {}).get("mode") == "recommend":
        raise HTTPException(409, "This workspace is in Recommend-only mode. Switch to Safe actions in Settings.")
    try:
        return action_json(execute(s, cand, actor=user.id, dry_run=effective_dry_run(org)))
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
    learned = await services.memory.list_rules(org)
    recent_scans = [x.id for x in s.scalars(select(Scan).where(Scan.org_id == org.id)
                                            .order_by(Scan.started_at.desc()).limit(20))]
    skipped = s.execute(select(CandidateRow, ResourceRow, Scan.started_at)
                        .join(ResourceRow, CandidateRow.resource_id == ResourceRow.id)
                        .join(Scan, CandidateRow.scan_id == Scan.id)
                        .where(CandidateRow.scan_id.in_(recent_scans),
                               CandidateRow.status == CandidateStatus.suppressed)).all()
    seeds = [t[:40].lower() for t in TEMPLATES.values()]
    out = []
    for r in learned:
        ids = {r.id, *(x.id for x in r.sources)}
        hits = [(res.name, at) for c, res, at in skipped
                if ids & set((c.agent_decision_json or {}).get("cited_memory_ids", []))]
        starter = "seed" in r.tags or any(seed in (x.text or "").lower() or seed in r.text.lower()
                                          for x in r.sources for seed in seeds)
        out.append({**r.model_dump(), "starter": starter, "protected": sorted({n for n, _ in hits}),
                    "last_used": max((at for _, at in hits), default=None)})
    return out


class ReportIn(BaseModel):
    reason: str = ""


@router.post("/orgs/{org_id}/rules/{memory_id}/report", status_code=204)
def report_rule(org_id: str, memory_id: str, body: ReportIn, s: DB, user: CurrentUser) -> None:
    """Flag a learned rule as wrong so an admin can review it (Activity shows the report)."""
    org = org_for(s, org_id, user)
    repo.log_audit(s, org.id, user.id, "rule_reported", {"memory_id": memory_id, "reason": body.reason})
    s.commit()


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


@router.post("/orgs/{org_id}/slack/test")
def slack_test(org_id: str, s: DB, user: CurrentUser) -> dict[str, Any]:
    """Post a test message to the workspace's review channel."""
    from backend.review.slack_app import send_test_message

    org = org_for(s, org_id, user)
    need(user, Role.admin)
    if not settings.SLACK_BOT_TOKEN:
        raise HTTPException(400, "SLACK_BOT_TOKEN is not set on the server.")
    channel = ((org.settings_json or {}).get("slack") or {}).get("channel") or settings.SLACK_REVIEW_CHANNEL
    ok, message = send_test_message(channel)
    if not ok:
        raise HTTPException(400, message)
    return {"ok": True, "message": message}


# ---------- activity ----------

@router.get("/orgs/{org_id}/activity")
def activity(org_id: str, s: DB, user: CurrentUser, limit: int = 200) -> list[dict[str, Any]]:
    org = org_for(s, org_id, user)
    names = {u.id: u.name for u in s.scalars(select(User).where(User.org_id == org.id))} | {"cloudsense": "CloudSense"}
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
