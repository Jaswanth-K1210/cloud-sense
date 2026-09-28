import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from backend.agent.decide import decide_all
from backend.agent.fake_llm import FakeLLM
from backend.candidates.rules import Candidate
from backend.memory.fake import InMemoryMemoryClient
from backend.scanner.models import Resource


@dataclass
class Org:
    id: str = "acme"
    name: str = "Acme"
    hindsight_bank: str = "org-acme"
    hard_rules: list = field(default_factory=list)


def one(name="dev-box", tags=None, hints=None):
    r = Resource(id=name, type="ec2", name=name, account_alias="prod", tags=tags or {}, role_hints=hints or [])
    c = Candidate(id=f"c-{name}", resource_id=name, rule_id="R1", action="stop", monthly_saving=30,
                  signals_text="idle", reversible=True)
    return c, r


def good(**kw) -> str:
    return json.dumps({"decision": "recommend", "action": "stop", "confidence": 0.8, "predicted_approval": 0.7,
                       "reason": "idle", "cited_memory_ids": [], **kw})


async def test_malformed_twice_then_valid_is_accepted() -> None:
    c, r = one()
    llm = FakeLLM(["not json", '{"decision": "maybe"}', good()])
    out = await decide_all(Org(), [c], [r], None, llm, no_memory=True)
    assert out[c.id].decision == "recommend"
    assert len(llm.calls) == 3 and len(llm.calls[-1]) == 6  # system, user, (bad, retry) x2


async def test_malformed_three_times_falls_back_to_ask() -> None:
    c, r = one()
    out = await decide_all(Org(), [c], [r], None, FakeLLM(["x", "y", "z"]), no_memory=True)
    assert out[c.id].decision == "ask"


async def test_llm_exception_falls_back_to_ask() -> None:
    class Boom:
        async def complete_json(self, messages):
            raise TimeoutError

    c, r = one()
    assert (await decide_all(Org(), [c], [r], None, Boom(), no_memory=True))[c.id].decision == "ask"


async def test_directive_prefilter_skips_llm() -> None:
    c1, r1 = one("keep-me", tags={"do_not_terminate": "true"})
    c2, r2 = one("pci", tags={"compliance:pci": "yes"})
    llm = FakeLLM()
    out = await decide_all(Org(), [c1, c2], [r1, r2], InMemoryMemoryClient(), llm)
    assert out[c1.id].decision == out[c2.id].decision == "suppress"
    assert out[c1.id].reason.startswith("Directive:")
    assert llm.calls == []


async def test_cited_ids_filtered_to_recalled() -> None:
    mc, org = InMemoryMemoryClient(), Org()
    c, r = one("orders-db-standby", hints=["standby"])

    @dataclass
    class V:
        decision: str = "reject"
        reason: str = "DR standby"
        scope: str = "similar"
        at: datetime = datetime(2026, 9, 1, tzinfo=UTC)

    @dataclass
    class U:
        id: str = "u"
        name: str = "R"

    await mc.retain_verdict(org, "s", c, r, V(), U())
    c2, r2 = one("payments-db-standby", hints=["standby"])
    llm = FakeLLM([good(cited_memory_ids=["verdict-c-orders-db-standby", "made-up-id"])])
    out = await decide_all(org, [c2], [r2], mc, llm)
    assert out[c2.id].cited_memory_ids == ["verdict-c-orders-db-standby"]


async def test_no_memory_calls_no_memory_methods() -> None:
    mc = InMemoryMemoryClient()
    c, r = one()
    await decide_all(Org(), [c], [r], mc, FakeLLM(), no_memory=True)
    assert mc.calls == []


async def test_fake_llm_obeys_lookalike_memory() -> None:
    mc, org = InMemoryMemoryClient(), Org()

    @dataclass
    class V:
        decision: str = "reject"
        reason: str = "DR standby for orders-db, idle on purpose"
        scope: str = "similar"
        at: datetime = datetime(2026, 9, 1, tzinfo=UTC)

    @dataclass
    class U:
        id: str = "u"
        name: str = "R"

    c, r = one("orders-db-standby", hints=["standby", "replica_of:orders-db"])
    await mc.retain_verdict(org, "s", c, r, V(), U())
    c2, r2 = one("payments-db-standby", hints=["standby", "no_dependents"])
    c3, r3 = one("dev-sandbox-3", hints=["no_dependents"])
    out = await decide_all(org, [c2, c3], [r2, r3], mc, FakeLLM())
    assert out[c2.id].decision == "suppress" and out[c2.id].cited_memory_ids
    assert out[c3.id].decision == "recommend"
