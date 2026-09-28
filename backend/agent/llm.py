"""The only module that talks to Groq (OpenAI-compatible API)."""

from typing import Protocol

from openai import AsyncOpenAI

from backend.config import settings

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
TIMEOUT_S = 30.0


class LLM(Protocol):
    async def complete_json(self, messages: list[dict[str, str]]) -> str: ...


class GroqLLM:
    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        self.client = client or AsyncOpenAI(base_url=GROQ_BASE_URL, api_key=settings.GROQ_API_KEY or "unset",
                                            timeout=TIMEOUT_S)
        self.models = [settings.AGENT_MODEL, settings.AGENT_FALLBACK_MODEL]

    async def complete_json(self, messages: list[dict[str, str]]) -> str:
        last: Exception | None = None
        for model in self.models:
            try:
                resp = await self.client.chat.completions.create(
                    model=model, messages=messages, response_format={"type": "json_object"}, temperature=0.1)
                return resp.choices[0].message.content or ""
            except Exception as e:  # fall through to the fallback model
                last = e
        raise RuntimeError(f"all models failed: {last}")
