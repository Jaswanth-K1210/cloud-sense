# CloudSense: Build Document

**An AWS cost agent that learns your organization's unwritten rules from every rejected recommendation, built on Hindsight agent memory.**

> Status: v1 build spec, ready for implementation.
> Owner: Jaswanth Koppisetty.
> Stack: Python 3.11, FastAPI, React + Vite, SQLite (demo) or Postgres (production), boto3, Slack Bolt, Hindsight (Python client), Groq.
>
> Lines marked **⚠ VERIFY** use an API signature that has not been checked against the SDK. Check each against the Hindsight docs before coding it.

---

## 0. One-liner and pitch

**One line:** *Cost tools tell you what to delete. CloudSense learns what you'll never let it delete.*

**Pitch:**
- Every cloud cost tool recommends deletions, and engineers ignore most of them. The tool doesn't know that the "idle" box is the disaster-recovery standby, or that the "overprovisioned" worker spikes at month-end payroll.
- Each bad recommendation erodes trust, until nobody reads the Slack channel.
- CloudSense turns every "No, because…" from an engineer into a durable, evidence-backed rule stored in Hindsight.
- It applies that rule to resources it has never seen, including untagged ones.
- Its recommendations get more trustworthy every week, and you can measure it: acceptance rate goes up and false alarms go down.

---

## 1. Problem and insight

| | |
|---|---|
| **Problem** | Recommendation engines are context-blind. They see CPU, not purpose. Engineers reject or ignore them, and savings are never realized. |
| **Why now** | AWS, Vantage, nOps and Sedai all ship FinOps agents (Section 2). The detection layer is commoditized. The **trust layer** is not. |
| **Insight** | The missing context already exists: it's in the engineers' heads, and it comes out every time they reject a recommendation. Nobody captures it. |
| **Mechanism** | Rejection reason → Hindsight `retain` → observations (consolidated rules with evidence counts) → `recall` and the playbook mental model at decision time. |
| **Proof** | Recommendation acceptance rate over time, with memory vs without. Measured offline in the eval harness (Section 15) and live in the product. |

---

## 2. Market scan: tools like this today

Accessed September 2026. Verify before the pitch.

| Tool | What it does | Human approval | Learns org context? | Gap CloudSense targets |
|---|---|---|---|---|
| **AWS Cost Optimization Hub / Compute Optimizer / Trusted Advisor** | Free, native. Consolidates rightsizing, idle-resource, Graviton and commitment recommendations across accounts. | Recommendations only; no execution | No. Trusted Advisor has a manual resource-exclusion API on paid support tiers. | Context-blind; data lag of up to ~72h reported |
| **AWS FinOps Agent** (public preview, Jun 2026, us-east-1) | Anomaly root-causing via CloudTrail; natural-language cost Q&A; recurring reports; pushes Cost Optimization Hub recommendations into Jira and Slack | Tickets for humans | **Partly.** You *upload* context files (owner mappings, known exceptions, tagging conventions); it remembers preferences. | Context is authored manually. CloudSense **learns it from rejections.** |
| **Vantage FinOps Agent** | Slack-native agent; scans for waste; remediates things like unattached EBS and orphaned snapshots; buys commitments | Optional approval mode in Slack | Not advertised | Approval exists, but the approval signal isn't turned into reusable rules |
| **nOps Clara** | FinOps agent (Bedrock AgentCore with memory); reports, allocation, commitment automation | Mixed | Conversational memory | Focuses on analytics and commitments, not learned exceptions |
| **Sedai** | Autonomous optimization using reinforcement learning on workload behavior; copilot → autopilot modes | Copilot mode | Learns *metric* behavior | Learns from telemetry, not from *human reasons*. Enterprise-priced. |
| **Amnic, Cloudgov.ai, Harness CCM, Wiv, CloudZero, ProsperOps** | Visibility, approval-gated remediation, auto-stopping, workflows, commitments | Varies | Mostly rules you configure | Rules are hand-written |

**Honest positioning:**
- Detection, Slack approvals and even "agentic remediation" already exist. Don't pitch any of those as new.
- The defensible differentiators are:
  1. **Learned rules from rejection reasons**, with provenance (who taught it, when, how many confirmations), generalizing to untagged look-alikes.
  2. **Blast-radius awareness** from a real dependency graph.
  3. The learned rules as an **exportable, versioned playbook**.
- **Product direction:** long term, CloudSense can sit *on top of* existing recommenders (import Cost Optimization Hub recommendations) as a trust and memory layer, instead of competing on detection.
- **Name check:** "CloudSense" is, as far as I know, already used by a commerce/CPQ software company. Check the trademark before any public launch.

---

## 3. v1 scope

### In scope
- **AWS only, one or more regions.** Services: EC2, EBS, EBS snapshots, Elastic IPs, RDS, S3.
- **Read-only cross-account role** (CloudFormation, ExternalId). A separate *opt-in* action role.
- **Deterministic candidate rules** (Section 6.4) with pricing from a bundled `aws_pricing.json`.
- **Agent review** with Hindsight: recall, playbook, directives, then a decision with citations.
- **Slack approve/reject** (Socket Mode, so no public URL is needed), plus a web dashboard.
- **Reversible actions only:** stop, snapshot, tag, gp2→gp3. Delete only after approval **and** a snapshot.
- **Learned Rules page:** observations with evidence, delete/override (admin), playbook with version history.
- **Eval harness:** the old CloudSense RL environment reused as an offline benchmark.

