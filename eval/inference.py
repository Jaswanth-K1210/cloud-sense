#!/usr/bin/env python3
"""CloudSense inference script — runs an LLM agent through all tasks.

Reads environment variables:
    API_BASE_URL: LLM API endpoint (default: https://router.huggingface.co/v1)
    MODEL_NAME: Model to use (default: Qwen/Qwen2.5-72B-Instruct)
    HF_TOKEN / API_KEY: Authentication token (no default)
    IMAGE_NAME: Docker image reference (no default)
"""

import json
import os
import sys
import time

import requests
from openai import OpenAI

# ─── Environment Variables ───────────────────────────────────────────
API_KEY = os.getenv("HF_TOKEN") or os.getenv("API_KEY")
API_BASE_URL = os.getenv("API_BASE_URL") or "https://router.huggingface.co/v1"
MODEL_NAME = os.getenv("MODEL_NAME") or "Qwen/Qwen2.5-72B-Instruct"
IMAGE_NAME = os.getenv("IMAGE_NAME")
LOCAL_IMAGE_NAME = os.getenv("LOCAL_IMAGE_NAME")
ENV_URL = os.getenv("ENV_URL") or "http://localhost:7860"

if not API_KEY:
    sys.exit("ERROR: HF_TOKEN (or API_KEY) environment variable is required")

# ─── LLM Client ─────────────────────────────────────────────────────
client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

SYSTEM_PROMPT = """You are a FinOps AI agent optimizing cloud infrastructure costs.

You will be shown AWS resources with their configurations, utilization metrics, costs, and dependencies.
For each resource, choose the best action:

Actions:
- rightsize_resource: Change to a smaller/cheaper instance type. Provide new_config with instance_type (and optionally storage_gb for RDS, node_count for K8s/ES).
- terminate_resource: Remove unused or unnecessary resources.
- add_lifecycle_policy: For S3 buckets with rarely-accessed data — transitions old data to cheaper storage tiers.
- enable_autoscaling: Enable auto-scaling for EC2/K8s resources.
- purchase_reservation: Buy reserved instances for steady-state workloads (or recommend spot for fault-tolerant).
- change_storage_class: Change S3 storage class (e.g., GLACIER_DEEP_ARCHIVE, INFREQUENT_ACCESS).
- schedule_uptime: Schedule non-prod resources to run only during business hours or weekdays.
- request_more_info: When you need more information before deciding.
- skip_resource: Leave the resource unchanged (use for critical prod resources).

CRITICAL RULES:
1. NEVER terminate or modify critical production resources. Use skip_resource for these.
2. Check dependencies before terminating — don't break other resources.
3. Pay attention to blast radius warnings — they show cascading impacts of your actions.
   Reference affected resources in your reasoning to demonstrate infrastructure awareness.
4. For dev/staging resources with very low utilization, rightsize aggressively.
5. For S3 buckets with rare access patterns, add lifecycle policies.
6. For unused load balancers (0 targets), terminate them.

Respond with ONLY a JSON object (no markdown, no explanation outside JSON):
{
    "action_type": "one_of_the_actions_above",
    "resource_id": "the_resource_id",
    "new_config": {"instance_type": "t3.small"},
    "reasoning": "Brief explanation of why this action"
}
"""

TASKS = ["startup-cleanup", "mid-size-audit", "enterprise-finops"]


def format_resources(resources: list[dict]) -> str:
    """Format resources into a readable text block for the LLM."""
    lines = []
    for r in resources:
        config = r.get("current_config", {})
        util = r.get("utilization", {})
        deps = r.get("dependencies", [])
        lines.append(f"─── {r['resource_id']} ───")
        lines.append(f"  Name: {r['name']}")
        lines.append(f"  Type: {r['resource_type']} | Env: {r['environment']} | Region: {r.get('region', 'us-east-1')}")
        lines.append(f"  Config: {json.dumps(config)}")
        lines.append(f"  Utilization: {json.dumps(util)}")
        lines.append(f"  Monthly Cost: ${r['monthly_cost']:.2f}")
        lines.append(f"  Tags: {json.dumps(r.get('tags', {}))}")
        lines.append(f"  Critical: {r.get('is_critical', False)} | Backups: {r.get('has_backups', False)}")
        lines.append(f"  Dependencies: {deps if deps else 'none'}")
        lines.append(f"  Usage Pattern: {r.get('usage_pattern', 'unknown')}")
        if r.get("subnet"):
            lines.append(f"  Subnet: {r['subnet']}")
        lines.append("")
    return "\n".join(lines)


def parse_action(response_text: str) -> dict:
    """Parse LLM JSON response into an action dict."""
    text = response_text.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        action = json.loads(text)
    except json.JSONDecodeError:
        # Try to extract JSON from the response
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                action = json.loads(text[start:end])
            except json.JSONDecodeError:
                return {
                    "action_type": "skip_resource",
                    "resource_id": "unknown",
                    "new_config": None,
                    "reasoning": f"Failed to parse LLM response: {text[:200]}",
                }
        else:
            return {
                "action_type": "skip_resource",
                "resource_id": "unknown",
                "new_config": None,
                "reasoning": f"No JSON found in LLM response: {text[:200]}",
            }

    # Validate action_type
    valid_types = {
        "rightsize_resource", "terminate_resource", "add_lifecycle_policy",
        "enable_autoscaling", "purchase_reservation", "change_storage_class",
        "schedule_uptime", "request_more_info", "skip_resource",
    }
    if action.get("action_type") not in valid_types:
        action["action_type"] = "skip_resource"
        action["reasoning"] = f"Invalid action_type corrected to skip: {action.get('reasoning', '')}"

    return {
        "action_type": action.get("action_type", "skip_resource"),
        "resource_id": action.get("resource_id", "unknown"),
        "new_config": action.get("new_config"),
        "reasoning": action.get("reasoning", ""),
    }


