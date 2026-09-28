"""Memory-layer data shapes and the retain/recall formats (BUILD_DOC 5.3, 5.4).

Shared by the real Hindsight client and the in-memory fake so both speak the same format.
"""

from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from backend.candidates.rules import Candidate
from backend.scanner.models import Resource

VERDICT_CONTEXT = "engineer review of an AWS cost-optimization recommendation"
SEED_CONTEXT = "org policy seed"
PLAYBOOK_ID = "org-playbook"


class MemoryHit(BaseModel):
    id: str
    text: str
    type: str | None = None
    score: float | None = None


class Playbook(BaseModel):
    content: str = ""
    structured: dict[str, Any] | None = None
    last_refreshed_at: str | None = None


class PlaybookVersion(BaseModel):
    content: str
    changed_at: str | None = None


class ReflectAnswer(BaseModel):
    text: str
    based_on: list[MemoryHit] = Field(default_factory=list)


class Rule(BaseModel):
    """A learned rule = a Hindsight observation, with provenance."""

    id: str
    text: str
    proof_count: int = 1
    tags: list[str] = Field(default_factory=list)
    sources: list[MemoryHit] = Field(default_factory=list)
    updated_at: str | None = None


class OrgLike(Protocol):
    id: str
    name: str


class VerdictLike(Protocol):
    decision: Any
    reason: str
    scope: Any
    at: datetime | None


class ReviewerLike(Protocol):
    id: str
    name: str


def bank_id(org: Any) -> str:
    return getattr(org, "hindsight_bank", None) or f"org-{org.id}"


def _val(x: Any) -> str:
    return str(getattr(x, "value", x))


def verdict_content(scan_id: str, cand: Candidate, res: Resource, verdict: Any, reviewer: Any) -> str:
    at = verdict.at or datetime.now(UTC)
    team = getattr(reviewer, "team", None) or _val(getattr(reviewer, "role", "reviewer"))
    return (
        f"Reviewer {reviewer.name} ({team}) at {at.isoformat()}:\n"
        f"CloudSense proposed: {cand.action} on {res.display_name} ({res.id}, "
        f"{res.type}, account {res.account_alias}).\n"
        f"Signals: {cand.signals_text}. Estimated saving ${cand.monthly_saving or 0:.0f}/month.\n"
        f"Dependencies: {', '.join(res.depends_on_names) or 'none'}; "
        f"dependents: {', '.join(res.dependent_names) or 'none'}.\n"
        f"Verdict: {_val(verdict.decision).upper()}. Reason: {verdict.reason}\n"
        f"Scope stated by reviewer: {_val(verdict.scope)}"
    )


def verdict_tags(res: Resource) -> list[str]:
    return [f"account:{res.account_alias}", f"team:{res.owner_team}", f"rtype:{res.type}"]


def verdict_item(scan_id: str, cand: Candidate, res: Resource, verdict: Any, reviewer: Any) -> dict[str, Any]:
    """One retain_batch item. observation_scopes: org-wide ([] = untagged), per-account, per-team."""
    at = verdict.at or datetime.now(UTC)
    return {
        "content": verdict_content(scan_id, cand, res, verdict, reviewer),
        "context": VERDICT_CONTEXT,
        "timestamp": at,
        "tags": verdict_tags(res),
        "metadata": {"candidate_id": cand.id, "resource_id": res.id, "decision": _val(verdict.decision),
                     "reviewer_id": str(reviewer.id), "scan_id": scan_id},
        "entities": [{"text": res.display_name},
                     *[{"text": n} for n in res.depends_on_names + res.dependent_names],
                     *([{"text": res.service}] if res.service else [])],
        "observation_scopes": [[], [f"account:{res.account_alias}"], [f"team:{res.owner_team}"]],
    }


def verdict_document_id(cand: Candidate) -> str:
    return f"verdict-{cand.id}"


def recall_query(cand: Candidate, res: Resource) -> str:
    return (f"{cand.action} {res.type} {res.display_name}; role hints: {res.role_hints}; "
            f"signals: {cand.signals_text}; connected to: {', '.join(res.neighbor_names)}")


class MemoryClientProtocol(Protocol):
    async def ensure_bank(self, org: Any) -> None: ...
    async def retain_verdict(self, org: Any, scan_id: str, cand: Candidate, res: Resource, verdict: Any,
                             reviewer: Any) -> str | None: ...
    async def retain_seed(self, org: Any, text: str, doc_id: str) -> None: ...
    async def recall_for(self, org: Any, cand: Candidate, res: Resource) -> list[MemoryHit]: ...
    async def recall_many(self, org: Any, items: list[tuple[Candidate, Resource]],
                          concurrency: int = 8) -> list[list[MemoryHit]]: ...
    async def get_playbook(self, org: Any) -> Playbook: ...
    async def playbook_history(self, org: Any) -> list[PlaybookVersion]: ...
    async def reflect(self, org: Any, question: str) -> ReflectAnswer: ...
    async def list_rules(self, org: Any) -> list[Rule]: ...
    async def delete_rule(self, org: Any, memory_id: str, reason: str = "removed by admin") -> None: ...
    async def wait_for_consolidation(self, org: Any, timeout_s: float = 90) -> bool: ...