### Out of scope for v1 (roadmap)
Azure/GCP, Kubernetes, commitment purchasing, autonomous mode, Jira, SSO, billing.

---

## 4. Architecture

```
                    ┌──────────────────────── Customer AWS account(s) ────────────────────────┐
                    │  CloudSenseReadOnlyRole (+ optional CloudSenseActionRole)               │
                    └───────────────▲─────────────────────────────────────────▲───────────────┘
                                    │ STS AssumeRole (ExternalId)             │ approved actions only
┌───────────────────────────────────┴─────────────────────────────────────────┴──────────────┐
│ CloudSense backend (FastAPI)                                                                │
│                                                                                             │
│  scanner/        → describe resources + CloudWatch 14d metrics → Resource models            │
│  graph/          → dependency edges → blast-radius BFS (reused from CloudSense env)         │
│  candidates/     → deterministic waste rules + pricing → Candidate list                     │
│  agent/          → for each candidate: Hindsight recall + playbook → LLM decision           │
│  review/         → Slack (Bolt, Socket Mode) + REST for dashboard → Verdict                 │
│  memory/         → Hindsight wrapper: retain_verdict / recall_for / playbook / reflect      │
│  actions/        → snapshot → stop/modify → tag → undo (IaC-managed → Terraform diff only)  │
│  store/          → SQLite/Postgres: scans, candidates, verdicts, actions, audit log         │
└──────────────┬───────────────────────────────┬──────────────────────────────────────────────┘
               │ retain / recall / reflect     │ JSON mode
        ┌──────▼──────────┐              ┌─────▼──────────────┐
        │ Hindsight Cloud │              │ Groq LLM           │
        │ bank per org    │              │ gpt-oss-120b agent │
        └─────────────────┘              └────────────────────┘
               ▲
┌──────────────┴──────────────────────────────────────────┐
│ React dashboard: Overview · Queue · Graph · Learned Rules │
│ · Playbook · Ask · Settings                               │
└──────────────────────────────────────────────────────────┘
```

**Core loop:** Scan → Candidates → Agent (recall + playbook) → Human verdict → **Retain** → Hindsight consolidates observations → playbook refreshes → next scan is smarter.

---

## 5. Hindsight integration (the heart of the product)

### 5.1 Concept mapping

| Hindsight concept | CloudSense usage |
|---|---|
| **Memory bank** | One bank per customer org: `org-{org_id}`. This is tenant isolation. |
| **Mission** | "I review AWS cost-saving recommendations for {Org}. I prioritize not breaking production over saving money." |
| **Directives** | The customer's *written* hard rules from the Settings page, e.g. "Never recommend terminating resources tagged do_not_terminate", "Never touch prod RDS". |
| **Disposition** | High skepticism, high literalism. |
| **retain (world facts)** | Facts about resources ("orders-db-standby replicates orders-db") |
| **retain (experience facts)** | "I recommended stopping X; the engineer rejected it because…" |
| **Observations** | **Learned rules**, with proof count, source quotes and history. Shown on the Learned Rules page. |
| **Mental model** | `org-playbook`: the living "what we never touch and why" document |
| **recall** | Before every decision: memories relevant to this resource (all four search strategies run) |
| **reflect** | The "Ask" page and "Why did you skip this?", with `based_on` citations |
| **Tags + observation_scopes** | Per-account and per-team rules, plus org-wide rules that transfer to new accounts |
| **Bank templates** | Cold-start pack of common exceptions a new customer can accept |
| **Memory Defense** | Poisoning protection: only reviewers can teach, provenance is visible, admins can delete |

### 5.2 Setup (one-time per org)

```python
# memory/setup.py
from hindsight_client import Hindsight
hs = Hindsight(base_url=HINDSIGHT_BASE_URL)  # ⚠ VERIFY: Cloud auth (api key header/param)

BANK = f"org-{org_id}"

# Mission / directives / disposition, via the Memory Banks API or the control plane UI.
# ⚠ VERIFY exact method name and fields: https://hindsight.vectorize.io/developer/api/memory-banks
hs.create_bank(bank_id=BANK,
    mission="I review AWS cost-saving recommendations for Acme. "
            "Breaking production is worse than missing a saving.",
    directives=["Never recommend terminating or stopping resources tagged do_not_terminate=true",
                "Never recommend actions on resources tagged compliance:*  without flagging for review"],
    disposition={"skepticism": 5, "literalism": 4, "empathy": 2})

# Playbook mental model: auto-refreshes after consolidation, delta mode keeps it stable
hs.create_mental_model(
    bank_id=BANK, id="org-playbook", name="Org Cost Playbook",
    source_query="Which AWS resources or resource patterns must never be stopped, deleted "
                 "or rightsized in this organization, and why? Include evidence.",
    trigger={"refresh_after_consolidation": True, "mode": "delta", "keep_trace": True,
             "response_schema": {"type": "object", "properties": {
                 "protected_patterns": {"type": "array", "items": {"type": "object", "properties": {
                     "pattern": {"type": "string"}, "reason": {"type": "string"},
                     "applies_to": {"type": "string"}}}},
                 "safe_patterns": {"type": "array", "items": {"type": "string"}}},
                 "required": ["protected_patterns"]}})
# Keep it UNTAGGED. Tagged mental models default to all_strict matching and can refresh to empty.
```

