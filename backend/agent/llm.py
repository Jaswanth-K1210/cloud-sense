"""The only module that talks to Groq (OpenAI-compatible API)."""

import asyncio
import weakref
from typing import Protocol

from openai import AsyncOpenAI

from backend.config import settings

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
TIMEOUT_S = 30.0
MAX_RETRIES = 5  # the SDK backs off on 429/5xx and honours Groq's retry-after header


class LLM(Protocol):
    async def complete_json(self, messages: list[dict[str, str]]) -> str: ...


class GroqLLM:
    def __init__(self, client: AsyncOpenAI | None = None) -> None:
        self._fixed = client  # injected (tests): used as-is
        # httpx connections are bound to the event loop that opened them; keep one client per running loop.
        self._per_loop: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, AsyncOpenAI] = (
            weakref.WeakKeyDictionary())
        self.models = [settings.AGENT_MODEL, settings.AGENT_FALLBACK_MODEL]

    @property
    def client(self) -> AsyncOpenAI:
        if self._fixed is not None:
            return self._fixed
        loop = asyncio.get_running_loop()
        if loop not in self._per_loop:
            self._per_loop[loop] = AsyncOpenAI(base_url=GROQ_BASE_URL, api_key=settings.GROQ_API_KEY or "unset",
                                               timeout=TIMEOUT_S, max_retries=MAX_RETRIES)
        return self._per_loop[loop]

    async def complete_json(self, messages: list[dict[str, str]]) -> str:
        errors: list[str] = []
        for model in self.models:
            try:
                resp = await self.client.chat.completions.create(
                    model=model, messages=messages, response_format={"type": "json_object"}, temperature=0.1)
                return resp.choices[0].message.content or ""
            except Exception as e:  # fall through to the fallback model
                errors.append(f"{model}: {type(e).__name__}: {str(e)[:200]}")
        raise RuntimeError("all models failed: " + " | ".join(errors))
