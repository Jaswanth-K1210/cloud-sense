"""Thin wrapper over the Hindsight SDK (the only module that talks to Hindsight).

Every method is async. Real signatures are documented in docs/HINDSIGHT_NOTES.md.
"""

import asyncio
import time
import weakref
from typing import Any

from hindsight_client import Hindsight
from hindsight_client_api.models.update_memory_request import UpdateMemoryRequest

from backend.candidates.rules import Candidate
from backend.config import settings
from backend.memory import setup
from backend.memory.types import (
    PLAYBOOK_ID,
    SEED_CONTEXT,
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

RECALL_MAX_TOKENS = 1500
POLL_S = 2.0
MAX_RULE_SOURCES = 5


def _hit(r: Any) -> MemoryHit:
    scores = getattr(r, "scores", None)
    return MemoryHit(id=r.id or "", text=r.text, type=getattr(r, "type", None),
                     score=getattr(scores, "final", None) if scores else None)


class MemoryClient:
    def __init__(self, hs: Hindsight | None = None) -> None:
        self._fixed = hs  # injected (tests): used as-is
        # The SDK's HTTP session is bound to the event loop that first used it; the Slack worker and
        # background tasks run on other loops, so keep one SDK client per running loop.
        self._per_loop: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, Hindsight] = (
            weakref.WeakKeyDictionary())

    @property
    def hs(self) -> Hindsight:
        if self._fixed is not None:
            return self._fixed
        loop = asyncio.get_running_loop()
        if loop not in self._per_loop:
            self._per_loop[loop] = Hindsight(base_url=settings.HINDSIGHT_BASE_URL, api_key=settings.HINDSIGHT_API_KEY)
        return self._per_loop[loop]

    async def ensure_bank(self, org: Any) -> None:
        await setup.ensure_bank(self.hs, org)

    async def retain_verdict(self, org: Any, scan_id: str, cand: Candidate, res: Resource, verdict: Any,
                             reviewer: Any) -> str | None:
        resp = await self.hs.aretain_batch(bank_id=bank_id(org), items=[verdict_item(scan_id, cand, res, verdict,
                                                                                  reviewer)],
                                           document_id=verdict_document_id(cand), retain_async=True)
        return resp.operation_id or (resp.operation_ids or [None])[0]

    async def retain_seed(self, org: Any, text: str, doc_id: str) -> None:
        await self.hs.aretain_batch(bank_id=bank_id(org), document_id=doc_id, items=[
            {"content": text, "context": SEED_CONTEXT, "tags": ["seed"], "observation_scopes": [[]]}])

    async def recall_for(self, org: Any, cand: Candidate, res: Resource) -> list[MemoryHit]:
        resp = await self.hs.arecall(bank_id=bank_id(org), query=recall_query(cand, res),
                                     tags=[f"account:{res.account_alias}"], tags_match="any",
                                     max_tokens=RECALL_MAX_TOKENS)
        return [_hit(r) for r in resp.results]

    async def recall_many(self, org: Any, items: list[tuple[Candidate, Resource]],
                          concurrency: int = 8) -> list[list[MemoryHit]]:
        sem = asyncio.Semaphore(concurrency)

        async def one(c: Candidate, r: Resource) -> list[MemoryHit]:
            async with sem:
                return await self.recall_for(org, c, r)

        return list(await asyncio.gather(*(one(c, r) for c, r in items)))

    async def get_playbook(self, org: Any) -> Playbook:
        try:
            mm = await self.hs.aget_mental_model(bank_id=bank_id(org), mental_model_id=PLAYBOOK_ID, detail="full")
        except Exception:
            return Playbook()
        rr = mm.reflect_response or {}
        return Playbook(content=mm.content or "", structured=rr.get("structured_output"),
                        last_refreshed_at=mm.last_refreshed_at)

    async def playbook_history(self, org: Any) -> list[PlaybookVersion]:
        entries = await self.hs.aget_mental_model_history(bank_id=bank_id(org), mental_model_id=PLAYBOOK_ID)
        out = []
        for e in entries or []:
            d = e if isinstance(e, dict) else getattr(e, "to_dict", lambda: {})()
            out.append(PlaybookVersion(content=d.get("previous_content") or "", changed_at=d.get("changed_at")))
        return out

    async def reflect(self, org: Any, question: str) -> ReflectAnswer:
        ans = await self.hs.areflect(bank_id=bank_id(org), query=question, include_facts=True)
        b = ans.based_on
        hits = [MemoryHit(id=m.id or "", text=m.text, type=m.type) for m in (b.memories or [] if b else [])]
        hits += [MemoryHit(id=m.id, text=m.text, type="mental_model") for m in (b.mental_models or [] if b else [])]
        return ReflectAnswer(text=ans.text, based_on=hits)

    async def list_rules(self, org: Any) -> list[Rule]:
        bid = bank_id(org)
        resp = await self.hs.alist_memories(bank_id=bid, type="observation", limit=100)
        rules = []
        for m in resp.items:
            if m.state == "invalidated":
                continue
            sources = []
            for sid in (m.source_memory_ids or [])[:MAX_RULE_SOURCES]:
                try:
                    s = await self.hs.memory.get_memory(bid, sid)
                    sources.append(MemoryHit(id=sid, text=getattr(s, "text", "") or "", type="source"))
                except Exception:
                    sources.append(MemoryHit(id=sid, text="", type="source"))
            rules.append(Rule(id=m.id, text=m.text or "", proof_count=m.proof_count or 1, tags=m.tags or [],
                              sources=sources, updated_at=m.updated_at))
        return sorted(rules, key=lambda r: -r.proof_count)

    async def delete_rule(self, org: Any, memory_id: str, reason: str = "removed by admin") -> None:
        """Hindsight cannot curate observations directly: invalidate their source facts instead."""
        bid = bank_id(org)
        mem = await self.hs.memory.get_memory(bid, memory_id)
        sources = getattr(mem, "source_memory_ids", None) or [memory_id]
        for sid in sources:
            await self.hs.memory.update_memory(bid, sid, UpdateMemoryRequest(state="invalidated", reason=reason))

    async def wait_for_consolidation(self, org: Any, timeout_s: float = 90) -> bool:
        """Poll until no pending/processing operations remain. False on timeout."""
        bid = bank_id(org)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            busy = 0
            for status in ("pending", "processing"):
                busy += (await self.hs.operations.list_operations(bid, status=status, limit=1)).total
            if busy == 0:
                return True
            await asyncio.sleep(POLL_S)
        return False