### 5.3 Retain: every human verdict (approvals too)

Approvals teach "this pattern is safe"; rejections teach "this pattern is protected". Both matter.

```python
# memory/client.py
def retain_verdict(org, scan, cand, verdict, reviewer):
    content = (
        f"Reviewer {reviewer.name} ({reviewer.team}) at {verdict.at.isoformat()}:\n"
        f"CloudSense proposed: {cand.action} on {cand.resource.name} ({cand.resource.id}, "
        f"{cand.resource.type}, account {cand.resource.account_alias}).\n"
        f"Signals: {cand.signals_text}. Estimated saving ${cand.monthly_saving:.0f}/month.\n"
        f"Dependencies: {', '.join(cand.resource.depends_on_names) or 'none'}; "
        f"dependents: {', '.join(cand.resource.dependent_names) or 'none'}.\n"
        f"Verdict: {verdict.decision.upper()}. Reason: {verdict.reason}\n"
        f"Scope stated by reviewer: {verdict.scope}"   # 'this resource' | 'all similar resources'
    )
    hs.retain(
        bank_id=f"org-{org.id}",
        content=content,
        context="engineer review of an AWS cost-optimization recommendation",
        timestamp=verdict.at.isoformat(),
        document_id=f"verdict-{cand.id}",          # idempotent: re-review replaces, never duplicates
        tags=[f"account:{cand.resource.account_alias}", f"team:{cand.resource.owner_team}",
              f"rtype:{cand.resource.type}"],
        metadata={"candidate_id": cand.id, "resource_id": cand.resource.id,
                  "decision": verdict.decision, "reviewer_id": reviewer.id, "scan_id": scan.id},
        entities=[{"text": cand.resource.name},
                  *[{"text": n} for n in cand.resource.depends_on_names + cand.resource.dependent_names],
                  *([{"text": cand.resource.service}] if cand.resource.service else [])],
        # Org-wide rule + per-account + per-team observations.
        # "shared"-style empty scope = untagged observation visible to every recall.
        observation_scopes=[[], [f"account:{cand.resource.account_alias}"],
                            [f"team:{cand.resource.owner_team}"]],   # ⚠ VERIFY custom-scope syntax
    )
```

**Why this format:**
- `context` shapes fact extraction.
- `timestamp` enables temporal recall ("month-end").
- `entities` ties the verdict into the graph, so "payroll" links different resources.
- `document_id` makes retain idempotent.
- An empty observation scope means org-level rules form and **transfer to new accounts**.

### 5.4 Recall: before every decision

```python
async def recall_for(org, cand):
    q = (f"{cand.action} {cand.resource.type} {cand.resource.name}; "
         f"role hints: {cand.resource.role_hints}; signals: {cand.signals_text}; "
         f"connected to: {', '.join(cand.resource.neighbor_names)}")
    return await hs.arecall(bank_id=f"org-{org.id}", query=q,
                            tags=[f"account:{cand.resource.account_alias}"], tags_match="any",
                            max_tokens=1500)   # ⚠ VERIFY async method + tag params
```

- Run recalls **in parallel** (`asyncio.gather`, with a concurrency limit of about 8).
- Untagged (org-level) observations match every tag filter.
- `role_hints` come from names, tags and graph position (e.g. `replica_of:orders-db`, `in_asg:false`, `no_inbound_traffic`). This is what lets rules **generalize to untagged look-alikes**.

### 5.5 Playbook: at the start of every scan

```python
pb = hs.get_mental_model(bank_id=BANK, mental_model_id="org-playbook")
playbook_text = pb.content                        # goes into the agent's system prompt
protected = pb.reflect_response.structured_output # for the UI chips   ⚠ VERIFY field path
```

The **Playbook page** shows the version history (`get_mental_model_history`), so viewers can watch rules being added over time.

### 5.6 Reflect: explanations and Q&A

```python
ans = hs.reflect(bank_id=BANK,
    query=f"Why should or shouldn't we stop {res.name}? Cite past decisions.")
# show ans.text + ans.based_on (source memories) in the "Why?" drawer
```

The **Ask page** is free-form: "Can we downsize the payroll workers?" or "What did the payments team tell us not to touch?"

### 5.7 Consolidation timing (critical)

- Observations are consolidated **asynchronously** by a Hindsight worker.
- After a review batch, poll the operations endpoint until consolidation completes, then refresh the playbook. Show a "Learning…" spinner in the UI.
- **Measure this latency on day zero.** If it's slow, the live demo waits on a spinner.
- For the demo, set `min_refresh_interval_seconds: 0` on the playbook.

### 5.8 Memory safety (Memory Defense)

