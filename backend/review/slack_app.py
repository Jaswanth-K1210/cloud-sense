"""Slack review loop (Bolt, Socket Mode: no public URL). The only module that talks to Slack.

Run the interactive worker:   python -m backend.review.slack_app
The API process posts new candidates through `make_notifier(WebClient)` (see backend/app.py).
"""

import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from backend.config import settings
from backend.deps import Services, services
from backend.review.service import VerdictError, learn, submit_verdict
from backend.store.models import (
    CandidateRow,
    CandidateStatus,
    Decision,
    Org,
    ResourceRow,
    Role,
    Scan,
    Scope,
    User,
    Verdict,
)

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


def _action_title(cand: dict[str, Any], resource: dict[str, Any]) -> str:
    proposed = re.search(r"proposed (\S+)", cand.get("signals_text", ""))
    verb = {"stop": "Stop", "rightsize": "Rightsize", "snapshot_delete": "Delete (after snapshot)",
            "modify_gp3": "Switch to gp3", "release": "Release", "delete_snapshot": "Delete snapshot",
            "s3_lifecycle": "Add lifecycle rule to"}.get(cand["action"], cand["action"])
    title = f"{verb} {resource['name']}"
    if cand["action"] == "rightsize" and proposed:
        title += f" to {proposed.group(1)}"
    return f"{title}: save ${cand.get('monthly_saving') or 0:,.0f}/mo"


def candidate_blocks(cand: dict[str, Any], resource: dict[str, Any], decision: dict[str, Any],
                     memories: list[dict[str, Any]], status_line: str | None = None) -> list[dict[str, Any]]:
    """Figma 14 "Recommendation block". status_line replaces the buttons once someone has decided."""
    ask = decision.get("decision") == "ask"
    br = cand.get("blast_radius") or {}
    n = br.get("count", 0)
    where = " · ".join(x for x in (resource.get("account"), resource.get("region")) if x)
    blast = f"{n} dependent{'s' if n != 1 else ''}" + (f" ({', '.join(br.get('names', [])[:3])})" if n else "")
    if memories:
        mem = "Memory checked: " + memory_line(memories[0]["text"])
    else:
        mem = "Memory checked: no past decisions about this pattern"
    blocks: list[dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"{':question:' if ask else ':large_orange_circle:'} "
                                                               f"*{_action_title(cand, resource)}*"
                                                               + (f"    _{where}_" if where else "")}},
        {"type": "section", "text": {"type": "mrkdwn", "text":
            f"*Why flagged:* {cand.get('signals_text', '')}\n*Blast radius:* {blast}"
            + (f"\n*Needs your input:* {decision['reason']}" if ask and decision.get("reason") else "")}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": f":sparkles: {mem}"}]},
    ]
    if status_line:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": status_line}]})
        return blocks
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


def row_blocks(s: Any, row: CandidateRow, status_line: str | None = None) -> list[dict[str, Any]]:
    res = s.get(ResourceRow, row.resource_id)
    decision = row.agent_decision_json or {}
    return candidate_blocks(
        {"id": row.id, "action": row.action, "monthly_saving": row.monthly_saving, "signals_text": row.signals_text,
         "blast_radius": row.blast_radius},
        {"id": res.aws_id, "name": res.name, "type": res.type, "account": (res.data_json or {}).get("account_alias"),
         "region": (res.data_json or {}).get("region")}, decision, decision.get("memories", []), status_line)


SCOPE_TEXT = {"similar": "all accounts", "this_resource": "this resource", "team": "your team"}


def learned_blocks(v: Verdict) -> list[dict[str, Any]]:
    """Figma 15 thread reply: the rule card."""
    r = v.learned_rule_json or {}
    blocks: list[dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f":sparkles: *Rule learned*\n*{r.get('text')}*"}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text":
            f"Confirmed {r.get('proof_count', 1)}× · applies to {SCOPE_TEXT.get(v.scope.value, 'all accounts')}"
            " · look-alikes will be skipped"}]},
    ]
    if settings.APP_URL:
        blocks.append({"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "View rule"},
             "url": f"{settings.APP_URL}/#rules"},
            {"type": "button", "text": {"type": "plain_text", "text": "View playbook"},
             "url": f"{settings.APP_URL}/#playbook"}]})
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


MAX_PER_SCAN = 10  # more than this: one summary message pointing at the dashboard


