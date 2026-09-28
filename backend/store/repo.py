"""Small data-access functions. Callers own the session and commit."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.store.models import (
    Account,
    ActionRow,
    AuditLog,
    CandidateRow,
    CandidateStatus,
    Org,
    ResourceRow,
    Scan,
    Verdict,
)


def create_org(s: Session, name: str, org_id: str | None = None) -> Org:
    org = Org(name=name, hindsight_bank="")
    if org_id:
        org.id = org_id
    s.add(org)
    s.flush()
    org.hindsight_bank = f"org-{org.id}"
    return org


def add_account(s: Session, org_id: str, **fields: Any) -> Account:
    acct = Account(org_id=org_id, **fields)
    s.add(acct)
    s.flush()
    return acct


def create_scan(s: Session, org_id: str) -> Scan:
    scan = Scan(org_id=org_id)
    s.add(scan)
    s.flush()
    return scan


def save_resources(s: Session, rows: list[ResourceRow]) -> list[ResourceRow]:
    s.add_all(rows)
    s.flush()
    return rows


def save_candidates(s: Session, rows: list[CandidateRow]) -> list[CandidateRow]:
    s.add_all(rows)
    s.flush()
    return rows


def record_verdict(s: Session, **fields: Any) -> Verdict:
    v = Verdict(**fields)
    s.add(v)
    s.flush()
    return v


def record_action(s: Session, **fields: Any) -> ActionRow:
    a = ActionRow(**fields)
    s.add(a)
    s.flush()
    return a


def log_audit(s: Session, org_id: str, actor: str, event: str, payload: dict[str, Any] | None = None) -> AuditLog:
    entry = AuditLog(org_id=org_id, actor=actor, event=event, payload_json=payload or {})
    s.add(entry)
    s.flush()
    return entry


def list_candidates(s: Session, scan_id: str, status: CandidateStatus | None = None) -> list[CandidateRow]:
    q = select(CandidateRow).where(CandidateRow.scan_id == scan_id)
    if status is not None:
        q = q.where(CandidateRow.status == status)
    return list(s.scalars(q))
