"""Scan pipeline: scan -> graph -> candidates -> agent -> persist -> notify."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from backend.agent.decide import decide_all
from backend.agent.schema import AgentDecision
from backend.candidates.rules import generate_candidates
from backend.deps import Services
from backend.graph.build import annotate
from backend.scanner.models import Resource
from backend.store import repo
from backend.store.models import Account, CandidateRow, CandidateStatus, Org, ResourceRow, Scan

log = logging.getLogger(__name__)
STATUS_FOR = {"recommend": CandidateStatus.pending, "suppress": CandidateStatus.suppressed,
              "ask": CandidateStatus.asked}
MEMORIES_SHOWN = 3


async def run_scan(svc: Services, scan_id: str, account_ids: list[str] | None = None) -> None:
    with svc.session_factory() as s:
        scan = s.get(Scan, scan_id)
        org = s.get(Org, scan.org_id)
        q = select(Account).where(Account.org_id == org.id)
        if account_ids:
            q = q.where(Account.id.in_(account_ids))
        accounts = list(s.scalars(q))
        errors: list[dict[str, Any]] = []
        progress: dict[str, Any] = {"step": 1, "counts": {}}

        def mark(step: int, **extra: Any) -> None:
            """Live progress for the first-scan screen (steps 1-6, 7 = done)."""
            progress.update(step=step, **extra)
            scan.progress = dict(progress)
            s.commit()

        services = (org.settings_json or {}).get("services")  # None = all
        try:
            resources: list[Resource] = []
            account_of: dict[str, str] = {}
            for acct in accounts:
                mark(1, account=acct.alias)
                try:
                    found = await asyncio.to_thread(svc.scan_account, acct)
                except Exception as e:  # one broken account must not fail the scan
                    log.exception("scan failed for account %s", acct.alias)
                    errors.append({"account": acct.alias, "error": f"{type(e).__name__}: {e}"})
                    continue
                new = [r for r in found if r.id not in account_of]  # same account connected twice
                resources += new
                account_of.update({r.id: acct.id for r in new})
                counts = dict(progress["counts"])
                for r in new:
                    counts[r.type] = counts.get(r.type, 0) + 1
                mark(2, counts=counts)
            mark(4)  # discovery and the 14-day metrics read happen together in scan_account

            graph = annotate(resources)
            mark(5)
            candidates = generate_candidates(resources, graph)
            if services is not None:
                candidates = [c for c in candidates if next((r.type for r in resources if r.id == c.resource_id),
                                                            None) in services]
            mark(6)

            no_memory = False
            try:
                await svc.memory.ensure_bank(org)
            except Exception as e:
                errors.append({"memory": f"Hindsight unavailable, deciding without memory: {e}"})
                no_memory = True
            recalled: dict[str, list] = {}
            decisions: dict[str, AgentDecision] = await decide_all(
                org, candidates, resources, svc.memory, svc.llm, no_memory=no_memory, recalled_out=recalled)

            row_of: dict[str, ResourceRow] = {}
            for r in resources:
                row = ResourceRow(scan_id=scan.id, account_id=account_of.get(r.id), aws_id=r.id, arn=r.arn, type=r.type,
                                  name=r.display_name, tags_json=r.tags, owner_team=r.owner_team,
                                  metrics_json=r.metrics.model_dump(), role_hints_json=r.role_hints,
                                  depends_on_json=r.depends_on, dependents_json=r.dependents,
                                  data_json=r.model_dump(mode="json"))
                s.add(row)
                row_of[r.id] = row
            s.flush()
            cand_rows = []
            for c in candidates:
                d = decisions[c.id]
                row = CandidateRow(id=c.id, scan_id=scan.id, resource_id=row_of[c.resource_id].id, rule_id=c.rule_id,
                                   action=c.action, monthly_saving=c.monthly_saving, signals_text=c.signals_text,
                                   blast_radius=c.blast_radius.model_dump(),
                                   agent_decision_json={**d.model_dump(), "memories": [
                                       m.model_dump() for m in recalled.get(c.id, [])[:MEMORIES_SHOWN]]},
                                   extra_json={"reversible": c.reversible, "warnings": c.warnings},
                                   status=STATUS_FOR[d.decision])
                s.add(row)
                cand_rows.append(row)
            scan.resource_count = len(account_of)  # discovered resources, not synthetic graph nodes
            scan.candidate_count = len(candidates)
            scan.status = "done"
            scan.progress = {**progress, "step": 7}
        except Exception as e:
            log.exception("scan %s failed", scan_id)
            s.rollback()
            scan = s.get(Scan, scan_id)
            scan.status = "failed"
            errors.append({"scan": f"{type(e).__name__}: {e}"})
            cand_rows = []
        scan.errors = errors
        scan.finished_at = datetime.now(UTC)
        repo.log_audit(s, org.id, "cloudsense", "scan_finished" if scan.status == "done" else "scan_failed", {
            "scan_id": scan.id, "resources": scan.resource_count,
            "recommendations": sum(c.status != CandidateStatus.suppressed for c in cand_rows),
            "skipped": sum(c.status == CandidateStatus.suppressed for c in cand_rows),
            "accounts": [a.alias for a in accounts], "errors": len(errors)})
        s.commit()

        to_review = [c for c in cand_rows if c.status in (CandidateStatus.pending, CandidateStatus.asked)]
        if svc.notify_review and to_review:
            try:
                svc.notify_review(org, scan.id, to_review)
            except Exception:
                log.exception("review notification failed")
