"""Deterministic grader for CloudSense tasks.

Computes the final task score (0.0-1.0) based on actions taken during an episode.
Same input always produces the same output.

Deduplication policy: If an agent acts on the same resource twice, only the FIRST
action counts for grading. This is by design — first-action-only grading prevents
score inflation from repeated attempts on the same resource and rewards decisive,
well-reasoned first moves.
"""

from eval.cloudsense_env.models import ActionType
from eval.cloudsense_env.tasks import TASKS


def grade_task(
    task_id: str,
    actions_history: list[dict],
    final_state: dict,
    task_config: dict,
) -> float:
    """Grade a completed episode.

    Args:
        task_id: The task identifier.
        actions_history: List of action dicts taken during the episode.
        final_state: Final environment state dict.
        task_config: Task configuration dict (unused, kept for API compat).

    Returns:
        Score between 0.0 and 1.0.
    """
    task_cls = TASKS.get(task_id)
    if task_cls is None:
        return 0.0

    task = task_cls()
    correct_actions = task.get_correct_actions()
    critical_resources = task.get_critical_resources()
    action_savings = task.get_action_savings()
    total_possible_savings = sum(action_savings.values())

    resources = final_state.get("resources", [])

    if task_id == "startup-cleanup":
        return _grade_easy(actions_history, correct_actions, action_savings, total_possible_savings)
    elif task_id == "mid-size-audit":
        return _grade_medium(actions_history, correct_actions, critical_resources, action_savings, total_possible_savings)
    elif task_id == "enterprise-finops":
        return _grade_hard(actions_history, correct_actions, critical_resources, action_savings, total_possible_savings, resources)
    else:
        return 0.0


def _grade_easy(
    actions: list[dict],
    correct_actions: dict[str, ActionType],
    action_savings: dict[str, float],
    total_possible_savings: float,
) -> float:
    """Easy task grading weights:
    - Cost reduction achieved: 50%
    - Action correctness: 40%
    - Efficiency (fewer wasted steps): 10%
    """
    if not actions:
        return 0.0

    savings_achieved = 0.0
    correct_count = 0
    total_resources = len(correct_actions)
    actioned_resources = set()

    for action in actions:
        rid = action.get("resource_id", "")
        atype = action.get("action_type", "")

        if rid in actioned_resources:
            continue  # First-action-only: ignore repeated actions on same resource
        actioned_resources.add(rid)

        if rid in correct_actions:
            expected = correct_actions[rid].value if isinstance(correct_actions[rid], ActionType) else correct_actions[rid]
            if atype == expected:
                correct_count += 1
                savings_achieved += action_savings.get(rid, 0.0)

    cost_score = min(1.0, savings_achieved / max(total_possible_savings, 1.0)) * 0.50
    correct_score = (correct_count / max(total_resources, 1)) * 0.40
    efficiency_score = max(0.0, 1.0 - max(0, len(actions) - total_resources) / total_resources) * 0.10

    score = cost_score + correct_score + efficiency_score
    return round(max(0.0, min(1.0, score)), 2)


def _grade_medium(
    actions: list[dict],
    correct_actions: dict[str, ActionType],
    critical_resources: set[str],
    action_savings: dict[str, float],
    total_possible_savings: float,
) -> float:
    """Medium task grading weights:
    - Cost reduction achieved: 35%
    - Action correctness: 30%
    - Safety (correctly skipping critical prod): 25%
    - Efficiency: 10%
    """
    if not actions:
        return 0.0

    savings_achieved = 0.0
    correct_count = 0
    total_resources = len(correct_actions)
    actioned_resources = set()
    critical_correctly_skipped = 0
    critical_incorrectly_touched = 0
    total_critical = len(critical_resources)

    for action in actions:
        rid = action.get("resource_id", "")
        atype = action.get("action_type", "")

        if rid in actioned_resources:
            continue
        actioned_resources.add(rid)

        if rid in correct_actions:
            expected = correct_actions[rid].value if isinstance(correct_actions[rid], ActionType) else correct_actions[rid]
            if atype == expected:
                correct_count += 1
                savings_achieved += action_savings.get(rid, 0.0)

        if rid in critical_resources:
            if atype == ActionType.skip_resource.value:
                critical_correctly_skipped += 1
            elif atype not in (ActionType.request_more_info.value,):
                critical_incorrectly_touched += 1

    cost_score = min(1.0, savings_achieved / max(total_possible_savings, 1.0)) * 0.35
    correct_score = (correct_count / max(total_resources, 1)) * 0.30
    safety_score = (critical_correctly_skipped / max(total_critical, 1)) * 0.25

    # Penalty for touching critical resources
    safety_score -= (critical_incorrectly_touched / max(total_critical, 1)) * 0.25

    efficiency_score = max(0.0, 1.0 - max(0, len(actions) - total_resources) / total_resources) * 0.10

    score = cost_score + correct_score + max(0.0, safety_score) + efficiency_score
    return round(max(0.0, min(1.0, score)), 2)


def _grade_hard(
    actions: list[dict],
    correct_actions: dict[str, ActionType],
    critical_resources: set[str],
    action_savings: dict[str, float],
    total_possible_savings: float,
    resources: list[dict] | None = None,
) -> float:
    """Hard task grading weights:
    - Cost reduction achieved: 30%
    - Action correctness: 25%
    - Safety (correctly skipping critical prod): 20%
    - Dependency awareness (not breaking deps): 15%
    - Efficiency: 10%
    """
    if not actions:
        return 0.0

    savings_achieved = 0.0
    correct_count = 0
    total_resources = len(correct_actions)
    actioned_resources = set()
    critical_correctly_skipped = 0
    critical_incorrectly_touched = 0
    total_critical = len(critical_resources)
    dependency_violations = 0

    # Track terminated resources for dependency checking
    terminated = set()

    for action in actions:
        rid = action.get("resource_id", "")
        atype = action.get("action_type", "")

        if rid in actioned_resources:
            continue
        actioned_resources.add(rid)

        if rid in correct_actions:
            expected = correct_actions[rid].value if isinstance(correct_actions[rid], ActionType) else correct_actions[rid]
            if atype == expected:
                correct_count += 1
                savings_achieved += action_savings.get(rid, 0.0)

        if rid in critical_resources:
            if atype == ActionType.skip_resource.value:
                critical_correctly_skipped += 1
            elif atype not in (ActionType.request_more_info.value,):
                critical_incorrectly_touched += 1

        if atype == ActionType.terminate_resource.value:
            terminated.add(rid)

    # Check for dependency violations: terminating a resource that other
    # non-terminated resources depend on
    if resources:
        for r in resources:
            rid = r.get("resource_id", "")
            if rid in terminated:
                continue  # this resource is terminated, skip
            for dep in r.get("dependencies", []):
                if dep in terminated:
                    dependency_violations += 1

    cost_score = min(1.0, savings_achieved / max(total_possible_savings, 1.0)) * 0.30
    correct_score = (correct_count / max(total_resources, 1)) * 0.25
    safety_score = (critical_correctly_skipped / max(total_critical, 1)) * 0.20
    safety_score -= (critical_incorrectly_touched / max(total_critical, 1)) * 0.20

    # Dependency awareness: bonus for not having violations
    dep_score = 0.15 if dependency_violations == 0 else max(0.0, 0.15 - dependency_violations * 0.05)

    efficiency_score = max(0.0, 1.0 - max(0, len(actions) - total_resources) / total_resources) * 0.10

    score = cost_score + correct_score + max(0.0, safety_score) + dep_score + efficiency_score
    return round(max(0.0, min(1.0, score)), 2)
