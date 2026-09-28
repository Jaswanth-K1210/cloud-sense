"""SQLAlchemy 2.0 tables (BUILD_DOC section 10)."""

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON, datetime: DateTime(timezone=True)}


class CandidateStatus(enum.StrEnum):
    pending = "pending"
    suppressed = "suppressed"
    asked = "asked"
    approved = "approved"
    rejected = "rejected"
    snoozed = "snoozed"
    executed = "executed"


class Decision(enum.StrEnum):
    approve = "approve"
    reject = "reject"
    snooze = "snooze"


class Scope(enum.StrEnum):
    this_resource = "this_resource"
    similar = "similar"
    team = "team"


class Role(enum.StrEnum):
    viewer = "viewer"
    reviewer = "reviewer"
    admin = "admin"


class Org(Base):
    __tablename__ = "orgs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    hindsight_bank: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    alias: Mapped[str] = mapped_column(String(200))
    aws_account_id: Mapped[str] = mapped_column(String(32))
    role_arn: Mapped[str] = mapped_column(String(300))
    external_id: Mapped[str] = mapped_column(String(100))
    regions: Mapped[list[Any]] = mapped_column(default=list)
    action_role_arn: Mapped[str | None] = mapped_column(String(300), default=None)


class Scan(Base):
    __tablename__ = "scans"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(20), default="running")
    resource_count: Mapped[int] = mapped_column(Integer, default=0)
    candidate_count: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list[Any]] = mapped_column(default=list)


class ResourceRow(Base):
    __tablename__ = "resources"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id"), index=True)
    account_id: Mapped[str | None] = mapped_column(ForeignKey("accounts.id"), default=None)
    aws_id: Mapped[str] = mapped_column(String(200))  # e.g. i-0abc; same across scans
    arn: Mapped[str] = mapped_column(String(400), default="")
    type: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(300), default="")
    tags_json: Mapped[dict[str, Any]] = mapped_column(default=dict)
    owner_team: Mapped[str | None] = mapped_column(String(100), default=None)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(default=dict)
    role_hints_json: Mapped[list[Any]] = mapped_column(default=list)
    depends_on_json: Mapped[list[Any]] = mapped_column(default=list)
    dependents_json: Mapped[list[Any]] = mapped_column(default=list)
    data_json: Mapped[dict[str, Any]] = mapped_column(default=dict)  # full Resource model dump


class CandidateRow(Base):
    __tablename__ = "candidates"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scans.id"), index=True)
    resource_id: Mapped[str] = mapped_column(ForeignKey("resources.id"))
    rule_id: Mapped[str] = mapped_column(String(10))
    action: Mapped[str] = mapped_column(String(40))
    monthly_saving: Mapped[float | None] = mapped_column(Float, default=None)
    signals_text: Mapped[str] = mapped_column(Text, default="")
    blast_radius: Mapped[dict[str, Any]] = mapped_column(default=dict)
    agent_decision_json: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[CandidateStatus] = mapped_column(Enum(CandidateStatus), default=CandidateStatus.pending)


class Verdict(Base):
    __tablename__ = "verdicts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"), index=True)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[Decision] = mapped_column(Enum(Decision))
    reason: Mapped[str] = mapped_column(Text, default="")
    scope: Mapped[Scope] = mapped_column(Enum(Scope), default=Scope.this_resource)
    until_date: Mapped[datetime | None] = mapped_column(default=None)
    at: Mapped[datetime] = mapped_column(default=utcnow)
    retained_op_id: Mapped[str | None] = mapped_column(String(200), default=None)


class ActionRow(Base):
    __tablename__ = "actions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id"))
    kind: Mapped[str] = mapped_column(String(40))
    api_calls_json: Mapped[list[Any]] = mapped_column(default=list)
    pre_snapshot_ids: Mapped[list[Any]] = mapped_column(default=list)
    status: Mapped[str] = mapped_column(String(20), default="planned")
    undo_handle: Mapped[dict[str, Any]] = mapped_column(default=dict)
    at: Mapped[datetime] = mapped_column(default=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(300), default="")
    slack_id: Mapped[str | None] = mapped_column(String(50), default=None, index=True)
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.viewer)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    actor: Mapped[str] = mapped_column(String(200))
    event: Mapped[str] = mapped_column(String(100))
    payload_json: Mapped[dict[str, Any]] = mapped_column(default=dict)
    at: Mapped[datetime] = mapped_column(default=utcnow)
