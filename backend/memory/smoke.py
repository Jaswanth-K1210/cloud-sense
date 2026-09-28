"""Manual smoke test against REAL Hindsight (not run by pytest).

    python -m backend.memory.smoke

Creates bank "smoke-<ts>", retains 2 verdicts, waits for consolidation, recalls, prints observations,
the playbook and the consolidation latency.
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from backend.candidates.rules import Candidate
from backend.memory.client import MemoryClient
from backend.scanner.models import Resource


@dataclass
class _Org:
    id: str
    name: str = "Smoke Org"
    hindsight_bank: str = ""
    hard_rules: list = field(default_factory=list)


@dataclass
class _Verdict:
    decision: str
    reason: str
    scope: str = "similar"
    at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class _Reviewer:
    id: str = "u-smoke"
    name: str = "Smoke Reviewer"
    team: str = "platform"


def _pair(name: str, source: str) -> tuple[Candidate, Resource]:
    res = Resource(id=name, type="rds", name=name, account_alias="sandbox", owner_team="orders",
                   role_hints=["standby", f"replica_of:{source}", "flat_zero"], depends_on_names=[source])
    cand = Candidate(resource_id=name, rule_id="R7", action="stop", monthly_saving=49.64,
                     signals_text="14-day max DatabaseConnections = 0", reversible=True)
    return cand, res


async def main() -> None:
    ts = int(time.time())
    org = _Org(id=f"smoke-{ts}", hindsight_bank=f"smoke-{ts}")
    mc = MemoryClient()
    await mc.ensure_bank(org)
    for name, src in [("orders-db-standby", "orders-db"), ("billing-db-standby", "billing-db")]:
        cand, res = _pair(name, src)
        await mc.retain_verdict(org, "smoke-scan", cand, res,
                                _Verdict("reject", f"DR standby for {src}, idle on purpose"), _Reviewer())
    t0 = time.monotonic()
    done = await mc.wait_for_consolidation(org, timeout_s=180)
    elapsed = time.monotonic() - t0
    cand, res = _pair("payments-db-standby", "payments-db")
    print("recall:", [h.text[:100] for h in await mc.recall_for(org, cand, res)])
    for r in await mc.list_rules(org):
        print(f"rule ({r.proof_count}x): {r.text}")
    print("playbook:\n", (await mc.get_playbook(org)).content)
    print(f"consolidation {'done' if done else 'TIMEOUT'} in {elapsed:.1f}s (bank {org.hindsight_bank})")


if __name__ == "__main__":
    asyncio.run(main())
