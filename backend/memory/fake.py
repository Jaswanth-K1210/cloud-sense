"""In-memory stand-in for MemoryClient. Used by every test and by `run_eval --fake`.

Recall = keyword overlap. "Observations" = rejection reasons grouped by normalized text, with counts.
"""

import asyncio
import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from backend.candidates.rules import Candidate
from backend.memory.types import (
    MemoryHit,
    Playbook,
    PlaybookVersion,
    ReflectAnswer,
    Rule,
    bank_id,
    recall_query,
    verdict_document_id,
    verdict_item,
)
from backend.scanner.models import Resource

STOP = {"the", "a", "an", "of", "on", "for", "and", "to", "is", "it", "in", "this", "that", "by", "with", "none",
        "at", "s", "i", "we", "our"}
TOP_K = 5


def tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP and len(t) > 1}


def _norm(reason: str) -> str:
    return " ".join(sorted(tokens(reason)))


@dataclass
class _Mem:
    id: str
    text: str
    reason: str
    decision: str
    tags: list[str]
    valid: bool = True


@dataclass
class _Bank:
    mems: dict[str, _Mem] = field(default_factory=dict)  # document_id -> memory
    history: list[PlaybookVersion] = field(default_factory=list)
    playbook: str = ""


class InMemoryMemoryClient:
    def __init__(self) -> None:
        self.banks: dict[str, _Bank] = {}
        self.calls: list[str] = []
        self.retained_items: list[dict[str, Any]] = []

    def _bank(self, org: Any) -> _Bank:
        return self.banks.setdefault(bank_id(org), _Bank())

    async def ensure_bank(self, org: Any) -> None:
        self.calls.append("ensure_bank")
        self._bank(org)

    async def retain_verdict(self, org: Any, scan_id: str, cand: Candidate, res: Resource, verdict: Any,
                             reviewer: Any) -> str | None:
        self.calls.append("retain_verdict")
        item = verdict_item(scan_id, cand, res, verdict, reviewer)
        self.retained_items.append(item)
        doc = verdict_document_id(cand)
        decision = item["metadata"]["decision"]
        self._bank(org).mems[doc] = _Mem(id=doc, text=item["content"], reason=verdict.reason, decision=decision,
                                         tags=item["tags"])
        return f"op-{doc}"

    async def retain_seed(self, org: Any, text: str, doc_id: str) -> None:
        self.calls.append("retain_seed")
        self._bank(org).mems[doc_id] = _Mem(id=doc_id, text=text, reason=text, decision="reject", tags=["seed"])

    async def recall_for(self, org: Any, cand: Candidate, res: Resource) -> list[MemoryHit]:
        self.calls.append("recall_for")
        return self._search(org, recall_query(cand, res))

    def _search(self, org: Any, query: str) -> list[MemoryHit]:
        q = tokens(query)
        scored = []
        for m in self._bank(org).mems.values():
            if not m.valid:
                continue
            overlap = len(q & tokens(m.text))
            if overlap:
                scored.append(MemoryHit(id=m.id, text=m.text, type="experience", score=overlap / max(len(q), 1)))
        return sorted(scored, key=lambda h: -(h.score or 0))[:TOP_K]

    async def recall_many(self, org: Any, items: list[tuple[Candidate, Resource]],
                          concurrency: int = 8) -> list[list[MemoryHit]]:
        return list(await asyncio.gather(*(self.recall_for(org, c, r) for c, r in items)))

    def _groups(self, org: Any) -> dict[str, list[_Mem]]:
        groups: dict[str, list[_Mem]] = {}
        for m in self._bank(org).mems.values():
            if m.valid and m.decision == "reject" and m.reason:
                groups.setdefault(_norm(m.reason), []).append(m)
        return groups

    async def list_rules(self, org: Any) -> list[Rule]:
        self.calls.append("list_rules")
        rules = [Rule(id="obs-" + hashlib.sha1(key.encode()).hexdigest()[:10], text=ms[0].reason,
                      proof_count=len(ms), tags=[], sources=[MemoryHit(id=m.id, text=m.text, type="source")
                                                            for m in ms])
                 for key, ms in self._groups(org).items()]
        return sorted(rules, key=lambda r: -r.proof_count)

    async def delete_rule(self, org: Any, memory_id: str, reason: str = "removed by admin") -> None:
        self.calls.append("delete_rule")
        bank = self._bank(org)
        if memory_id in bank.mems:
            bank.mems[memory_id].valid = False
            return
        for rule in await self.list_rules(org):
            if rule.id == memory_id:
                for s in rule.sources:
                    bank.mems[s.id].valid = False

    async def get_playbook(self, org: Any) -> Playbook:
        self.calls.append("get_playbook")
        rules = await self.list_rules(org)
        content = "\n".join(f"- {r.text} (confirmed {r.proof_count}x)" for r in rules)
        bank = self._bank(org)
        if content != bank.playbook:
            bank.history.insert(0, PlaybookVersion(content=bank.playbook))
            bank.playbook = content
        return Playbook(content=content, structured={"protected_patterns": [
            {"pattern": r.text, "reason": r.text, "applies_to": "org"} for r in rules]})

    async def playbook_history(self, org: Any) -> list[PlaybookVersion]:
        self.calls.append("playbook_history")
        return list(self._bank(org).history)

    async def reflect(self, org: Any, question: str) -> ReflectAnswer:
        self.calls.append("reflect")
        hits = self._search(org, question)
        def gist(t: str) -> str:  # the verdict line of a retained decision, or the whole (one-line) seed rule
            return next((ln for ln in t.splitlines() if ln.startswith("Verdict:")), t.splitlines()[0] if t else "")

        text = "Based on past decisions: " + " | ".join(gist(h.text) for h in hits) if hits else \
            "No relevant past decisions."
        return ReflectAnswer(text=text, based_on=hits)

    async def wait_for_consolidation(self, org: Any, timeout_s: float = 90) -> bool:
        self.calls.append("wait_for_consolidation")
        return True
