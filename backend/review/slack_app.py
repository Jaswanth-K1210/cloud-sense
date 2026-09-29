"""Slack review loop (Bolt, Socket Mode: no public URL). The only module that talks to Slack.

Run the interactive worker:   python -m backend.review.slack_app
The API process posts new candidates through `make_notifier(WebClient)` (see backend/app.py).
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from backend.config import settings
from backend.deps import Services, services
from backend.review.service import VerdictError, learn, submit_verdict
from backend.store.models import CandidateRow, Decision, Org, ResourceRow, Role, Scan, Scope, User, Verdict

log = logging.getLogger(__name__)
ACTION_TITLES = {"stop": "Stop", "rightsize": "Rightsize", "snapshot_delete": "Snapshot + delete",
                 "modify_gp3": "Modify gp2 → gp3", "release": "Release", "delete_snapshot": "Delete snapshot",
                 "s3_lifecycle": "Add lifecycle rule"}
SCOPES = [("this_resource", "Only this resource"), ("similar", "All similar resources"),
          ("team", "Everything owned by this team")]
REJECT_CALLBACK = "reject_modal"


# ---------- block builders (pure) ----------

def memory_line(text: str, limit: int = 280) -> str:
    """One readable line from a retained verdict: what was proposed and why it was (not) allowed."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    picked = [ln for ln in lines if ln.startswith("CloudSense proposed") or ln.startswith("Verdict:")]
    return (" → ".join(picked) or (lines[0] if lines else ""))[:limit]


def candidate_blocks(cand: dict[str, Any], resource: dict[str, Any], decision: dict[str, Any],
                     memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    title = f"{ACTION_TITLES.get(cand['action'], cand['action'])} *{resource['name']}*"
    if decision.get("decision") == "ask":
        title = f":question: Needs a human: {title}"
    br = cand.get("blast_radius") or {}
    fields = [
        f"*Resource*\n`{resource['id']}` ({resource['type']})",
        f"*Est. saving*\n${cand.get('monthly_saving') or 0:,.2f}/month",
        f"*Signals*\n{cand.get('signals_text', '')}",
        f"*Blast radius*\n{br.get('count', 0)} resource(s)",
    ]
    blocks: list[dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": title}},
        {"type": "section", "fields": [{"type": "mrkdwn", "text": f} for f in fields]},
    ]
    if decision.get("reason"):
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"Agent: {decision['reason']}"}]})
    if memories:
        bullets = "\n".join(f"• {memory_line(m['text'])}" for m in memories[:3])
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Memories consulted*\n{bullets}"}})
    blocks.append({"type": "actions", "block_id": "review", "elements": [
        {"type": "button", "action_id": "approve", "text": {"type": "plain_text", "text": "Approve"},
         "style": "primary", "value": cand["id"]},
        {"type": "button", "action_id": "reject", "text": {"type": "plain_text", "text": "Reject"},
         "style": "danger", "value": cand["id"]},
        {"type": "button", "action_id": "snooze", "text": {"type": "plain_text", "text": "Snooze 30d"},
         "value": cand["id"]},
        {"type": "button", "action_id": "why", "text": {"type": "plain_text", "text": "Why?"}, "value": cand["id"]},
    ]})
    return blocks


def reject_modal(cand_id: str, channel: str, ts: str, resource_name: str) -> dict[str, Any]:
    return {
        "type": "modal", "callback_id": REJECT_CALLBACK,
        "private_metadata": json.dumps({"cand_id": cand_id, "channel": channel, "ts": ts}),
        "title": {"type": "plain_text", "text": "Reject recommendation"},
        "submit": {"type": "plain_text", "text": "Reject"},
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": f"Why should CloudSense leave *{resource_name}* "
                                                                   "alone? Your reason becomes a learned rule."}},
            {"type": "input", "block_id": "reason", "label": {"type": "plain_text", "text": "Reason"},
             "element": {"type": "plain_text_input", "action_id": "reason_input", "multiline": True}},
            {"type": "input", "block_id": "scope", "label": {"type": "plain_text", "text": "Scope"},
             "element": {"type": "radio_buttons", "action_id": "scope_input",
                         "initial_option": {"text": {"type": "plain_text", "text": SCOPES[0][1]},
                                            "value": SCOPES[0][0]},
                         "options": [{"text": {"type": "plain_text", "text": t}, "value": v} for v, t in SCOPES]}},
            {"type": "input", "block_id": "until", "optional": True,
             "label": {"type": "plain_text", "text": "Temporary? Don't touch until"},
             "element": {"type": "datepicker", "action_id": "until_input"}},
        ],
    }


