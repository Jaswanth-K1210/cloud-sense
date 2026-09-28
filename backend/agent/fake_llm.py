"""Deterministic stand-in for Groq, used by tests and `run_eval --fake`.

It "obeys memories": if a recalled REJECT memory shares a meaningful role-hint token with the
candidate (standby, payroll, archive, ...), it suppresses and cites it; otherwise it recommends.
"""

import json
import re

from backend.graph.build import NAME_TOKENS

HINT_WORDS = set(NAME_TOKENS) | {"periodic", "spikes", "license", "debug", "oncall", "sre"}


class FakeLLM:
    def __init__(self, scripted: list[str] | None = None) -> None:
        self.scripted = list(scripted or [])
        self.calls: list[list[dict[str, str]]] = []

    async def complete_json(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        if self.scripted:
            return self.scripted.pop(0)
        prompt = messages[1]["content"]
        action = re.search(r"proposed action: (\S+)", prompt).group(1)
        hints_line = re.search(r"role hints: (.*)", prompt).group(1).lower()
        hint_tokens = set(re.findall(r"[a-z0-9]+", hints_line)) & HINT_WORDS
        mem_block = prompt.split("MEMORIES", 1)[1]
        for mid, text in re.findall(r"\[([^\]]+)\] (.*?)(?=\n\[|\nReturn the JSON|\Z)", mem_block, re.S):
            low = text.lower()
            is_protective = "verdict: reject" in low or "never" in low
            if is_protective and hint_tokens & set(re.findall(r"[a-z0-9]+", low)):
                return json.dumps({"decision": "suppress", "action": "none", "confidence": 0.9,
                                   "predicted_approval": 0.05,
                                   "reason": f"Past decision marks look-alikes as protected ({mid}).",
                                   "cited_memory_ids": [mid], "risk_note": ""})
        return json.dumps({"decision": "recommend", "action": action, "confidence": 0.7, "predicted_approval": 0.7,
                           "reason": "Signals indicate waste and no memory protects it.", "cited_memory_ids": [],
                           "risk_note": ""})
