"""Scheduled scans: orgs whose settings say "daily" or "weekly" get a scan when the last one is older than that."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from backend.deps import Services
from backend.pipeline import run_scan
from backend.store import repo
from backend.store.models import Org, Scan

log = logging.getLogger(__name__)
PERIOD = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}
CHECK_EVERY_S = 600


def due_orgs(svc: Services, now: datetime) -> list[str]:
    due = []
    with svc.session_factory() as s:
        for org in s.scalars(select(Org)):
            period = PERIOD.get((org.settings_json or {}).get("schedule", "manual"))
            if not period or not (org.settings_json or {}).get("onboarded"):
                continue
            last = s.scalars(select(Scan).where(Scan.org_id == org.id).order_by(Scan.started_at.desc())).first()
            started = last.started_at.replace(tzinfo=last.started_at.tzinfo or UTC) if last else None
            if last is None or (last.status != "running" and now - started >= period):
                due.append(org.id)
    return due


async def run_due(svc: Services) -> list[str]:
    started = []
    for org_id in due_orgs(svc, datetime.now(UTC)):
        with svc.session_factory() as s:
            scan = repo.create_scan(s, org_id)
            s.commit()
            scan_id = scan.id
        started.append(org_id)
        await run_scan(svc, scan_id)
    return started


async def loop(svc: Services) -> None:
    # ponytail: in-process timer; one API replica only. Use a real cron/queue when running several.
    while True:
        try:
            await run_due(svc)
        except Exception:
            log.exception("scheduled scan check failed")
        await asyncio.sleep(CHECK_EVERY_S)
