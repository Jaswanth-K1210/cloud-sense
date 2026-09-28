"""Offline eval: acceptance rate per scan, with vs without memory (BUILD_DOC section 15).

    python -m eval.run_eval --fake      # in-memory memory + fake LLM, seconds, no network (CI)
    python -m eval.run_eval             # real Hindsight + Groq, fresh bank per run

Writes eval/results/<condition>-seed<seed>.json and eval/results/summary.json.
"""

import argparse
import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.agent.decide import decide_all
from backend.candidates.rules import generate_candidates
from backend.graph.build import annotate
from eval.sequence import generate
from eval.simulated_engineer import SimReviewer, SimulatedEngineer

RESULTS = Path(__file__).parent / "results"
CONDITIONS = ["no_memory", "hindsight"]
SEEDS = [1, 2, 3]


@dataclass
class EvalOrg:
    id: str
    hindsight_bank: str
    name: str = "Eval Org"
    hard_rules: list = field(default_factory=list)


def clients(fake: bool):
    if fake:
        from backend.agent.fake_llm import FakeLLM
        from backend.memory.fake import InMemoryMemoryClient

        return InMemoryMemoryClient(), FakeLLM()
    from backend.agent.llm import GroqLLM
    from backend.memory.client import MemoryClient

    return MemoryClient(), GroqLLM()


async def run_one(condition: str, seed: int, fake: bool, n_scans: int, stamp: int) -> dict[str, Any]:
    memory, llm = clients(fake)
    bank = f"eval-{condition}-{seed}-{stamp}"
    org = EvalOrg(id=bank, hindsight_bank=bank)
    no_memory = condition == "no_memory"
    if not no_memory:
        await memory.ensure_bank(org)
    engineer, reviewer = SimulatedEngineer(seed), SimReviewer()
    per_scan = []
    for spec in generate(seed, n_scans):
        resources = spec.resources
        graph = annotate(resources)
        cands = generate_candidates(resources, graph)
        decisions = await decide_all(org, cands, resources, memory, llm, no_memory=no_memory)
        by_id = {r.id: r for r in resources}
        row = {"scan": spec.index, "candidates": len(cands), "shown": 0, "approved": 0, "rejected": 0,
               "suppressed": 0, "trap_hits": 0, "traps_suppressed": 0, "safe_suppressed": 0,
               "savings_approved": 0.0}
        for c in cands:
            truth = spec.truth.get(c.resource_id)
            is_trap = truth is not None and truth.archetype is not None
            if decisions[c.id].decision == "suppress":
                row["suppressed"] += 1
                row["traps_suppressed" if is_trap else "safe_suppressed"] += 1
                continue
            row["shown"] += 1
            row["trap_hits"] += is_trap
            verdict = engineer.review(c, by_id[c.resource_id], truth)
            if verdict.decision == "approve":
                row["approved"] += 1
                row["savings_approved"] += c.monthly_saving or 0
            else:
                row["rejected"] += 1
            if not no_memory:
                await memory.retain_verdict(org, f"{bank}-scan{spec.index}", c, by_id[c.resource_id], verdict,
                                            reviewer)
        decided = row["approved"] + row["rejected"]
        row["acceptance_rate"] = row["approved"] / decided if decided else None
        row["savings_approved"] = round(row["savings_approved"], 2)
        if not no_memory:
            t0 = time.monotonic()
            row["consolidated"] = await memory.wait_for_consolidation(org, timeout_s=10 if fake else 180)
            row["consolidation_s"] = round(time.monotonic() - t0, 1)
        per_scan.append(row)
    return {"condition": condition, "seed": seed, "bank": bank, "fake": fake, "scans": per_scan}


def summarize(runs: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for cond in CONDITIONS:
        rs = [r for r in runs if r["condition"] == cond]
        if not rs:
            continue
        n = len(rs[0]["scans"])
        rates = [[r["scans"][i]["acceptance_rate"] for r in rs] for i in range(n)]
        out[cond] = {
            "acceptance_mean": [sum(x for x in v if x is not None) / max(1, sum(x is not None for x in v))
                                for v in rates],
            "acceptance_min": [min((x for x in v if x is not None), default=None) for v in rates],
            "acceptance_max": [max((x for x in v if x is not None), default=None) for v in rates],
            "trap_hits_mean": [sum(r["scans"][i]["trap_hits"] for r in rs) / len(rs) for i in range(n)],
        }
    return out


async def main(fake: bool, seeds: list[int], n_scans: int) -> dict[str, Any]:
    RESULTS.mkdir(exist_ok=True)
    stamp = int(time.time())
    runs = []
    for cond in CONDITIONS:
        for seed in seeds:
            run = await run_one(cond, seed, fake, n_scans, stamp)
            (RESULTS / f"{cond}-seed{seed}.json").write_text(json.dumps(run, indent=2))
            rates = [s["acceptance_rate"] for s in run["scans"]]
            print(f"{cond:10s} seed {seed}: acceptance " + " ".join("-" if r is None else f"{r:.0%}" for r in rates))
            runs.append(run)
    summary = {**summarize(runs), "meta": {"fake": fake, "seeds": seeds, "scans": n_scans, "stamp": stamp}}
    (RESULTS / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--fake", action="store_true", help="in-memory memory + fake LLM (no network)")
    p.add_argument("--seeds", type=int, nargs="+", default=SEEDS)
    p.add_argument("--scans", type=int, default=10)
    a = p.parse_args()
    asyncio.run(main(a.fake, a.seeds, a.scans))