- Only users with the `reviewer` or `admin` role can submit verdicts. `reviewer_id` is stored in metadata.
- **Learned Rules page:** each observation shows its proof count and source verdicts (who, when, quote).
- Admins can **delete** a memory through the Memories API, which removes a poisoned rule.
- Directives always win over learned rules, and the agent prompt states this explicitly.
- Rejections that contradict an existing rule are flagged "rule conflict" in the UI. Hindsight keeps the history.

### 5.9 Cold start

- Ship a **bank template** of about 10 common exceptions: DR standbys, month-end batch jobs, legally required archives, blue/green standbys, license-pinned hosts, on-call debug hosts, CI runners, bastions, NAT instances, log shippers.
- On onboarding, the customer accepts or discards each one. Accepted ones are retained as `context="org policy seed"`.
- ⚠ VERIFY the Bank Templates API: https://hindsight.vectorize.io/developer/api/bank-templates

---

## 6. AWS integration

### 6.1 Onboarding (CloudFormation, one click)

`infra/cloudsense-readonly.yaml` creates `CloudSenseReadOnlyRole`:
- Trusts CloudSense's AWS principal.
- Requires the condition `sts:ExternalId = <per-org random UUID>`.
- Uses the read-only policy in 6.2.

The customer launches it from a "Launch Stack" URL and pastes the role ARN back. **CloudSense stores no credentials**, only the role ARN and ExternalId.

### 6.2 Read-only permissions

```
ec2:DescribeInstances, ec2:DescribeVolumes, ec2:DescribeSnapshots, ec2:DescribeImages,
ec2:DescribeAddresses, ec2:DescribeSecurityGroups, ec2:DescribeNetworkInterfaces, ec2:DescribeTags,
autoscaling:DescribeAutoScalingGroups,
elasticloadbalancing:DescribeLoadBalancers, elasticloadbalancing:DescribeTargetGroups,
elasticloadbalancing:DescribeTargetHealth,
rds:DescribeDBInstances, rds:DescribeDBClusters, rds:ListTagsForResource,
s3:ListAllMyBuckets, s3:GetBucketLocation, s3:GetBucketTagging, s3:GetLifecycleConfiguration,
cloudwatch:GetMetricData, cloudwatch:ListMetrics,
tag:GetResources,
# optional
ce:GetCostAndUsage, cost-optimization-hub:ListRecommendations, compute-optimizer:GetEC2InstanceRecommendations
```

### 6.3 Action role (opt-in, separate stack)

```
ec2:StopInstances, ec2:StartInstances, ec2:CreateSnapshot, ec2:CreateTags,
ec2:ModifyVolume, ec2:DeleteVolume (only with tag condition cloudsense:approved=true),
rds:StopDBInstance, rds:StartDBInstance, rds:CreateDBSnapshot, rds:AddTagsToResource
```

### 6.4 Candidate rules (deterministic, no LLM)

| ID | Rule | Signal (14-day window) | Proposed action | Reversible? |
|---|---|---|---|---|
| R1 | Idle EC2 | avg CPU < 5% **and** max CPU < 20% **and** network in+out < 5 MB/day | Stop (snapshot the EBS volumes first) | ✅ start |
| R2 | Oversized EC2 | p95 CPU < 40% and memory unknown | Rightsize one size down, same family | ✅ resize back |
| R3 | Unattached EBS | state=`available` for > 7 days | Snapshot, then delete (after approval) | ✅ restore from snapshot |
| R4 | gp2 volume | volumeType=`gp2` | Modify to gp3 | ⚠ one modification per volume per 6h |
| R5 | Old snapshot | age > 90 days, not referenced by an AMI | Flag for delete | ❌ (approval + 2nd confirm) |
| R6 | Idle Elastic IP | not associated | Release | ❌ (address lost) |
| R7 | Idle RDS | max DatabaseConnections = 0 | Snapshot, then stop | ⚠ **AWS auto-restarts stopped RDS after 7 days** |
| R8 | S3 without lifecycle | no lifecycle config and size > threshold | Recommend Intelligent-Tiering rule | recommend-only in v1 |

Savings come from `aws_pricing.json` (from the CloudSense RL environment). Show savings as estimates; Cost Explorer reconciliation is on the roadmap.

### 6.5 Dependency graph (for blast radius)

Edges:
- EBS → EC2 (attachment)
- EC2 → target group → load balancer
- EC2 ∈ Auto Scaling group
- RDS read replica → source DB
- Security group → security group references
- Elastic IP → instance/ENI
- Snapshot → volume / AMI
- Tag `depends-on` (customer-declared)

Blast radius = BFS over **dependents**, reusing the existing `blast_radius()` from the RL environment. Show it on the candidate card and weigh it in the agent prompt.

### 6.6 Role hints (generalization fuel)

Derived per resource and fed to both recall and the agent:
- **Name tokens:** `standby`, `replica`, `dr`, `backup`, `batch`, `payroll`, `archive`, `audit`, `bastion`, `runner`.
- **Graph facts:** `replica_of:X`, `in_asg`, `behind_lb`, `no_dependents`.
- **Traffic shape:** `periodic_spikes` (e.g. monthly), `flat_zero`.
- **Tags:** `created_by:terraform` → IaC-managed.

---

## 7. Agent design

### 7.1 Per-candidate decision (JSON mode)

