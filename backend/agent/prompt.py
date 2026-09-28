"""Agent prompts (BUILD_DOC 7.1)."""

import json
from typing import Any

from backend.agent.schema import AgentDecision
from backend.candidates.rules import Candidate
from backend.memory.types import MemoryHit
from backend.scanner.models import Resource

OUTPUT_SCHEMA = json.dumps({
    "decision": "recommend | suppress | ask",
    "action": "stop | rightsize | snapshot_delete | modify_gp3 | release | delete_snapshot | s3_lifecycle | none",
    "confidence": "0.0-1.0",
    "predicted_approval": "0.0-1.0",
    "reason": "one or two sentences, max 300 chars",
    "cited_memory_ids": ["ids of MEMORIES you relied on"],
    "risk_note": "blast radius / IaC / compliance note",
})


def build_system_prompt(org: Any, directives: list[str], playbook_text: str) -> str:
    rules = "\n".join(f"- {d}" for d in directives) or "- (none)"
    return f"""You review AWS cost recommendations for {org.name}.

DIRECTIVES (never violate, they override everything else):
{rules}

ORG PLAYBOOK (learned from engineers' past verdicts):
{playbook_text.strip() or "(empty: nothing learned yet)"}

For each candidate you get resource facts, signals, role hints, blast radius and MEMORIES recalled from past
engineer decisions.
- Learned rules and memories override raw utilization signals.
- If a memory marks this resource OR a look-alike (same role hints, e.g. another standby/replica, another
  month-end batch worker) as protected, decide "suppress" and cite that memory id.
- If a memory shows engineers approved this pattern, "recommend" with higher predicted_approval.
- If uncertain (large blast radius, IaC-managed, conflicting memories, missing data), decide "ask" and say why.
- Only cite ids that appear in MEMORIES.
Output JSON only, exactly this shape:
{OUTPUT_SCHEMA}"""


def build_candidate_prompt(resource: Resource, candidate: Candidate, memories: list[MemoryHit]) -> str:
    mem_lines = "\n".join(f"[{m.id}] {m.text}" for m in memories) or "(no relevant memories)"
    return f"""CANDIDATE
rule: {candidate.rule_id}  proposed action: {candidate.action}  reversible: {candidate.reversible}
estimated saving: ${candidate.monthly_saving or 0:.2f}/month
signals: {candidate.signals_text}
warnings: {"; ".join(candidate.warnings) or "none"}

RESOURCE
{resource.display_name} ({resource.id}), type {resource.type}, account {resource.account_alias}, \
region {resource.region}, state {resource.state}, instance/volume type {resource.instance_type or resource.volume_type}
owner team: {resource.owner_team}  service: {resource.service}
tags: {json.dumps(resource.tags)}
iac_managed: {resource.iac_managed}
role hints: {", ".join(resource.role_hints) or "none"}
depends on: {", ".join(resource.depends_on_names) or "none"}
dependents: {", ".join(resource.dependent_names) or "none"}
blast radius: {candidate.blast_radius.count} ({", ".join(candidate.blast_radius.names[:10]) or "none"})

MEMORIES
{mem_lines}

Return the JSON decision."""


def retry_prompt(error: str) -> str:
    return (f"Your last answer failed validation: {error[:800]}\n"
            f"Return ONLY a JSON object matching: {json.dumps(AgentDecision.model_json_schema()['properties'])}")
