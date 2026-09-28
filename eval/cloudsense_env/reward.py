"""Per-step reward function for CloudSense.

Provides feedback to the agent after each action.
Not the final score — that comes from the grader.
"""

from eval.cloudsense_env.models import ActionType


def compute_reward(
    action: dict,
    resource: dict,
    task,
    account_state: list[dict],
    actions_history: list[dict],
    original_cost: float,
    current_cost: float,
    cost_after_action: float,
    blast_radius: dict | None = None,
) -> tuple[float, float]:
    """Compute per-step reward for an action.

    Returns (raw_reward, api_reward):
        raw_reward: unclamped, used by grader for accurate penalty tracking
        api_reward: clamped to [0.0, 1.0], returned in API responses
    """
    reward = 0.0
    action_type = action.get("action_type", "")
    resource_id = action.get("resource_id", "")
    reasoning = action.get("reasoning", "")

    correct_actions = task.get_correct_actions()
    critical_resources = task.get_critical_resources()

    # =============================================
    # PENALTIES (applied first, can make reward negative before clamping)
    # =============================================

    # Terminate prod/critical resource: -0.50
    if action_type == ActionType.terminate_resource.value:
        if resource.get("is_critical") and resource.get("environment") == "prod":
            reward -= 0.50

    # Delete only backup of critical: -0.80
    if action_type == ActionType.terminate_resource.value:
        if resource.get("has_backups") and resource.get("is_critical"):
            # Check if this is the only backup
            backup_count = sum(
                1 for r in account_state
                if r.get("has_backups") and r.get("resource_id") != resource_id
                and any(dep == resource_id for dep in r.get("dependencies", []))
            )
            if backup_count == 0 and resource.get("has_backups"):
                reward -= 0.80

    # Undersize resource: -0.30
    if action_type == ActionType.rightsize_resource.value:
        if _is_undersized(action.get("new_config", {}), resource.get("utilization", {})):
            reward -= 0.30

    # Duplicate action on same resource: -0.10
    if _is_duplicate_action(action, actions_history):
        reward -= 0.10

    # Break dependency: -0.40
    if _breaks_dependency(action, resource, account_state):
        reward -= 0.40

    # =============================================
    # POSITIVE REWARDS
    # =============================================

    # Cost reduction component (0.0 - 0.40)
    if original_cost > 0:
        cost_saved = current_cost - cost_after_action
        if cost_saved > 0:
            pct_of_total = cost_saved / original_cost
            reward += min(0.40, pct_of_total * 4.0)

    # Action correctness (0.0 - 0.20)
    if resource_id in correct_actions:
        expected = correct_actions[resource_id]
        expected_val = expected.value if isinstance(expected, ActionType) else expected
        if action_type == expected_val:
            reward += 0.20

    # Safe skip of critical resource (0.0 - 0.15)
    if resource_id in critical_resources:
        if action_type == ActionType.skip_resource.value:
            reward += 0.15

    # Reasoning quality (0.0 - 0.05)
    if reasoning and len(reasoning) > 20:
        # Basic check: mentions utilization, cost, or relevant keywords
        keywords = ["cpu", "utilization", "cost", "unused", "critical", "prod", "dependency",
                     "oversized", "idle", "savings", "%", "lifecycle", "terminate", "rightsize"]
        matches = sum(1 for kw in keywords if kw.lower() in reasoning.lower())
        if matches >= 2:
            reward += 0.05
        elif matches >= 1:
            reward += 0.02

    # Blast radius awareness bonus (+0.05)
    # Rewards agent for acknowledging the current action's blast radius in reasoning
    if blast_radius and blast_radius.get("risk_level", "none") != "none":
        affected = blast_radius.get("affected_resources", [])
        awareness_keywords = ["blast", "impact", "cascade", "dependency", "affected", "risk"]
        has_awareness = any(kw in reasoning.lower() for kw in awareness_keywords)
        has_resource_ref = any(rid in reasoning for rid in affected)
        if has_awareness or has_resource_ref:
            reward += 0.05

    raw_reward = round(reward, 2)
    api_reward = round(max(0.0, min(1.0, reward)), 2)
    return raw_reward, api_reward


def _is_undersized(new_config: dict, utilization: dict) -> bool:
    """Check if new config would be undersized for current utilization."""
    if not new_config or not utilization:
        return False

    cpu_util = utilization.get("cpu_percent", 0)

    # For EC2: check if new instance type is too small
    new_type = new_config.get("instance_type", "")
    if new_type:
        # Simple heuristic: nano/micro can't handle > 30% util
        if "nano" in new_type and cpu_util > 30:
            return True
        if "micro" in new_type and cpu_util > 50:
            return True
        if "small" in new_type and cpu_util > 70:
            return True

    # For RDS: check storage
    new_storage = new_config.get("storage_gb", 0)
    used_storage = utilization.get("storage_used_gb", 0)
    if new_storage > 0 and used_storage > 0:
        if new_storage < used_storage * 1.2:  # less than 20% headroom
            return True

    return False


def _is_duplicate_action(action: dict, history: list[dict]) -> bool:
    """Check if same action_type on same resource_id already taken."""
    for prev in history:
        if (prev.get("resource_id") == action.get("resource_id") and
                prev.get("action_type") == action.get("action_type")):
            return True
    return False


def _breaks_dependency(action: dict, resource: dict, account_state: list[dict]) -> bool:
    """Check if terminating this resource breaks dependencies for other resources."""
    if action.get("action_type") != ActionType.terminate_resource.value:
        return False

    resource_id = action.get("resource_id", "")

    for r in account_state:
        if resource_id in r.get("dependencies", []):
            return True

    return False
