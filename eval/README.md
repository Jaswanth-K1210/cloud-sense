---
title: CloudSense
emoji: ☁️
colorFrom: blue
colorTo: green
sdk: docker
tags:
  - openenv
  - finops
pinned: false
---

# CloudSense

**An OpenEnv-compatible RL benchmark for training and evaluating FinOps AI agents on cloud cost optimization.**

CloudSense simulates real AWS cloud accounts with realistic resource configurations, pricing, and dependency graphs. Agents must analyze infrastructure, identify waste, and take cost-optimization actions — while avoiding dangerous changes to production systems.

Uses **real AWS us-east-1 on-demand pricing** (Q1 2025). Features a novel **blast radius mechanic** that shows cascading infrastructure impact of each action, forcing agents to reason about dependencies before acting.

## Environment Description & Motivation

Cloud cost optimization is a $50B+ problem every company faces. FinOps teams manually audit accounts, identify waste, and recommend actions — a process that's tedious, error-prone, and highly automatable. CloudSense captures this real-world task as an RL benchmark:

- **Realistic data**: Actual AWS instance types, pricing, utilization patterns
- **Safety-critical decisions**: Must distinguish "low-utilization but critical prod" from "low-utilization and safe to downsize"
- **Dependency graphs**: Actions cascade through infrastructure — terminating a load balancer disconnects EC2 instances behind it
- **Progressive difficulty**: From trivial dev cleanup to enterprise-scale FinOps with 40 interdependent resources

## Action Space

| Action | Description |
|--------|-------------|
| `rightsize_resource` | Change to smaller/cheaper instance type. Requires `new_config`. |
| `terminate_resource` | Remove unused or unnecessary resources. Cost goes to $0. |
| `add_lifecycle_policy` | For S3: transition old data to cheaper storage tiers (~70% savings). |
| `enable_autoscaling` | Enable auto-scaling for EC2/K8s (~20% savings). |
| `purchase_reservation` | Buy reserved instances for steady workloads (~30% savings). |
| `change_storage_class` | Change S3 storage class (e.g., to Glacier Deep Archive). |
| `schedule_uptime` | Run non-prod resources only during business hours/weekdays. |
| `request_more_info` | Request additional information before deciding. |
| `skip_resource` | Leave resource unchanged (correct for critical prod resources). |

## Observation Space

| Field | Type | Description |
|-------|------|-------------|
| `task_id` | string | Current task identifier |
| `goal` | string | Task description |
| `account_id` | string | Account identifier |
| `resources` | list[dict] | All resources with configs, utilization, costs, deps |
| `monthly_cost_current` | float | Current monthly spend |
| `monthly_cost_optimized` | float | Optimal monthly spend |
| `total_possible_savings` | float | Maximum achievable savings |
| `actions_taken` | list[dict] | History of actions in this episode |
| `warnings` | list[string] | Active warnings |
| `step_number` | int | Current step |
| `max_steps` | int | Maximum steps allowed |
| `last_reward` | float | Reward from previous step |
| `last_action_error` | string? | Error message if last action failed |
| `info` | dict | Additional info including blast_radius |

### Blast Radius Info (in `info.blast_radius`)

```json
{
  "affected_resources": ["res-hard-001", "res-hard-002"],
  "risk_level": "high",
  "explanation": "Terminating this ELB will disconnect 3 EC2 instances"
}
```

Risk levels: `none`, `low`, `medium`, `high`, `critical`

## Task Descriptions

### Easy: Startup Cleanup (6 resources, 10 steps)
A small startup's dev/staging account with ~$627/mo spend. All resources are obviously oversized or unused. No production resources, no dependencies. Tests basic cost optimization skills.

### Medium: Mid-Size Audit (15 resources, 20 steps)
A mid-size company's mixed account with ~$3,487/mo spend. 5 critical production resources that must be skipped. Includes tricky scenarios: prod EC2 with 5% CPU (seasonal spikes), RDS read replica for failover, expiring reserved instance, EC2 in ASG.

### Hard: Enterprise FinOps (40 resources, 45 steps)
An enterprise account with ~$14,230/mo spend. Complex dependency graphs, blast radius considerations, reserved instances in wrong regions, massively oversized Elasticsearch (12 nodes for 200 documents), orphaned EBS volumes, redundant cross-region replication, and NAT Gateway replacement opportunities.

## Reward Function

Per-step rewards provide feedback during episodes:

**Positive components:**
- **Cost reduction** (0.0–0.40): Proportional to savings achieved
- **Action correctness** (0.0–0.20): Matches expected optimal action
- **Safe skip** (0.0–0.15): Correctly skipping critical prod resources
- **Reasoning quality** (0.0–0.05): References relevant metrics in reasoning
- **Blast radius awareness** (+0.05 bonus): References cascade impacts from previous step

**Penalties:**
- Terminate prod resource: **-0.50**
- Delete only backup of critical: **-0.80**
- Undersize resource: **-0.30**
- Break dependency: **-0.40**
- Duplicate action: **-0.10**

Final per-step reward is clamped to [0.0, 1.0].

## Blast Radius Mechanic

CloudSense tracks infrastructure dependencies and computes cascading impact for every action:

- **Terminating a load balancer** → All EC2 instances routing through it are affected (risk: high)
- **Terminating a NAT Gateway** → All resources in the same subnet lose internet access (risk: critical)
- **Rightsizing an RDS primary** → Read replicas are affected (risk: medium)
- **Terminating with no dependents** → No blast radius (risk: none)

Agents that reference blast radius information in their reasoning receive a +0.05 reward bonus, incentivizing infrastructure-aware decision making.

## Setup

### Docker (recommended)
```bash
docker build -t cloudsense .
docker run -p 7860:7860 cloudsense
```

### Local development
```bash
pip install -r requirements.txt
uvicorn eval.cloudsense_env.server.app:app --port 7860
```

### Run tests
```bash
pip install pytest
python -m pytest eval/tests -v
```

### Run inference
```bash
export HF_TOKEN=your_token_here
python eval/inference.py
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Status check |
| GET | `/health` | Health check |
| GET | `/tasks` | List available tasks |
| POST | `/reset?task_id=<id>` | Start new episode |
| POST | `/step` | Execute an action (JSON body) |
| GET | `/state` | Get current state |
| POST | `/close` | End episode |

## Baseline Score Targets

| Task | Expected Range | Notes |
|------|---------------|-------|
| startup-cleanup | 0.70–0.95 | Straightforward — most agents should score well |
| mid-size-audit | 0.50–0.80 | Requires prod safety awareness |
| enterprise-finops | 0.30–0.65 | Complex deps and blast radius reasoning |

## Baseline Results

Reproduced via `inference.py` against the live environment with `Qwen/Qwen2.5-72B-Instruct` (Hugging Face Router):

| Task | Steps | Score | Notes |
|------|-------|-------|-------|
| startup-cleanup | 6 | **0.94** | Top of expected range |
| mid-size-audit | 10 | **0.78** | Within expected range |
| enterprise-finops | 37 | **0.76** | Above expected range |

Total wall-clock time for all 3 tasks: **~4 minutes** (well under the 20 min budget).

To reproduce:
```bash
uvicorn eval.cloudsense_env.server.app:app --port 7860 &
HF_TOKEN=hf_xxx python eval/inference.py
```

All pricing based on AWS us-east-1 on-demand rates as of Q1 2025.
