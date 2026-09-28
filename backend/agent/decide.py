"""Per-candidate decisions: directive pre-filter -> recall -> LLM -> validated AgentDecision."""

import asyncio
import logging
from typing import Any

from pydantic import ValidationError

from backend.agent.llm import LLM
from backend.agent.prompt import build_candidate_prompt, build_system_prompt, retry_prompt
from backend.agent.schema import AgentDecision, fallback_ask
from backend.candidates.rules import Candidate
from backend.memory.setup import directives as org_directives
from backend.memory.types import MemoryClientProtocol, MemoryHit
from backend.scanner.models import Resource

log = logging.getLogger(__name__)
LLM_CONCURRENCY = 6
RETRIES = 2


def directive_block(resource: Resource) -> str | None:
    """Hard directive match on tags; no LLM call needed."""
    tags = {k.lower(): v for k, v in resource.tags.items()}
    if tags.get("do_not_terminate", "").lower() == "true":
        return "Directive: resource is tagged do_not_terminate=true."
    if any(k == "compliance" or k.startswith("compliance:") for k in tags):
        return "Directive: resource carries a compliance:* tag and needs a compliance review."
    return None


async def decide_one(llm: LLM, system: str, res: Resource, cand: Candidate, memories: list[MemoryHit]) -> AgentDecision:
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": build_candidate_prompt(res, cand, memories)}]
    for attempt in range(RETRIES + 1):
        try:
            raw = await llm.complete_json(messages)
        except Exception as e:
            log.warning("LLM call failed for %s: %s", cand.id, e)
            return fallback_ask(f"Agent unavailable ({type(e).__name__}); needs a human look.")
        try:
            decision = AgentDecision.model_validate_json(raw)
        except ValidationError as e:
            if attempt == RETRIES:
                break
            messages += [{"role": "assistant", "content": raw}, {"role": "user", "content": retry_prompt(str(e))}]
            continue
        allowed = {m.id for m in memories}
        decision.cited_memory_ids = [i for i in decision.cited_memory_ids if i in allowed]
        return decision
    return fallback_ask("Agent output failed validation 3 times; needs a human look.")


async def decide_all(org: Any, candidates: list[Candidate], resources: list[Resource],
                     memory_client: MemoryClientProtocol | None, llm: LLM, *, no_memory: bool = False,
                     recalled_out: dict[str, list[MemoryHit]] | None = None) -> dict[str, AgentDecision]:
    """recalled_out, if given, receives candidate id -> memories consulted (for UI / Slack)."""
    by_id = {r.id: r for r in resources}
    out: dict[str, AgentDecision] = {}
    todo: list[tuple[Candidate, Resource]] = []
    for c in candidates:
        res = by_id[c.resource_id]
        if reason := directive_block(res):
            out[c.id] = AgentDecision(decision="suppress", action="none", confidence=1.0, predicted_approval=0.0,
                                      reason=reason, risk_note="hard directive")
        else:
            todo.append((c, res))
    if not todo:
        return out

    if no_memory or memory_client is None:
        playbook, recalled = "", [[] for _ in todo]
    else:
        playbook_obj, recalled = await asyncio.gather(memory_client.get_playbook(org),
                                                      memory_client.recall_many(org, todo))
        playbook = playbook_obj.content
    system = build_system_prompt(org, org_directives(org), playbook)
    sem = asyncio.Semaphore(LLM_CONCURRENCY)

    async def run(c: Candidate, r: Resource, mems: list[MemoryHit]) -> None:
        if recalled_out is not None:
            recalled_out[c.id] = mems
        async with sem:
            out[c.id] = await decide_one(llm, system, r, c, mems)

    await asyncio.gather(*(run(c, r, m) for (c, r), m in zip(todo, recalled, strict=True)))
    return out