def learned_text(v: Verdict) -> str:
    if v.learning_status == "learned" and v.learned_rule_json:
        r = v.learned_rule_json
        return f"Rule learned: *{r['text']}* (confirmed {r['proof_count']}×)"
    if v.learning_status == "learned":
        return "Saved and consolidated."
    return "Saved; still consolidating."


# ---------- helpers ----------

def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _reviewer(s: Any, slack_id: str) -> User | None:
    user = s.scalars(select(User).where(User.slack_id == slack_id)).first()
    return user if user and user.role in (Role.reviewer, Role.admin) else None


def _not_reviewer(client: Any, channel: str, slack_id: str) -> None:
    client.chat_postEphemeral(channel=channel, user=slack_id, text="You're not a CloudSense reviewer.")


def _ctx(body: dict[str, Any]) -> tuple[str, str, str, str]:
    return (body["actions"][0]["value"], body["user"]["id"], body["channel"]["id"], body["message"]["ts"])


def post_candidate(client: Any, cand: dict[str, Any], resource: dict[str, Any], decision: dict[str, Any],
                   memories: list[dict[str, Any]], channel: str | None = None) -> Any:
    return client.chat_postMessage(channel=channel or settings.SLACK_REVIEW_CHANNEL,
                                   text=f"CloudSense: {cand['action']} {resource['name']}?",
                                   blocks=candidate_blocks(cand, resource, decision, memories))


def make_notifier(client: Any, svc: Services = services):
    """Pipeline hook: post each pending/asked candidate to the review channel."""
    def notify(org: Org, scan_id: str, rows: list[CandidateRow]) -> None:
        channel = ((org.settings_json or {}).get("slack") or {}).get("channel") if org else None
        with svc.session_factory() as s:
            for row in rows:
                res = s.get(ResourceRow, row.resource_id)
                decision = row.agent_decision_json or {}
                post_candidate(client, {"id": row.id, "action": row.action, "monthly_saving": row.monthly_saving,
                                        "signals_text": row.signals_text, "blast_radius": row.blast_radius},
                               {"id": res.aws_id, "name": res.name, "type": res.type}, decision,
                               decision.get("memories", []), channel=channel)
    return notify


# ---------- handlers (called by Bolt; testable with a fake client) ----------

def _simple_verdict(body: dict[str, Any], client: Any, svc: Services, decision: Decision) -> None:
    cand_id, slack_id, channel, ts = _ctx(body)
    with svc.session_factory() as s:
        user = _reviewer(s, slack_id)
        if user is None:
            return _not_reviewer(client, channel, slack_id)
        cand = s.get(CandidateRow, cand_id)
        try:
            _run(submit_verdict(s, svc, cand, user, decision))
        except VerdictError as e:
            client.chat_postEphemeral(channel=channel, user=slack_id, text=str(e))
            return None
    word = "Approved" if decision == Decision.approve else "Snoozed for 30 days"
    client.chat_postMessage(channel=channel, thread_ts=ts, text=f"{word} by <@{slack_id}>.")
    return None


def handle_approve(ack: Any, body: dict[str, Any], client: Any, svc: Services = services) -> None:
    ack()
    _simple_verdict(body, client, svc, Decision.approve)


def handle_snooze(ack: Any, body: dict[str, Any], client: Any, svc: Services = services) -> None:
    ack()
    _simple_verdict(body, client, svc, Decision.snooze)