**System prompt (abridged):**

```
You review AWS cost recommendations for {org}. Directives (never violate): {directives}.
Org playbook (learned from engineers): {playbook_text}.
For each candidate you get: resource facts, signals, role hints, blast radius, and MEMORIES
recalled from past engineer decisions. Learned rules override raw utilization signals.
If a memory indicates the resource or a look-alike is protected, SUPPRESS and cite it.
If uncertain, ASK (send to human with your concern). Output JSON only.
```

**Output schema (validated with Pydantic):**

```json
{
  "decision": "recommend | suppress | ask",
  "action": "stop | rightsize | snapshot_delete | modify_gp3 | release | none",
  "confidence": 0.0,
  "predicted_approval": 0.0,
  "reason": "one or two sentences",
  "cited_memory_ids": ["..."],
  "risk_note": "blast radius / IaC / compliance note"
}
```

- **Model:** Groq `openai/gpt-oss-120b`; fall back to `qwen/qwen3-32b`.
- **Robustness:** validate with Pydantic; on failure retry twice with the error text, then default to `ask`. The event brief explicitly warns about function-calling errors.
- **Suppressed candidates are kept**, not dropped. They appear under "Skipped (N)", each with its "Why?". This is how the product shows its learning.

### 7.2 Metrics the agent is judged on (product KPIs)

- **Acceptance rate** = approved / (approved + rejected). This is the headline number.
- **False-alarm rate** = rejected / shown.
- **Suppression precision:** how many suppressions a reviewer later confirmed. Sample a few to audit.
- **Savings approved and realized** ($/month).

---

## 8. Human review loop

### 8.1 Slack (Bolt for Python, **Socket Mode**, so no public URL is needed)

The message for each recommendation shows:
- title and resource,
- signals, estimated saving and blast-radius count,
- "memories consulted" (1–3 bullets),
- buttons: **Approve**, **Reject**, **Snooze 30d**, **Why?**

**Reject** opens a modal with:
- **Reason** (required, free text): this is the training data.
- **Scope** (radio): `Only this resource` / `All similar resources` / `Everything owned by this team`.
- **Temporary?** (optional date): "don't touch until Oct 31".

On submit: store the verdict → `retain_verdict()` → post a thread reply: "Got it. I'll remember this. Learning…" → after consolidation, update the thread: "Rule learned: *DR standbys are idle by design* (confirmed 1×)."

### 8.2 Dashboard pages
1. **Overview:** savings found / approved / realized; **acceptance-rate trend**; top learned rules.
2. **Queue:** pending recommendations, same actions as Slack, plus "Skipped (N)".
3. **Graph:** account dependency graph; click a node to see its blast radius.
4. **Learned Rules:** observations with proof count, sources and history; admin delete.
5. **Playbook:** current mental model plus version-history diff.
6. **Ask:** reflect box with cited answers.
7. **Settings:** connected accounts, hard rules (→ directives), reviewers, action-role toggle.

---

## 9. Safe execution

| Action | Pre-step | Execute | Post-step | Undo |
|---|---|---|---|---|
| Stop EC2 | Snapshot all attached EBS volumes | `StopInstances` | Tags `cloudsense:stopped-by`, `cloudsense:ticket` | `StartInstances` |
| Rightsize | Record the old type | stop → `ModifyInstanceAttribute` → start | Tag | Revert the type |
| gp2→gp3 | Check the 6h cooldown | `ModifyVolume` | Tag | (not needed) |
| Delete EBS | `CreateSnapshot`, wait until complete | `DeleteVolume` | Record the snapshot ID | Restore from snapshot |
| Stop RDS | `CreateDBSnapshot` | `StopDBInstance` | Warn about the 7-day auto-restart; schedule a re-stop or recommend snapshot + delete | `StartDBInstance` |

**Rules:**
- **IaC-managed resources** (tag `created_by:terraform`, or CloudFormation stack tags) never get a live mutation. Generate a Terraform diff snippet for a pull request instead.
- **No action without an approved verdict.** Every action is written to an audit log (who approved, when, what, and the undo handle).
- **Demo default:** action role off; show "dry run" with the exact API calls, plus one real stop on a sandbox instance.

---

## 10. Data model

```
orgs(id, name, hindsight_bank, created_at)
accounts(id, org_id, alias, aws_account_id, role_arn, external_id, regions, action_role_arn?)
scans(id, org_id, started_at, finished_at, status, resource_count, candidate_count)
resources(id, scan_id, account_id, arn, type, name, tags_json, owner_team, metrics_json,
          role_hints_json, depends_on_json, dependents_json)
candidates(id, scan_id, resource_id, rule_id, action, monthly_saving, signals_text,
           blast_radius, agent_decision_json, status)       -- status: pending|suppressed|approved|rejected|snoozed|executed
verdicts(id, candidate_id, reviewer_id, decision, reason, scope, until_date, at, retained_op_id)
actions(id, candidate_id, kind, api_calls_json, pre_snapshot_ids, status, undo_handle, at)
users(id, org_id, name, email, slack_id, role)               -- role: viewer|reviewer|admin
audit_log(id, org_id, actor, event, payload_json, at)
```

---

## 11. API (FastAPI)

