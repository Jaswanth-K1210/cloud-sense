import json

import pytest
from sqlalchemy.orm import sessionmaker

from backend.deps import Services
from backend.memory.fake import InMemoryMemoryClient
from backend.review import slack_app as sa
from backend.scanner.models import Resource
from backend.store.db import init_db, make_engine
from backend.store.models import CandidateRow, CandidateStatus, ResourceRow, Scan, User, Verdict
from backend.store.seed_demo import seed


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __getattr__(self, name):
        def rec(**kw):
            self.calls.append((name, kw))
            return {"ok": True, "ts": f"ts-{len(self.calls)}"}
        return rec

    def named(self, name: str) -> list[dict]:
        return [kw for n, kw in self.calls if n == name]


class Ack:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, **kw) -> None:
        self.calls.append(kw)


@pytest.fixture
def svc():
    engine = make_engine("sqlite://")
    init_db(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        seed(s)
        s.add(Scan(id="scan1", org_id="acme", status="done"))
        res = Resource(id="i-1", type="ec2", name="orders-db-standby", account_alias="sandbox",
                       role_hints=["standby"])
        s.add(ResourceRow(id="r1", scan_id="scan1", aws_id="i-1", type="ec2", name="orders-db-standby",
                          data_json=res.model_dump(mode="json")))
        s.add(CandidateRow(id="c1", scan_id="scan1", resource_id="r1", rule_id="R1", action="stop",
                           monthly_saving=7.59, signals_text="CPU avg 0.4%", blast_radius={"count": 0, "names": []},
                           extra_json={"reversible": True, "warnings": []}))
        s.add(User(id="u-viewer", org_id="acme", name="Vic", slack_id="U00VIEW"))
        s.commit()
    svc = Services(session_factory=factory)
    svc.memory = InMemoryMemoryClient()
    return svc


def action_body(action: str, user: str = "U00REVIEW") -> dict:
    return {"user": {"id": user}, "actions": [{"action_id": action, "value": "c1"}], "channel": {"id": "C1"},
            "message": {"ts": "100.1"}, "trigger_id": "trig"}


def status(svc: Services) -> CandidateStatus:
    with svc.session_factory() as s:
        return s.get(CandidateRow, "c1").status


def test_candidate_blocks() -> None:
    blocks = sa.candidate_blocks(
        {"id": "c1", "action": "stop", "monthly_saving": 7.59, "signals_text": "idle",
         "blast_radius": {"count": 2}},
        {"id": "i-1", "name": "orders-db-standby", "type": "ec2"},
        {"decision": "recommend", "reason": "looks idle"},
        [{"id": "m1", "text": "line\nVerdict: REJECT. Reason: DR standby\nScope"}])
    text = json.dumps(blocks)
    assert "orders-db-standby" in text and "$7.59/month" in text and "2 resource(s)" in text
    assert "Memories consulted" in text and "DR standby" in text
    assert [e["action_id"] for e in blocks[-1]["elements"]] == ["approve", "reject", "snooze", "why"]
    assert all(e["value"] == "c1" for e in blocks[-1]["elements"])


def test_reject_modal_shape() -> None:
    m = sa.reject_modal("c1", "C1", "100.1", "db")
    assert json.loads(m["private_metadata"]) == {"cand_id": "c1", "channel": "C1", "ts": "100.1"}
    assert [b.get("block_id") for b in m["blocks"][1:]] == ["reason", "scope", "until"]
    assert [o["value"] for o in m["blocks"][2]["element"]["options"]] == ["this_resource", "similar", "team"]


def test_approve(svc: Services) -> None:
    client, ack = FakeClient(), Ack()
    sa.handle_approve(ack, action_body("approve"), client, svc)
    assert ack.calls == [{}]
    assert status(svc) == CandidateStatus.approved
    assert "Approved by <@U00REVIEW>" in client.named("chat_postMessage")[0]["text"]


def test_unknown_or_viewer_is_rejected(svc: Services) -> None:
    for user in ("UNKNOWN", "U00VIEW"):
        client = FakeClient()
        sa.handle_approve(Ack(), action_body("approve", user), client, svc)
        assert client.named("chat_postEphemeral")[0]["text"] == "You're not a CloudSense reviewer."
    assert status(svc) == CandidateStatus.pending


def test_reject_opens_modal_then_submit_learns(svc: Services) -> None:
    client = FakeClient()
    sa.handle_reject(Ack(), action_body("reject"), client, svc)
    view = client.named("views_open")[0]["view"]

    body = {"user": {"id": "U00REVIEW"}, "view": {"private_metadata": view["private_metadata"], "state": {"values": {
        "reason": {"reason_input": {"value": "DR standby for orders-db, idle on purpose"}},
        "scope": {"scope_input": {"selected_option": {"value": "similar"}}},
        "until": {"until_input": {"selected_date": None}}}}}}
    ack = Ack()
    sa.handle_reject_submit(ack, body, client, svc)
    assert ack.calls == [{}]
    assert status(svc) == CandidateStatus.rejected
    assert client.named("chat_postMessage")[0]["text"] == "Got it. I'll remember this. Learning…"
    update = client.named("chat_update")[0]
    assert update["text"].startswith("Rule learned: *DR standby for orders-db, idle on purpose* (confirmed 1×)")
    with svc.session_factory() as s:
        (v,) = s.query(Verdict).all()
        assert v.scope.value == "similar"


def test_reject_submit_requires_reason(svc: Services) -> None:
    body = {"user": {"id": "U00REVIEW"}, "view": {"private_metadata": "{}", "state": {"values": {
        "reason": {"reason_input": {"value": "  "}}}}}}
    ack = Ack()
    sa.handle_reject_submit(ack, body, FakeClient(), svc)
    assert ack.calls[0]["response_action"] == "errors"


def test_why_replies_ephemerally_with_sources(svc: Services) -> None:
    client = FakeClient()
    sa.handle_reject_submit(Ack(), {"user": {"id": "U00REVIEW"}, "view": {
        "private_metadata": json.dumps({"cand_id": "c1", "channel": "C1", "ts": "1"}), "state": {"values": {
            "reason": {"reason_input": {"value": "DR standby, idle on purpose"}},
            "scope": {"scope_input": {"selected_option": {"value": "similar"}}}}}}}, client, svc)
    sa.handle_why(Ack(), action_body("why"), client, svc)
    msg = client.named("chat_postEphemeral")[-1]
    assert msg["user"] == "U00REVIEW" and "Sources" in msg["text"] and "orders-db-standby" in msg["text"]


def test_notifier_posts_each_candidate(svc: Services) -> None:
    client = FakeClient()
    with svc.session_factory() as s:
        rows = [s.get(CandidateRow, "c1")]
    sa.make_notifier(client, svc)(None, "scan1", rows)
    (post,) = client.named("chat_postMessage")
    assert post["blocks"][-1]["elements"][0]["value"] == "c1"


def test_send_test_message_explains_slack_errors(monkeypatch) -> None:
    from slack_sdk.errors import SlackApiError

    class Boom:
        def __init__(self, token=None) -> None:
            pass

        def chat_postMessage(self, **kw):
            raise SlackApiError("no", {"ok": False, "error": "not_in_channel"})

    monkeypatch.setattr("slack_sdk.WebClient", Boom)
    ok, msg = sa.send_test_message("#x")
    assert not ok and "/invite" in msg
