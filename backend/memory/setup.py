"""One-time, idempotent bank + playbook setup per org (BUILD_DOC 5.2). Signatures: docs/HINDSIGHT_NOTES.md."""

from typing import Any

from backend.memory.types import PLAYBOOK_ID, bank_id

DISPOSITION = {"disposition_skepticism": 5, "disposition_literalism": 4, "disposition_empathy": 2}
DEFAULT_DIRECTIVES = [
    "Never recommend terminating or stopping resources tagged do_not_terminate=true",
    "Never recommend actions on resources tagged compliance:* without flagging for review",
]
PLAYBOOK_QUERY = ("Which AWS resources or resource patterns must never be stopped, deleted or rightsized in this "
                  "organization, and why? Include evidence.")
PLAYBOOK_SCHEMA = {
    "type": "object",
    "properties": {
        "protected_patterns": {"type": "array", "items": {"type": "object", "properties": {
            "pattern": {"type": "string"}, "reason": {"type": "string"}, "applies_to": {"type": "string"}}}},
        "safe_patterns": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["protected_patterns"],
}
PLAYBOOK_TRIGGER = {
    "refresh_after_consolidation": True,
    "mode": "delta",
    "keep_trace": True,
    "min_refresh_interval_seconds": 0,  # demo: refresh on every consolidation
    "response_schema": PLAYBOOK_SCHEMA,
}


def mission(org: Any) -> str:
    return (f"I review AWS cost-saving recommendations for {org.name}. "
            "Breaking production is worse than missing a saving.")


def directives(org: Any) -> list[str]:
    return list(dict.fromkeys(DEFAULT_DIRECTIVES + list(getattr(org, "hard_rules", None) or [])))


async def ensure_bank(hs: Any, org: Any) -> None:
    bid = bank_id(org)
    await hs.acreate_bank(bank_id=bid, name=org.name, mission=mission(org), **DISPOSITION)  # PUT: create or update
    existing = {d.content for d in (await hs.alist_directives(bank_id=bid)).items}
    for i, text in enumerate(directives(org)):
        if text not in existing:
            await hs.acreate_directive(bank_id=bid, name=f"hard-rule-{i + 1}", content=text)
    try:
        await hs.aget_mental_model(bank_id=bid, mental_model_id=PLAYBOOK_ID, detail="metadata")
    except Exception:  # not found -> create. Untagged on purpose (tagged models match all_strict).
        await hs.acreate_mental_model(bank_id=bid, id=PLAYBOOK_ID, name="Org Cost Playbook",
                                      source_query=PLAYBOOK_QUERY, trigger=PLAYBOOK_TRIGGER)
