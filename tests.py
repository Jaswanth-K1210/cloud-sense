"""End-to-end simulation of the CloudSense demo story, through the real REST API.

    python tests.py            # offline: moto AWS + in-memory memory + fake LLM (free, ~1 min)
    python tests.py --live     # moto AWS + REAL Hindsight and Groq from .env (checks your keys)

AWS is always simulated with moto: nothing is created in a real account and nothing costs money.
The story (BUILD_DOC section 17 / Prompt 16, minus real AWS):
  seed the sandbox estate -> connect account -> scan -> directive suppression -> reject the standby
  with a reason -> learning -> launch an untagged look-alike -> rescan -> look-alike suppressed with a citation
  -> approve + dry run -> real stop + undo -> IaC diff -> rules / playbook / ask / metrics / graph -> eval harness.
Exit code 0 when every check passes.
"""

import argparse
import asyncio
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import boto3
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "infra" / "sandbox-seed"))

import launch_lookalike  # noqa: E402
import seed as sandbox  # noqa: E402

from backend.app import app  # noqa: E402
from backend.deps import services  # noqa: E402
from backend.store.db import get_session, init_db, make_engine  # noqa: E402
from backend.store.models import Account, Org  # noqa: E402
from backend.store.seed_demo import seed as seed_demo  # noqa: E402

REGION = "us-east-1"
ADMIN = {"X-User-Id": "u-admin"}
REVIEWER = {"X-User-Id": "u-reviewer"}
REJECT_REASON = "DR standby for orders-db, idle on purpose"


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def check(self, name: str, ok: bool, detail: str = "", soft: bool = False) -> bool:
        status = "PASS" if ok else ("WARN" if soft else "FAIL")
        self.rows.append((status, name, detail))
        print(f"  {status:4s}  {name}" + (f"  ({detail})" if detail else ""), flush=True)
        return ok

    @property
    def failed(self) -> int:
        return sum(s == "FAIL" for s, _, _ in self.rows)


def put_cpu(cw, instance_id: str, spiky: bool = False) -> None:
    now = datetime.now(UTC)
    data = []
    for h in range(1, 72):
        value = 90.0 if spiky and h in (20, 21, 44, 45) else 0.4
        data.append({"MetricName": "CPUUtilization", "Dimensions": [{"Name": "InstanceId", "Value": instance_id}],
                     "Timestamp": now - timedelta(hours=h), "Value": value})
    for i in range(0, len(data), 20):
        cw.put_metric_data(Namespace="AWS/EC2", MetricData=data[i:i + 20])


def by_name(scan: dict, *sections: str) -> dict[str, dict]:
    return {c["resource"]["name"]: c for s in sections for c in scan[s]}


def run_scan(client: TestClient) -> dict:
    sid = client.post("/orgs/acme/scans", headers=REVIEWER).json()["scan_id"]
    return client.get(f"/orgs/acme/scans/{sid}", headers=REVIEWER).json()


def wait_learned(client: TestClient, verdict_id: str, timeout_s: float) -> dict:
    deadline = time.monotonic() + timeout_s
    while True:
        v = client.get(f"/verdicts/{verdict_id}", headers=REVIEWER).json()
        if v["learning_status"] != "learning" or time.monotonic() > deadline:
            return v
        time.sleep(2)