def handle_reject(ack: Any, body: dict[str, Any], client: Any, svc: Services = services) -> None:
    ack()
    cand_id, slack_id, channel, ts = _ctx(body)
    with svc.session_factory() as s:
        if _reviewer(s, slack_id) is None:
            return _not_reviewer(client, channel, slack_id)
        cand = s.get(CandidateRow, cand_id)
        name = s.get(ResourceRow, cand.resource_id).name
    client.views_open(trigger_id=body["trigger_id"], view=reject_modal(cand_id, channel, ts, name))
    return None


def handle_reject_submit(ack: Any, body: dict[str, Any], client: Any, svc: Services = services,
                         learn_timeout_s: float = 90) -> None:
    values = body["view"]["state"]["values"]
    reason = (values["reason"]["reason_input"].get("value") or "").strip()
    if not reason:
        ack(response_action="errors", errors={"reason": "A reason is required: it's what CloudSense learns from."})
        return
    ack()
    meta = json.loads(body["view"]["private_metadata"])
    scope = Scope(values["scope"]["scope_input"]["selected_option"]["value"])
    until_raw = values.get("until", {}).get("until_input", {}).get("selected_date")
    until = datetime.fromisoformat(until_raw).replace(tzinfo=UTC) if until_raw else None
    slack_id = body["user"]["id"]
    with svc.session_factory() as s:
        user = _reviewer(s, slack_id)
        if user is None:
            return _not_reviewer(client, meta["channel"], slack_id)
        try:
            v = _run(submit_verdict(s, svc, s.get(CandidateRow, meta["cand_id"]), user, Decision.reject, reason,
                                    scope, until))
        except VerdictError as e:
            client.chat_postEphemeral(channel=meta["channel"], user=slack_id, text=str(e))
            return None
        verdict_id = v.id
    reply = client.chat_postMessage(channel=meta["channel"], thread_ts=meta["ts"],
                                    text="Got it. I'll remember this. Learning…")
    _run(learn(svc, verdict_id, timeout_s=learn_timeout_s))
    with svc.session_factory() as s:
        text = learned_text(s.get(Verdict, verdict_id))
    client.chat_update(channel=meta["channel"], ts=reply["ts"], text=text)
    return None


def handle_why(ack: Any, body: dict[str, Any], client: Any, svc: Services = services) -> None:
    ack()
    cand_id, slack_id, channel, _ = _ctx(body)
    with svc.session_factory() as s:
        cand = s.get(CandidateRow, cand_id)
        res = s.get(ResourceRow, cand.resource_id)
        org = s.get(Org, s.get(Scan, cand.scan_id).org_id)
        ans = _run(svc.memory.reflect(org, f"Why should or shouldn't we {cand.action} {res.name} ({res.type})? "
                                           "Cite past decisions."))
    sources = "\n".join(f"• {memory_line(h.text)}" for h in ans.based_on[:3]) or "• (no past decisions)"
    client.chat_postEphemeral(channel=channel, user=slack_id, text=f"{ans.text}\n\n*Sources*\n{sources}")


def register(app: Any, svc: Services = services) -> None:
    app.action("approve")(lambda ack, body, client: handle_approve(ack, body, client, svc))
    app.action("reject")(lambda ack, body, client: handle_reject(ack, body, client, svc))
    app.action("snooze")(lambda ack, body, client: handle_snooze(ack, body, client, svc))
    app.action("why")(lambda ack, body, client: handle_why(ack, body, client, svc))
    app.view(REJECT_CALLBACK)(lambda ack, body, client: handle_reject_submit(ack, body, client, svc))


def main() -> None:
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    from backend.store.db import init_db

    if not (settings.SLACK_BOT_TOKEN and settings.SLACK_APP_TOKEN):
        raise SystemExit("Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN (Socket Mode) first.")
    init_db()
    app = App(token=settings.SLACK_BOT_TOKEN)
    register(app)
    SocketModeHandler(app, settings.SLACK_APP_TOKEN).start()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