def make_notifier(client: Any, svc: Services = services):
    """Pipeline hook: a scan summary (incl. what learned rules skipped), then one message per recommendation."""
    def notify(org: Org, scan_id: str, rows: list[CandidateRow]) -> None:
        channel = (((org.settings_json or {}).get("slack") or {}).get("channel") if org else None) \
            or settings.SLACK_REVIEW_CHANNEL
        with svc.session_factory() as s:
            skipped = list(s.scalars(select(CandidateRow).where(CandidateRow.scan_id == scan_id,
                                                              CandidateRow.status == CandidateStatus.suppressed)))
            accounts = sorted({(s.get(ResourceRow, r.resource_id).data_json or {}).get("account_alias")
                               or "your account" for r in rows}) or ["your account"]
            summary = [{"type": "section", "text": {"type": "mrkdwn", "text":
                f"*{len(rows)} new recommendation{'s' if len(rows) != 1 else ''}* from today’s scan of "
                f"{', '.join(accounts)}" + (f" · {len(skipped)} skipped by learned rules" if skipped else "") + "."}}]
            for sk in skipped[:5]:
                res = s.get(ResourceRow, sk.resource_id)
                why = (sk.agent_decision_json or {}).get("reason", "")
                summary.append({"type": "context", "elements": [{"type": "mrkdwn",
                                "text": f":sparkles: *Skipped {res.name}:* {why} No action needed."}]})
            if len(rows) > MAX_PER_SCAN:
                summary.append({"type": "context", "elements": [{"type": "mrkdwn", "text":
                    "Too many to post one by one. Review them in the CloudSense dashboard."
                    + (f" {settings.APP_URL}/#recommendations" if settings.APP_URL else "")}]})
            client.chat_postMessage(channel=channel, text=f"{len(rows)} new CloudSense recommendations",
                                    blocks=summary)
            for row in rows[:MAX_PER_SCAN]:
                res = s.get(ResourceRow, row.resource_id)
                client.chat_postMessage(channel=channel, text=f"CloudSense: {row.action} {res.name}?",
                                        blocks=row_blocks(s, row))
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
        line = (f":white_check_mark: Approved by <@{slack_id}> · queued for execution" if decision == Decision.approve
                else f":zzz: Snoozed for 30 days by <@{slack_id}>")
        client.chat_update(channel=channel, ts=ts, text=line, blocks=row_blocks(s, cand, line))
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
    with svc.session_factory() as s:
        line = f":x: Rejected by <@{slack_id}>: “{reason}”"
        client.chat_update(channel=meta["channel"], ts=meta["ts"], text=line,
                           blocks=row_blocks(s, s.get(CandidateRow, meta["cand_id"]), line))
    reply = client.chat_postMessage(channel=meta["channel"], thread_ts=meta["ts"],
                                    text="Got it. I'll remember this. Learning…")
    _run(learn(svc, verdict_id, timeout_s=learn_timeout_s))
    with svc.session_factory() as s:
        v = s.get(Verdict, verdict_id)
        text = learned_text(v)
        blocks = learned_blocks(v) if v.learning_status == "learned" and v.learned_rule_json else None
    client.chat_update(channel=meta["channel"], ts=reply["ts"], text=text, **({"blocks": blocks} if blocks else {}))
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


def start_socket_mode(svc: Services = services):
    """Open the Socket Mode connection in background threads (used by the API process at startup)."""
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    app = App(token=settings.SLACK_BOT_TOKEN)
    register(app, svc)
    handler = SocketModeHandler(app, settings.SLACK_APP_TOKEN)
    handler.connect()  # non-blocking
    return handler


SLACK_FIXES = {
    "channel_not_found": "Channel not found. Check the name, or invite the bot to the channel (/invite @your-bot).",
    "not_in_channel": "The bot isn't in this channel. In Slack, type /invite @your-bot in the channel.",
    "is_archived": "That channel is archived. Pick another one.",
    "invalid_auth": "Slack rejected the bot token. Reinstall the app and update SLACK_BOT_TOKEN.",
    "missing_scope": "The bot lacks a permission. Add chat:write and chat:write.public, then reinstall the app.",
}


def send_test_message(channel: str) -> tuple[bool, str]:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    try:
        WebClient(token=settings.SLACK_BOT_TOKEN).chat_postMessage(
            channel=channel, text=":white_check_mark: CloudSense is connected. New recommendations will appear here.")
        return True, f"Test message sent to {channel}."
    except SlackApiError as e:
        code = e.response.get("error", "")
        return False, SLACK_FIXES.get(code, f"Slack said: {code or e}")


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