```
POST /orgs/{org}/accounts                  connect account (role ARN + ExternalId check)
POST /orgs/{org}/scans                     start scan → background task
GET  /orgs/{org}/scans/{id}                scan status + candidates (recommended / suppressed)
POST /candidates/{id}/verdict              {decision, reason, scope, until_date}
POST /candidates/{id}/execute              approved only; returns action record
POST /actions/{id}/undo
GET  /orgs/{org}/rules                     observations (Hindsight) + provenance
DELETE /orgs/{org}/rules/{memory_id}       admin only
GET  /orgs/{org}/playbook                  current + history
POST /orgs/{org}/ask                       reflect proxy
GET  /orgs/{org}/metrics                   acceptance rate series, savings
GET  /graph/{scan_id}                      nodes/edges for the graph view
```

---

## 12. Repo structure

```
cloudsense/
├── backend/
│   ├── app.py                  # FastAPI entry
│   ├── config.py               # env vars
│   ├── scanner/                # aws_session.py, ec2.py, ebs.py, rds.py, s3.py, metrics.py
│   ├── graph/                  # build.py, blast_radius.py (reused)
│   ├── candidates/             # rules.py, pricing.py, aws_pricing.json (reused)
│   ├── agent/                  # prompt.py, decide.py, schema.py
│   ├── memory/                 # client.py, setup.py, templates.py
│   ├── review/                 # slack_app.py (Bolt, Socket Mode), routes.py
│   ├── actions/                # executor.py, iac.py, undo.py
│   ├── store/                  # models.py, db.py
│   └── tests/
├── frontend/                   # React + Vite: Overview, Queue, Graph, Rules, Playbook, Ask, Settings
├── infra/
│   ├── cloudsense-readonly.yaml
│   ├── cloudsense-action.yaml
│   └── sandbox-seed/           # Terraform/boto3 script to seed the demo account
├── eval/                       # reused CloudSense env + SimulatedEngineer + run_eval.py
├── docs/architecture.png
├── README.md                   # includes "How Hindsight memory is used"
└── .env.example
```

---

## 13. Configuration

```
HINDSIGHT_BASE_URL=            # Hindsight Cloud endpoint (from dashboard)
HINDSIGHT_API_KEY=             # ⚠ VERIFY auth mechanism
GROQ_API_KEY=
AGENT_MODEL=openai/gpt-oss-120b
AGENT_FALLBACK_MODEL=qwen/qwen3-32b
SLACK_BOT_TOKEN=
SLACK_APP_TOKEN=               # Socket Mode
SLACK_REVIEW_CHANNEL=#cloudsense-review
DATABASE_URL=sqlite:///cloudsense.db
CLOUDSENSE_PRINCIPAL_ARN=      # the account CloudSense runs in
DEMO_LOOKBACK_HOURS=           # optional, demo mode only
```

Promo code **MEMHACK99** gives $50 of Hindsight Cloud credit. Apply it after registering, in the billing section.

---

## 14. Security and multi-tenancy

- **One Hindsight bank per org**; the org ID is never taken from client input without an auth check.
- **STS AssumeRole with ExternalId** (confused-deputy protection). No static keys stored.
- **Least privilege:** the read role and the action role are separate; the action role is opt-in.
- **Audit log** of every verdict and action. Actions carry an undo handle.
- **Poisoning controls** per Section 5.8.
- Hindsight retains *derived facts*, not the raw text (per the docs). Still, never put secrets in verdict text: strip ARNs of account IDs if the customer requires it.

---

## 15. Eval harness (the RL environment, repurposed)

**Purpose:** prove the learning curve offline and reproducibly, and use it as a regression test.

1. Reuse the CloudSense environment: accounts with 7, 15 and 40 resources, trap resources, real pricing, the grader and blast radius.
2. Add `SimulatedEngineer`: converts grader penalties into natural-language rejection reasons ("That's the standby for orders-db, it's idle on purpose").
3. Sequence: 10 scans of one org across 3 accounts; traps reappear under **new names and no tags**.
4. Conditions:
   - **A:** no memory (recall and playbook disabled).
   - **B:** Hindsight memory.
   - Run 3 seeds each; use a fresh `bank_id` per run.
5. Plot acceptance rate and trap hits per scan (mean ± spread).
6. Output: `eval/results/*.json` plus `eval/plot.png`, used in the demo, README and article.

**Trap archetypes** (must be mostly *untagged*, otherwise directives alone solve them):

| Trap | Surface signal | Unwritten rule |
|---|---|---|
| DR standby | 0% CPU for 30 days | Idle by design |
| Payroll batch | Low average CPU | Month-end spikes |
| Audit archive | Cold S3, never read | Legal retention |
| Blue/green standby | Zero traffic | Rollback path |
| License-pinned host | Oversized | License forbids changing the instance type |
| On-call debug host | Dev-tagged, idle | Owned by SRE during incidents |

---

## 16. Build plan