def simulate(live: bool, r: Report) -> None:
    engine = make_engine("sqlite://")
    init_db(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    stamp = int(time.time())
    with factory() as s:
        seed_demo(s)
        s.get(Org, "acme").hindsight_bank = f"sim-{stamp}"  # fresh bank, never pollutes a real one
        s.get(Account, "acct-sandbox").action_role_arn = "local"
        s.commit()

    def session_override():
        with factory() as s:
            yield s

    if live:
        from backend.agent.llm import GroqLLM
        from backend.memory.client import MemoryClient

        services.memory, services.llm = MemoryClient(), GroqLLM()
    else:
        from backend.agent.fake_llm import FakeLLM
        from backend.memory.fake import InMemoryMemoryClient

        services.memory, services.llm = InMemoryMemoryClient(), FakeLLM()
    services.session_factory = factory
    services.notify_review = None
    app.dependency_overrides[get_session] = session_override
    client = TestClient(app)

    print("\n[1] Sandbox estate (moto) + connection")
    ec2 = boto3.client("ec2", region_name=REGION)
    cw = boto3.client("cloudwatch", region_name=REGION)
    ami = ec2.describe_images(Owners=["amazon"])["Images"][0]["ImageId"]
    ids = sandbox.seed(REGION, ami=ami)
    for name in sandbox.INSTANCES:
        put_cpu(cw, ids[name], spiky=name == "payroll-batch-worker")
    r.check("sandbox seeded", set(sandbox.INSTANCES) <= set(ids), f"{len(ids)} resources")
    org = client.get("/orgs/acme", headers=ADMIN).json()
    r.check("org + seeded account visible", len(org["accounts"]) == 1, f"ExternalId {org['external_id'][:8]}…")
    r.check("viewer without header is refused", client.get("/orgs/acme").status_code == 401)

    print("\n[2] First scan")
    t0 = time.monotonic()
    scan1 = run_scan(client)
    r.check("scan finished", scan1["status"] == "done",
            f"{scan1['resource_count']} resources, {scan1['candidate_count']} candidates, "
            f"{time.monotonic() - t0:.1f}s, errors={scan1['errors']}")
    shown = by_name(scan1, "recommended", "asked")
    suppressed = by_name(scan1, "suppressed")
    r.check("orders-db-standby shown to a human (no memory yet)", "orders-db-standby" in shown,
            shown.get("orders-db-standby", {}).get("agent", {}).get("decision", "missing"))
    od_reason = suppressed.get("orders-db", {}).get("agent", {}).get("reason", "missing")
    r.check("orders-db (do_not_terminate) suppressed by directive", od_reason.startswith("Directive:"), od_reason)
    standby = shown.get("orders-db-standby") or {}
    r.check("savings priced (t4g)", (standby.get("monthly_saving") or 0) > 0, f"${standby.get('monthly_saving')}")

    print("\n[3] Reject with a reason -> memory")
    if not standby:
        r.check("reject step", False, "orders-db-standby was not shown, cannot reject")
        return
    v = client.post(f"/candidates/{standby['id']}/verdict", headers=REVIEWER,
                    json={"decision": "reject", "reason": REJECT_REASON, "scope": "similar"})
    r.check("verdict accepted", v.status_code == 201, v.text[:120] if v.status_code != 201 else "")
    t0 = time.monotonic()
    verdict = wait_learned(client, v.json()["id"], timeout_s=200 if live else 5)
    learned = verdict["learning_status"] == "learned"
    r.check("consolidation finished", learned,
            f"{verdict['learning_status']} after {time.monotonic() - t0:.0f}s", soft=live)
    r.check("learned rule matches the reason", bool(verdict.get("learned_rule")),
            (verdict.get("learned_rule") or {}).get("text", "no matching observation yet"), soft=live)
    rules = client.get("/orgs/acme/rules", headers=REVIEWER).json()
    r.check("Learned Rules page has a rule", len(rules) > 0, f"{len(rules)} rule(s)", soft=live)

    print("\n[4] Untagged look-alike appears -> rescan")
    look = launch_lookalike.launch(REGION, ami=ami)
    put_cpu(cw, look)
    scan2 = run_scan(client)
    s2 = by_name(scan2, "suppressed")
    pay = s2.get("payments-db-standby")
    r.check("payments-db-standby SUPPRESSED on first sight", pay is not None,
            (pay or by_name(scan2, "recommended", "asked").get("payments-db-standby", {})).get("agent", {})
            .get("reason", "not found"))
    r.check("…and it cites a past decision", bool(pay and pay["agent"]["cited_memory_ids"]),
            ", ".join(pay["agent"]["cited_memory_ids"]) if pay else "")
    if pay:
        why = client.post(f"/candidates/{pay['id']}/why", headers=REVIEWER).json()
        r.check("Why? answers with sources", bool(why["text"]) and len(why["based_on"]) > 0,
                why["text"][:100].replace("\n", " "))
    r.check("dev-sandbox-3 still recommended (no over-suppression)",
            "dev-sandbox-3" in by_name(scan2, "recommended", "asked"))

    print("\n[5] Approve -> dry run -> real stop -> undo")
    dev = by_name(scan2, "recommended", "asked").get("dev-sandbox-3")
    if dev:
        client.post(f"/candidates/{dev['id']}/verdict", headers=REVIEWER, json={"decision": "approve"})
        dry = client.post(f"/candidates/{dev['id']}/execute", headers=REVIEWER).json()
        r.check("dry run returns the exact AWS calls", dry.get("status") == "dry_run",
                " -> ".join(c["op"] for c in dry.get("api_calls", [])))
        from backend.actions.executor import execute
        from backend.actions.undo import undo
        from backend.store.models import CandidateRow

        with factory() as s:
            act = execute(s, s.get(CandidateRow, dev["id"]), actor="u-reviewer", dry_run=False)
            state = ec2.describe_instances(InstanceIds=[ids["dev-sandbox-3"]])["Reservations"][0]["Instances"][0][
                "State"]["Name"]
            r.check("real stop: snapshot first, instance stopped", state == "stopped" and bool(act.pre_snapshot_ids),
                    f"state={state}, snapshots={len(act.pre_snapshot_ids)}")
            undo(s, act, actor="u-reviewer")
            state = ec2.describe_instances(InstanceIds=[ids["dev-sandbox-3"]])["Reservations"][0]["Instances"][0][
                "State"]["Name"]
            r.check("undo restarts it", state in ("pending", "running"), f"state={state}")
    else:
        r.check("dev-sandbox-3 available to approve", False)

    ci = by_name(scan2, "recommended", "asked").get("ci-runner-old")
    if ci:
        client.post(f"/candidates/{ci['id']}/verdict", headers=REVIEWER, json={"decision": "approve"})
        act = client.post(f"/candidates/{ci['id']}/execute", headers=REVIEWER).json()
        r.check("Terraform-managed ci-runner-old gets a diff, not a change", act.get("kind") == "iac_diff")
    else:
        r.check("ci-runner-old (terraform) shown", False, "not in recommended/asked", soft=True)

    print("\n[6] Dashboard endpoints")
    for path in ("/orgs/acme/metrics", "/orgs/acme/playbook", f"/graph/{scan2['id']}", "/templates"):
        code = client.get(path, headers=REVIEWER).status_code
        r.check(f"GET {path.replace(scan2['id'], '<scan>')}", code == 200, str(code))
    ask = client.post("/orgs/acme/ask", headers=REVIEWER, json={"question": "Which standbys must we never stop?"})
    r.check("POST /ask (reflect)", ask.status_code == 200, ask.json().get("text", "")[:100].replace("\n", " "))
    m = client.get("/orgs/acme/metrics", headers=REVIEWER).json()
    r.check("metrics track the rejection", m["series"][0]["rejected"] >= 1,
            f"scan acceptance: {[s['acceptance_rate'] for s in m['series']]}")
    app.dependency_overrides.clear()


def eval_harness(r: Report) -> None:
    print("\n[7] Eval harness (offline, 1 seed x 4 scans)")
    import eval.run_eval as run_eval

    out = ROOT / ".sim-eval"
    run_eval.RESULTS = out
    summary = asyncio.run(run_eval.main(fake=True, seeds=[1], n_scans=4))
    mem, base = summary["hindsight"]["trap_hits_mean"][-1], summary["no_memory"]["trap_hits_mean"][-1]
    r.check("memory reduces trap hits by the last scan", mem < base, f"{mem:.0f} vs {base:.0f} without memory")
    for f in out.glob("*.json"):
        f.unlink()
    out.rmdir()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--live", action="store_true", help="use real Hindsight + Groq from .env (AWS stays simulated)")
    a = p.parse_args()
    import os

    os.environ.update({"AWS_ACCESS_KEY_ID": "testing", "AWS_SECRET_ACCESS_KEY": "testing",
                       "AWS_SESSION_TOKEN": "testing", "AWS_DEFAULT_REGION": REGION})
    os.environ.pop("AWS_PROFILE", None)
    print(f"CloudSense simulation ({'LIVE Hindsight + Groq' if a.live else 'offline fakes'}, AWS simulated by moto)")
    r = Report()
    t0 = time.monotonic()
    with mock_aws():
        try:
            simulate(a.live, r)
        except Exception as e:  # report instead of a bare traceback
            r.check("simulation ran to the end", False, f"{type(e).__name__}: {e}")
    eval_harness(r)
    passed = sum(s == "PASS" for s, _, _ in r.rows)
    warned = sum(s == "WARN" for s, _, _ in r.rows)
    print(f"\n{passed} passed, {warned} warnings, {r.failed} failed in {time.monotonic() - t0:.0f}s")
    return 1 if r.failed else 0


if __name__ == "__main__":
    sys.exit(main())