def call_llm(messages: list[dict], max_retries: int = 3) -> str:
    """Call the LLM API with exponential backoff (1s, 2s, 4s)."""
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                max_tokens=512,
                temperature=0.1,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt  # 1s, 2s, 4s
                time.sleep(wait)
            else:
                return json.dumps({
                    "action_type": "skip_resource",
                    "resource_id": "unknown",
                    "reasoning": f"LLM API failed after {max_retries} retries: {str(e)[:200]}",
                })


def run_task(task_id: str):
    """Run a single task and print [START], [STEP], [END] to stdout."""
    step = 0
    rewards = []
    success = False
    score = 0.0

    print(f"[START] task={task_id} env=cloudsense model={MODEL_NAME}")

    try:
        # Reset environment
        resp = requests.post(f"{ENV_URL}/reset", params={"task_id": task_id}, timeout=30)
        resp.raise_for_status()
        obs = resp.json()

        resources = obs["resources"]
        actioned_ids = set()
        last_blast_radius = None

        while True:
            # Pick next resource to act on
            remaining = [r for r in resources if r["resource_id"] not in actioned_ids]
            if not remaining:
                break

            target = remaining[0]

            # Build user prompt
            user_msg = f"Task: {obs['goal']}\n"
            user_msg += f"Step {step + 1}/{obs['max_steps']} | "
            user_msg += f"Current cost: ${obs['monthly_cost_current']:.2f}/mo | "
            user_msg += f"Possible savings: ${obs['total_possible_savings']:.2f}\n\n"

            # Add blast radius warning if applicable
            if last_blast_radius and last_blast_radius.get("risk_level", "none") != "none":
                user_msg += "\n⚠️ BLAST RADIUS from last action:\n"
                user_msg += f"Risk: {last_blast_radius['risk_level']}\n"
                user_msg += f"Affected resources: {last_blast_radius.get('affected_resources', [])}\n"
                user_msg += f"Impact: {last_blast_radius.get('explanation', '')}\n"
                user_msg += "Consider this when choosing your next action.\n\n"

            user_msg += "Analyze this resource and choose an action:\n\n"
            user_msg += format_resources([target])

            if len(remaining) > 1:
                user_msg += f"\n({len(remaining) - 1} more resources remaining after this one)"

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ]

            # Call LLM
            llm_response = call_llm(messages)
            action = parse_action(llm_response)

            # Override resource_id if LLM returned wrong one
            if action["resource_id"] != target["resource_id"]:
                action["resource_id"] = target["resource_id"]

            # Execute action with retry
            result = None
            for attempt in range(3):
                try:
                    resp = requests.post(
                        f"{ENV_URL}/step",
                        json=action,
                        timeout=30,
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    break
                except Exception as e:
                    if attempt < 2:
                        wait = 2 ** attempt  # 1s, 2s
                        print(f"[STEP] retry {attempt + 1}/3 after error: {str(e)[:80]}")
                        time.sleep(wait)
                    else:
                        step += 1
                        rewards.append(0.0)
                        error_str = str(e)[:100]
                        print(f"[STEP] step={step} action=error({error_str}) reward=0.00 done=false error={error_str}")

            if result is None:
                continue

            step += 1
            reward = result.get("reward", 0.0)
            done = result.get("done", False)
            rewards.append(reward)

            # Update state
            obs = result.get("observation", obs)
            resources = obs.get("resources", resources)
            last_blast_radius = result.get("info", {}).get("blast_radius")
            error = obs.get("last_action_error")
            actioned_ids.add(action["resource_id"])

            done_str = "true" if done else "false"
            error_str = error if error else "null"
            print(f"[STEP] step={step} action={action['action_type']}({action['resource_id']}) reward={reward:.2f} done={done_str} error={error_str}")

            if done:
                score = result.get("info", {}).get("task_score", 0.0)
                success = True
                break

            if step >= obs.get("max_steps", 999):
                break

    except Exception as e:
        step += 1
        rewards.append(0.0)
        error_str = str(e)[:100]
        print(f"[STEP] step={step} action=error({error_str}) reward=0.00 done=true error={error_str}")
    finally:
        # Always close and emit [END]
        try:
            requests.post(f"{ENV_URL}/close", timeout=10)
        except Exception:
            pass

        if score == 0.0 and rewards:
            score = round(sum(rewards) / max(len(rewards), 1), 2)

        score = max(0.0, min(1.0, score))
        success_str = "true" if success else "false"
        rewards_str = ",".join(f"{r:.2f}" for r in rewards) if rewards else "0.00"
        print(f"[END] success={success_str} steps={step} score={score:.2f} rewards={rewards_str}")


def main():
    for task_id in TASKS:
        run_task(task_id)


if __name__ == "__main__":
    main()
