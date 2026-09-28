from typing import Literal

from pydantic import BaseModel, Field

Action = Literal["stop", "rightsize", "snapshot_delete", "modify_gp3", "release", "delete_snapshot", "s3_lifecycle",
                 "none"]


class AgentDecision(BaseModel):
    decision: Literal["recommend", "suppress", "ask"]
    action: Action = "none"
    confidence: float = Field(ge=0, le=1)
    predicted_approval: float = Field(ge=0, le=1)
    reason: str = Field(max_length=300)
    cited_memory_ids: list[str] = Field(default_factory=list)
    risk_note: str = ""


def fallback_ask(reason: str) -> AgentDecision:
    return AgentDecision(decision="ask", action="none", confidence=0.0, predicted_approval=0.5, reason=reason[:300])
