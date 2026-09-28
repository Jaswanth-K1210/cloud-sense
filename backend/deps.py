"""Wiring for external services. Tests swap attributes on `services` for fakes."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from backend.agent.llm import LLM
from backend.memory.types import MemoryClientProtocol
from backend.scanner.models import Resource


@dataclass
class Services:
    session_factory: sessionmaker[Session]
    _memory: MemoryClientProtocol | None = None
    _llm: LLM | None = None
    scan_account: Callable[[Any], list[Resource]] | None = None
    # Called with (org, scan_id, [candidate rows]) after a scan; set by the Slack app. None = no-op.
    notify_review: Callable[[Any, str, list[Any]], Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def memory(self) -> MemoryClientProtocol:
        if self._memory is None:
            from backend.memory.client import MemoryClient

            self._memory = MemoryClient()
        return self._memory

    @memory.setter
    def memory(self, value: MemoryClientProtocol) -> None:
        self._memory = value

    @property
    def llm(self) -> LLM:
        if self._llm is None:
            from backend.agent.llm import GroqLLM

            self._llm = GroqLLM()
        return self._llm

    @llm.setter
    def llm(self, value: LLM) -> None:
        self._llm = value


def _offline_scan(account: Any) -> list[Resource]:
    """APP_ENV=offline: 'scan' the eval env's medium account instead of AWS."""
    from eval.cloudsense_env.adapter import to_resources
    from eval.cloudsense_env.tasks import TASKS

    return to_resources(TASKS["mid-size-audit"]().load_account_raw(), account_alias=account.alias)


def _default() -> Services:
    from backend.config import settings
    from backend.scanner.scan import scan_account
    from backend.store.db import SessionLocal

    if settings.APP_ENV == "offline":  # no AWS, Hindsight or Groq needed
        from backend.agent.fake_llm import FakeLLM
        from backend.memory.fake import InMemoryMemoryClient

        return Services(session_factory=SessionLocal, _memory=InMemoryMemoryClient(), _llm=FakeLLM(),
                        scan_account=_offline_scan)
    return Services(session_factory=SessionLocal, scan_account=scan_account)


services = _default()
