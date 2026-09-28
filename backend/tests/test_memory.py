from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import SimpleNamespace

from backend.candidates.rules import Candidate
from backend.memory import setup
from backend.memory.client import MemoryClient
from backend.memory.fake import InMemoryMemoryClient
from backend.memory.templates import TEMPLATES, seed_accepted
from backend.memory.types import verdict_item


@dataclass
class Org:
    id: str = "acme"
    name: str = "Acme"
    hindsight_bank: str = "org-acme"
    hard_rules: list = field(default_factory=lambda: ["Never touch prod RDS"])


@dataclass
class V:
    decision: str = "reject"
    reason: str = "DR standby for orders-db, idle on purpose"
    scope: str = "similar"
    at: datetime = field(default_factory=lambda: datetime(2026, 9, 1, tzinfo=UTC))


@dataclass
class U:
    id: str = "u1"
    name: str = "Riley"
    team: str = "orders"


def pair(name: str = "orders-db-standby", source: str = "orders-db"):
    from backend.scanner.models import Resource

    res = Resource(id=name, type="rds", name=name, account_alias="prod", owner_team="orders", service="orders",
                   role_hints=["standby", f"replica_of:{source}"], depends_on_names=[source])
    cand = Candidate(id=f"c-{name}", resource_id=name, rule_id="R7", action="stop", monthly_saving=49.64,
                     signals_text="max DatabaseConnections = 0", reversible=True)
    return cand, res


def test_verdict_item_matches_spec_format() -> None:
    cand, res = pair()
    item = verdict_item("s1", cand, res, V(), U())
    assert item["tags"] == ["account:prod", "team:orders", "rtype:rds"]
    assert item["observation_scopes"] == [[], ["account:prod"], ["team:orders"]]
    assert item["metadata"] == {"candidate_id": "c-orders-db-standby", "resource_id": "orders-db-standby",
                                "decision": "reject", "reviewer_id": "u1", "scan_id": "s1"}
    assert {"text": "orders-db"} in item["entities"] and {"text": "orders"} in item["entities"]
    assert "Verdict: REJECT. Reason: DR standby for orders-db, idle on purpose" in item["content"]
    assert "Reviewer Riley (orders)" in item["content"]


async def test_fake_retain_then_recall_lookalike() -> None:
    mc, org = InMemoryMemoryClient(), Org()
    cand, res = pair()
    await mc.retain_verdict(org, "s1", cand, res, V(), U())
    hits = await mc.recall_for(org, *pair("payments-db-standby", "payments-db"))
    assert hits and hits[0].id == "verdict-c-orders-db-standby"


async def test_fake_rules_group_and_delete() -> None:
    mc, org = InMemoryMemoryClient(), Org()
    for name in ("a-standby", "b-standby"):
        c, r = pair(name)
        await mc.retain_verdict(org, "s1", c, r, V(reason="DR standby, idle on purpose"), U())
    c, r = pair("c-worker")
    await mc.retain_verdict(org, "s1", c, r, V(reason="month-end payroll spikes"), U())
    rules = await mc.list_rules(org)
    assert [x.proof_count for x in rules] == [2, 1]
    await mc.delete_rule(org, rules[0].id)
    assert [x.text for x in await mc.list_rules(org)] == ["month-end payroll spikes"]


async def test_seed_templates() -> None:
    mc, org = InMemoryMemoryClient(), Org()
    assert len(TEMPLATES) == 10
    assert await seed_accepted(mc, org, ["dr-standby", "nope"]) == ["dr-standby"]
    assert "seed-dr-standby" in mc.banks["org-acme"].mems


class StubHS:
    """Records calls made by the real MemoryClient; no network."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.pending = [1, 0]
        self.memory = SimpleNamespace(get_memory=self._get_memory, update_memory=self._update_memory)
        self.operations = SimpleNamespace(list_operations=self._list_ops)

    def __getattr__(self, name):
        async def rec(**kw):
            self.calls.append((name, kw))
            if name == "alist_directives":
                return SimpleNamespace(items=[SimpleNamespace(content=setup.DEFAULT_DIRECTIVES[0])])
            if name == "aget_mental_model":
                raise RuntimeError("404")
            if name == "aretain_batch":
                return SimpleNamespace(operation_id="op-1", operation_ids=None)
            return None
        return rec

    async def _get_memory(self, bank, mid):
        return SimpleNamespace(source_memory_ids=["f1", "f2"])

    async def _update_memory(self, bank, mid, req):
        self.calls.append(("update_memory", {"id": mid, "state": req.state}))

    async def _list_ops(self, bank, status=None, limit=None):
        return SimpleNamespace(total=self.pending.pop(0) if status == "pending" and self.pending else 0)


async def test_real_client_wiring(monkeypatch) -> None:
    monkeypatch.setattr("backend.memory.client.POLL_S", 0)
    hs = StubHS()
    mc, org = MemoryClient(hs), Org()
    await mc.ensure_bank(org)
    names = [n for n, _ in hs.calls]
    assert names[0] == "acreate_bank"
    assert hs.calls[0][1]["disposition_skepticism"] == 5
    created = [kw["content"] for n, kw in hs.calls if n == "acreate_directive"]
    assert created == [setup.DEFAULT_DIRECTIVES[1], "Never touch prod RDS"]  # first one already existed
    mm = next(kw for n, kw in hs.calls if n == "acreate_mental_model")
    assert mm["id"] == "org-playbook" and "tags" not in mm and mm["trigger"]["mode"] == "delta"

    cand, res = pair()
    assert await mc.retain_verdict(org, "s1", cand, res, V(), U()) == "op-1"
    kw = next(kw for n, kw in hs.calls if n == "aretain_batch")
    assert kw["document_id"] == "verdict-c-orders-db-standby"
    assert kw["items"][0]["observation_scopes"][0] == []

    await mc.delete_rule(org, "obs-1")
    assert [c[1] for c in hs.calls if c[0] == "update_memory"] == [
        {"id": "f1", "state": "invalidated"}, {"id": "f2", "state": "invalidated"}]
    assert await mc.wait_for_consolidation(org, timeout_s=5) is True


def test_real_client_uses_one_sdk_client_per_event_loop(monkeypatch) -> None:
    import asyncio

    made = []

    class FakeHindsight:
        def __init__(self, **kw) -> None:
            made.append(self)

    monkeypatch.setattr("backend.memory.client.Hindsight", FakeHindsight)
    mc = MemoryClient()

    async def grab():
        return mc.hs, mc.hs

    a1, a2 = asyncio.run(grab())
    b1, _ = asyncio.run(grab())  # a new loop, like the Slack worker's asyncio.run per click
    assert a1 is a2 and a1 is not b1 and len(made) == 2