### 16.1 Before the day
- [ ] Confirm the prior-work rule with the organizers. Prepared in advance: pricing JSON, eval environment, blast-radius code. Built on the day: everything else.
- [ ] Create the **sandbox AWS account**. Deploy `cloudsense-readonly.yaml` (this is the onboarding demo).
- [ ] Seed about 12 cheap resources with realistic names (t3.micro/t4g.nano instances, small gp2 volumes, one unattached volume, one EIP, a tiny S3 bucket). Include the traps `orders-db-standby`, `payroll-batch-worker`, `audit-archive`. **Leave them running several days** so CloudWatch has history.
- [ ] Set a **billing alarm** on the sandbox account.
- [ ] Hindsight Cloud account and promo credits. Smoke-test retain → consolidation → observation. **Record the latency.**
- [ ] Slack app with Socket Mode enabled, bot in `#cloudsense-review`.
- [ ] Groq key; test JSON-mode output on `gpt-oss-120b`.

### 16.2 The 8 hours (tracks A, B and C can run in parallel if you have teammates)

| Time | Track A: AWS | Track B: UX / Slack | Track C: Agent + memory |
|---|---|---|---|
| 0:00–1:30 | Scanner: assume role, describe, 14-day metrics → `Resource` | Slack app: message blocks, Approve/Reject/Why, reject modal | `memory/`: setup, `retain_verdict`, `recall_for`, playbook, reflect |
| 1:30–2:30 | Graph builder + role hints + blast radius | FastAPI routes for candidates and verdicts | Agent prompt + JSON schema + retries |
| 2:30–3:30 | Candidate rules R1–R8 + pricing | Dashboard shell + Queue page | Wire the agent: parallel recall, suppress/ask flows |
| 3:30–5:00 | Actions: snapshot → stop → tag → undo; IaC diff | Learned Rules + Playbook (history) pages | Consolidation polling + "Learning…" status to Slack/UI |
| 5:00–6:00 | End-to-end scan on the sandbox | Graph page + Overview metrics | Eval harness: 10 scans × 2 conditions × 3 seeds |
| 6:00–7:00 | **All:** full live run-through; fix what breaks | | |
| 7:00–8:00 | **All:** README (Hindsight section), architecture diagram, backup video, freeze | | |

### 16.3 Claude Code prompts (one task per prompt, in order)

1. "Create the repo skeleton from Section 12 with FastAPI app, config and SQLite models from Section 10. No business logic."
2. "Implement `scanner/` per Section 6: assume role with ExternalId; describe EC2/EBS/RDS/S3/EIP; 14-day CloudWatch metrics via GetMetricData; map to `Resource`. Add a moto-based test."
3. "Implement `graph/` per Section 6.5–6.6: dependency edges, role hints, and port `blast_radius()` from the old env."
4. "Implement `candidates/` rules R1–R8 from Section 6.4 using `aws_pricing.json`. Unit tests per rule."
5. "Implement `memory/` per Section 5.2–5.6 with the Hindsight Python client. Verify every ⚠ VERIFY signature against the docs first."
6. "Implement `agent/` per Section 7: prompt, Pydantic schema, Groq JSON mode, retries and fallback."
7. "Implement `review/slack_app.py` per Section 8.1 (Bolt, Socket Mode), calling the verdict route."
8. "Implement consolidation polling and the playbook refresh status per Section 5.7."
9. "Implement `actions/` per Section 9 with a dry-run mode and undo."
10. "Build the React pages per Section 8.2 against the API in Section 11."
11. "Implement `eval/` per Section 15 and produce `plot.png`."
12. "Write the README: setup, architecture, and a 'How Hindsight memory is used' section mapping each feature to Section 5.1."

---

## 17. Demo script (3 minutes)

| Time | Beat | Screen |
|---|---|---|
| 0:00 | "Cost tools tell you what to delete. Engineers ignore them, because the tools don't know *why* things exist." | Title |
| 0:15 | Connect: one CloudFormation stack → first scan → "$X/month of waste found" | Overview |
| 0:40 | Top recommendation: stop `orders-db-standby` (0% CPU). The blast-radius graph lights up. | Graph |
| 1:00 | The engineer **rejects in Slack**: "DR standby for orders-db, idle on purpose." Thread: "Learning…" → "Rule learned (1×)" | Slack |
| 1:25 | Learned Rules page: the observation with its source quote. Playbook history: new version. | Rules / Playbook |
| 1:45 | **Live:** launch a new untagged instance `payments-db-standby`. Rescan. | Terminal → Queue |
| 2:10 | It's under **Skipped**. "Why?" → a reflect answer citing the orders-db rejection. | Why drawer |
| 2:30 | Eval chart: acceptance rate with vs without Hindsight memory, 3 seeds | Chart |
| 2:50 | "Every 'no' makes it smarter. That's the part nobody else is capturing." | Close |

**Backup:** a pre-recorded run of the whole flow, plus pre-computed eval results.

---

## 18. Submission and content checklist

- [ ] Public GitHub repo, clean and documented. README explains **how Hindsight memory is used**.
- [ ] Demo video.
- [ ] Live demo to the judges.
- [ ] **Each member:** one article (800–1,500 words) on Medium, Dev.to, Hashnode, Substack or LinkedIn Articles. Include links to:
  - Hindsight GitHub: https://github.com/vectorize-io/hindsight
  - Hindsight docs: https://hindsight.vectorize.io/
  - Vectorize agent-memory page: https://vectorize.io/what-is-agent-memory
- [ ] Post the article as a link post on r/llmdevs, r/sideproject, r/aiagents or r/aimemory.
- [ ] **Each member:** one LinkedIn post (under 800 characters).
  - Include the repo link in the post.
  - Put the article URL in the first comment.
  - Add a comment linking the Hindsight GitHub repo.
- [ ] **Team:** one YouTube video (2–5 minutes, 1080p, public) with a custom thumbnail.
- [ ] 🚫 **The forbidden event word (see CLAUDE.md) must not appear anywhere** in the article, post, video title or hashtags. It disqualifies the entry.
- [ ] Article checklist:
  - specific hook,
  - a real `retain`/`recall` code snippet,
  - a before/after example,
  - one honest limitation (e.g. consolidation latency, cold start),
  - screenshots.

Title ideas:
- "My cost agent learned our DR rules from one Slack rejection, using Hindsight"
- "Why I stopped hand-writing FinOps exceptions and let Hindsight learn them"
- "Teaching an AWS cost agent the rules nobody wrote down"

---

## 19. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| No CloudWatch history in a fresh sandbox | No idle signals in the demo | Seed the account days ahead; `DEMO_LOOKBACK_HOURS` as a fallback (labeled) |
| Consolidation latency | The learning looks slow live | Measure early; "Learning…" status; pre-warm with template rules |
| Generalization to untagged look-alikes fails | The key scene fails | Role hints (6.6), entity linking, test before the day; fallback: show the same-resource suppression |
| LLM JSON / function-call errors | Crashes | Pydantic validation, retries, fallback model, default to `ask` |
| Memory poisoning | Bad rules spread | Reviewer roles, provenance, admin delete, directives take priority |
| Directives solve all tagged traps | No visible memory gain | Traps mostly untagged (Section 15) |
| RDS auto-restart after 7 days | Savings silently vanish | Warn in the UI; recommend snapshot + delete for truly dead DBs |
| Accidental real damage | Trust lost | Reversible-only actions, snapshots first, IaC diff-only, sandbox account |
| Sandbox AWS bill | Money | Smallest instances, billing alarm, tear-down script |
| Crowded market | Innovation score | Pitch the learning layer, not detection (Section 2) |
| Prior-work rule | Disqualification | Confirm with organizers; document what was built on the day |
| Name collision ("CloudSense") | Launch risk | Trademark check; keep a backup name |

---

## 20. Roadmap after v1

1. **Import recommendations** from Cost Optimization Hub and Compute Optimizer. Become the trust layer on top of any recommender.
2. **Reconcile savings** against Cost Explorer (realized vs estimated).
3. **Jira and GitHub:** Terraform pull requests for IaC-managed resources.
4. **Graduated autonomy:** auto-execute patterns with ≥N approvals and zero rejections, with per-pattern opt-in.
5. **Kubernetes** (requests/limits), then Azure and GCP.
6. **Playbook export** (Markdown/PDF) for onboarding and audits.
7. **Commitment recommendations**, informed by learned usage patterns.
8. **SOC 2 path:** SSO, data residency, self-hosted Hindsight option (it's open source).

---

## 21. Business model (for the impact score)

- **Buyer:** platform and FinOps leads at companies spending roughly $50k+ a month on AWS, with 20+ engineers.
- **Pricing options:**
  - flat per connected account per month, or
  - a share of *realized* savings (Vantage charges 5% on commitment savings, which is a useful reference point).
- **Wedge:** free read-only scan, which shows waste in minutes. The paid tier adds the Slack loop, learned rules and actions.
- **Moat:** each customer's learned playbook compounds. Switching means losing months of institutional memory.

---

## 22. References

- Hindsight docs: https://hindsight.vectorize.io/
  - Quick Start: https://hindsight.vectorize.io/developer/api/quickstart
  - Retain: https://hindsight.vectorize.io/developer/api/retain
  - Recall: https://hindsight.vectorize.io/developer/api/recall
  - Reflect: https://hindsight.vectorize.io/developer/api/reflect
  - Mental Models: https://hindsight.vectorize.io/developer/api/mental-models
  - Memory Banks: https://hindsight.vectorize.io/developer/api/memory-banks
  - Bank Templates: https://hindsight.vectorize.io/developer/api/bank-templates
  - Memory Defense: https://hindsight.vectorize.io/developer/memory-defense
- Hindsight GitHub: https://github.com/vectorize-io/hindsight
- Vectorize, what is agent memory: https://vectorize.io/what-is-agent-memory
- AWS FinOps Agent preview: https://aws.amazon.com/blogs/aws-cloud-financial-management/aws-finops-agent-is-now-public-preview/
- AWS Cost Optimization Hub: https://aws.amazon.com/aws-cost-management/cost-optimization-hub
- Vantage FinOps Agent: https://docs.vantage.sh/vantage_finops_agent
- nOps Clara on AgentCore: https://aws.amazon.com/blogs/machine-learning/how-nops-shipped-finops-agents-75-faster-with-amazon-bedrock-agentcore/
- Sedai: https://sedai.io/
- Amnic, AI FinOps agents compared: https://amnic.com/blogs/top-ai-agent-tools-for-finops
