"""CloudSense RL environment — manages state, steps, and episode lifecycle."""

import copy
import json

from backend.candidates import PRICING_FILE
from backend.graph.blast_radius import blast_radius
from eval.cloudsense_env.graders.grader import grade_task
from eval.cloudsense_env.models import ActionType, CloudObservation, StepResult
from eval.cloudsense_env.reward import compute_reward
from eval.cloudsense_env.tasks import TASKS

# Schedule uptime savings constants
# Weekday-only: run Mon-Fri (5 of 7 days), pay for 5/7 of the month
WEEKDAY_ONLY_FACTOR = 5 / 7                    # 0.714 — cost multiplier
# Business hours: run 10hrs/day instead of 24
BUSINESS_HOURS_FACTOR = 10 / 24                 # 0.417 — cost multiplier
# Combined: Mon-Fri, 10hrs/day
WEEKDAY_BUSINESS_HOURS = (5 / 7) * (10 / 24)   # 0.298 — cost multiplier

# Action cost multipliers for non-rightsize actions
LIFECYCLE_POLICY_FACTOR = 0.30    # S3: transition to IA saves ~70%
AUTOSCALING_FACTOR = 0.80         # ~20% savings from dynamic scaling
RESERVATION_FACTOR = 0.70         # RI typically saves ~30-40% on on-demand

with open(PRICING_FILE) as f:
    PRICING = json.load(f)


class CloudSenseEnv:
    def __init__(self):
        self.task = None
        self.task_id = None
        self.current_resources: list[dict] = []
        self.original_resources: list[dict] = []
        self.actions_history: list[dict] = []
        self.original_cost: float = 0.0
        self.current_cost: float = 0.0
        self.step_count: int = 0
        self.done: bool = False
        self.last_blast_radius: dict | None = None
        self.last_reward: float = 0.0
        self.last_action_error: str | None = None

    def reset(self, task_id: str) -> CloudObservation:
        """Reset environment for a new episode."""
        task_cls = TASKS.get(task_id)
        if task_cls is None:
            raise ValueError(f"Unknown task: {task_id}. Available: {list(TASKS.keys())}")

        self.task = task_cls()
        self.task_id = task_id
        raw = self.task.load_account_raw()
        self.current_resources = copy.deepcopy(raw)
        self.original_resources = copy.deepcopy(raw)
        self.actions_history = []
        self.original_cost = sum(r["monthly_cost"] for r in self.current_resources)
        self.current_cost = self.original_cost
        self.step_count = 0
        self.done = False
        self.last_blast_radius = None
        self.last_reward = 0.0
        self.last_action_error = None

        return self._make_observation()

    def step(self, action: dict) -> StepResult:
        """Execute one action and return result."""
        if self.task is None:
            raise RuntimeError("Environment not initialized. Call reset() first.")
        if self.done:
            raise RuntimeError("Episode is done. Call reset() to start a new one.")

        self.step_count += 1
        self.last_action_error = None

        # Validate action
        action_type = action.get("action_type", "")
        resource_id = action.get("resource_id", "")

        # Validate action_type
        valid_types = {a.value for a in ActionType}
        if action_type not in valid_types:
            self.last_action_error = f"Invalid action_type: {action_type}"
            return self._make_step_result(0.0)

        # Find the resource
        resource = None
        for r in self.current_resources:
            if r["resource_id"] == resource_id:
                resource = r
                break

        if resource is None:
            self.last_action_error = f"Resource not found: {resource_id}"
            return self._make_step_result(0.0)

        # Validate action_type is applicable to resource type
        error = self._validate_action_for_resource(action_type, resource, action)
        if error:
            self.last_action_error = error
            return self._make_step_result(0.0)

        # Compute blast radius BEFORE applying action
        blast_radius = self._compute_blast_radius(action, resource)

        # Apply action and compute new cost
        cost_before = self.current_cost
        self._apply_action(action, resource)
        cost_after = sum(r["monthly_cost"] for r in self.current_resources)
        self.current_cost = cost_after

        # Compute reward — raw for grader, api for response
        # Pass current action's blast radius so reward reflects THIS action's impact
        raw_reward, api_reward = compute_reward(
            action=action,
            resource=resource,
            task=self.task,
            account_state=self.current_resources,
            actions_history=self.actions_history,
            original_cost=self.original_cost,
            current_cost=cost_before,
            cost_after_action=cost_after,
            blast_radius=blast_radius,
        )

        self.actions_history.append({**action, "_raw_reward": raw_reward})
        self.last_blast_radius = blast_radius
        self.last_reward = api_reward

        # Check done condition
        self.done = self._is_done()

        info = {"blast_radius": blast_radius}

        # If done, compute final grader score
        if self.done:
            task_score = grade_task(
                self.task_id,
                self.actions_history,
                self.state(),
                {},
            )
            info["task_score"] = task_score

        return self._make_step_result(api_reward, info)

    def state(self) -> dict:
        """Return full current environment state."""
        return {
            "task_id": self.task_id,
            "resources": copy.deepcopy(self.current_resources),
            "original_cost": self.original_cost,
            "current_cost": self.current_cost,
            "step_count": self.step_count,
            "max_steps": self.task.max_steps if self.task else 0,
            "done": self.done,
            "actions_history": list(self.actions_history),
        }

    def close(self):
        """Clean up environment state."""
        self.task = None
        self.task_id = None
        self.current_resources = []
        self.original_resources = []
        self.actions_history = []
        self.original_cost = 0.0
        self.current_cost = 0.0
        self.step_count = 0
        self.done = False
        self.last_blast_radius = None
        self.last_reward = 0.0
        self.last_action_error = None

    def _make_observation(self) -> CloudObservation:
        """Build an observation from current state."""
        action_savings = self.task.get_action_savings() if self.task else {}
        total_possible_savings = sum(action_savings.values())

        return CloudObservation(
            task_id=self.task_id or "",
            goal=self.task.description if self.task else "",
            account_id=f"account-{self.task_id}",
            resources=copy.deepcopy(self.current_resources),
            monthly_cost_current=self.current_cost,
            monthly_cost_optimized=self.current_cost - total_possible_savings,
            total_possible_savings=total_possible_savings,
            actions_taken=[dict(a) for a in self.actions_history],
            warnings=[],
            step_number=self.step_count,
            max_steps=self.task.max_steps if self.task else 0,
            last_reward=self.last_reward,
            last_action_error=self.last_action_error,
            info={"blast_radius": self.last_blast_radius} if self.last_blast_radius else {},
        )

    def _make_step_result(self, reward: float, info: dict | None = None) -> StepResult:
        """Build a StepResult."""
        obs = self._make_observation()
        if info is None:
            info = {}
        if self.last_blast_radius and "blast_radius" not in info:
            info["blast_radius"] = self.last_blast_radius
        if "blast_radius" not in info:
            info["blast_radius"] = {"affected_resources": [], "risk_level": "none", "explanation": ""}

        return StepResult(
            observation=obs,
            reward=reward,
            done=self.done,
            info=info,
        )

    def _validate_action_for_resource(self, action_type: str, resource: dict, action: dict = None) -> str | None:
        """Return error message if action is invalid for this resource type, else None."""
        rtype = resource.get("resource_type", "")

        if action_type == ActionType.add_lifecycle_policy.value and rtype != "s3":
            return f"add_lifecycle_policy only applies to S3, not {rtype}"
        if action_type == ActionType.change_storage_class.value and rtype != "s3":
            return f"change_storage_class only applies to S3, not {rtype}"
        if action_type == ActionType.enable_autoscaling.value and rtype not in ("ec2", "kubernetes"):
            return f"enable_autoscaling only applies to EC2/K8s, not {rtype}"
        if action_type == ActionType.rightsize_resource.value:
            if rtype in ("s3", "ebs", "eip", "nat_gateway", "load_balancer"):
                return f"rightsize_resource does not apply to {rtype}"
            if action and not action.get("new_config"):
                return "rightsize_resource requires new_config with target configuration"
        if action_type == ActionType.purchase_reservation.value:
            eligible = ("ec2", "rds", "elasticsearch", "kubernetes")
            if rtype not in eligible:
                return f"purchase_reservation only applies to {', '.join(eligible)}, not {rtype}"

        return None

    def _apply_action(self, action: dict, resource: dict):
        """Simulate the cost impact of an action on a resource."""
        action_type = action.get("action_type", "")
        new_config = action.get("new_config", {})

        if action_type == ActionType.terminate_resource.value:
            resource["monthly_cost"] = 0.0
            resource["current_config"]["terminated"] = True

        elif action_type == ActionType.rightsize_resource.value:
            if new_config:
                new_cost = self._compute_new_cost(resource, new_config)
                if new_cost is not None:
                    resource["monthly_cost"] = new_cost
                    resource["current_config"].update(new_config)

        elif action_type == ActionType.add_lifecycle_policy.value:
            resource["monthly_cost"] = round(resource["monthly_cost"] * LIFECYCLE_POLICY_FACTOR, 2)
            resource["current_config"]["lifecycle_policy"] = "transition_to_ia_30d"

        elif action_type == ActionType.change_storage_class.value:
            target = (new_config or {}).get("storage_class", "GLACIER_DEEP_ARCHIVE")
            if target == "GLACIER_DEEP_ARCHIVE":
                resource["monthly_cost"] = round(resource["monthly_cost"] * 0.04, 2)
            elif target == "GLACIER_INSTANT":
                resource["monthly_cost"] = round(resource["monthly_cost"] * 0.17, 2)
            elif target == "INFREQUENT_ACCESS":
                resource["monthly_cost"] = round(resource["monthly_cost"] * 0.54, 2)
            elif target == "STANDARD":
                pass  # No cost change — already at standard pricing
            resource["current_config"]["storage_class"] = target

        elif action_type == ActionType.schedule_uptime.value:
            pattern = (new_config or {}).get("schedule", "weekday_only")
            if pattern == "business_hours":
                # Mon-Fri 10hrs/day: cost = original * WEEKDAY_BUSINESS_HOURS
                resource["monthly_cost"] = round(resource["monthly_cost"] * WEEKDAY_BUSINESS_HOURS, 2)
            else:
                # Weekday-only: cost = original * WEEKDAY_ONLY_FACTOR (pay for 5/7 of month)
                resource["monthly_cost"] = round(resource["monthly_cost"] * WEEKDAY_ONLY_FACTOR, 2)

        elif action_type == ActionType.enable_autoscaling.value:
            resource["monthly_cost"] = round(resource["monthly_cost"] * AUTOSCALING_FACTOR, 2)
            resource["current_config"]["autoscaling"] = True

        elif action_type == ActionType.purchase_reservation.value:
            resource["monthly_cost"] = round(resource["monthly_cost"] * RESERVATION_FACTOR, 2)
            resource["current_config"]["reservation_status"] = "reserved"

        # skip_resource and request_more_info don't change cost

    def _compute_new_cost(self, resource: dict, new_config: dict) -> float | None:
        """Compute the new monthly cost after rightsizing."""
        rtype = resource.get("resource_type", "")
        new_instance = new_config.get("instance_type", "")

        if rtype == "ec2" and new_instance:
            cost = PRICING.get("ec2", {}).get(new_instance)
            if cost is not None:
                return round(cost, 2)

        elif rtype == "rds" and new_instance:
            instance_cost = PRICING.get("rds", {}).get(new_instance)
            if instance_cost is not None:
                storage_gb = new_config.get("storage_gb", resource["current_config"].get("storage_gb", 0))
                storage_cost = storage_gb * PRICING["ebs"]["gp2_per_gb"]
                return round(instance_cost + storage_cost, 2)

        elif rtype == "elasticsearch" and new_instance:
            node_cost = PRICING.get("elasticsearch", {}).get(new_instance)
            if node_cost is not None:
                node_count = new_config.get("node_count", 1)
                return round(node_cost * node_count, 2)

        elif rtype == "kubernetes":
            node_type = new_config.get("node_type", "")
            node_count = new_config.get("node_count", 1)
            key = f"per_node_{node_type.replace('.', '_')}"
            per_node = PRICING.get("kubernetes", {}).get(key)
            if per_node is not None:
                base = PRICING["kubernetes"]["cluster_base"]
                return round(base + per_node * node_count, 2)

        return None

    def _dependents_graph(self) -> dict[str, list[str]]:
        """Invert `dependencies` into resource_id -> ids that depend on it."""
        graph: dict[str, list[str]] = {}
        for r in self.current_resources:
            for dep in r.get("dependencies", []):
                graph.setdefault(dep, []).append(r["resource_id"])
        return graph

    def _compute_blast_radius(self, action: dict, resource: dict) -> dict:
        """Compute cascading impact of an action using transitive BFS.

        BFS through dependency graph: if ELB → EC2 → RDS, terminating ELB
        shows BOTH EC2 AND RDS as affected (not just direct dependents).
        """
        action_type = action.get("action_type", "")
        resource_id = action.get("resource_id", "")

        # Skip/info actions have no blast radius
        if action_type in (ActionType.skip_resource.value, ActionType.request_more_info.value):
            return {"affected_resources": [], "risk_level": "none", "explanation": ""}

        affected = []
        risk_level = "none"
        explanation = ""

        if action_type == ActionType.terminate_resource.value:
            # BFS through dependency graph — find ALL transitively affected resources
            affected = blast_radius(self._dependents_graph(), resource_id)
            visited = set(affected)

            # Check subnet-based impact (NAT Gateway)
            if resource.get("resource_type") == "nat_gateway":
                subnet = resource.get("subnet")
                if subnet:
                    for r in self.current_resources:
                        if r.get("subnet") == subnet and r["resource_id"] != resource_id:
                            if r["resource_id"] not in visited:
                                visited.add(r["resource_id"])
                                affected.append(r["resource_id"])

            # Determine risk level based on affected count and criticality
            has_critical = any(
                r.get("is_critical") for r in self.current_resources
                if r["resource_id"] in visited
            )
            has_prod = any(
                r.get("environment") == "prod" for r in self.current_resources
                if r["resource_id"] in visited
            )

            if len(affected) == 0:
                risk_level = "none"
                explanation = "No dependent resources affected."
            elif resource.get("resource_type") == "nat_gateway" and has_critical:
                risk_level = "critical"
                explanation = (
                    f"Terminating this NAT Gateway will cut internet access for "
                    f"{len(affected)} resources in subnet {resource.get('subnet')}."
                )
            elif has_prod:
                risk_level = "critical"
                explanation = f"Terminating this resource affects {len(affected)} resources including production."
            elif has_critical:
                risk_level = "high"
                explanation = f"Terminating this resource affects {len(affected)} resources including critical ones."
            elif resource.get("resource_type") == "load_balancer":
                risk_level = "high"
                explanation = (
                    f"Terminating this ELB will disconnect {len(affected)} "
                    f"instances that route through it."
                )
            elif len(affected) > 2:
                risk_level = "high"
                explanation = f"Terminating this resource affects {len(affected)} dependent resources."
            elif len(affected) > 0:
                risk_level = "medium"
                explanation = f"Terminating this resource affects {len(affected)} dependent resource(s)."

        elif action_type == ActionType.rightsize_resource.value:
            # BFS for rightsize too — affects dependents but one tier lower risk
            affected = blast_radius(self._dependents_graph(), resource_id)
            visited = set(affected)

            if affected:
                has_critical = any(
                    r.get("is_critical") for r in self.current_resources
                    if r["resource_id"] in visited
                )
                # Rightsizing keeps service running — reduce risk one tier
                if has_critical:
                    risk_level = "high"
                    explanation = f"Rightsizing affects {len(affected)} dependent resource(s) including critical ones."
                elif len(affected) > 2:
                    risk_level = "medium"
                    explanation = f"Rightsizing affects {len(affected)} dependent resource(s)."
                else:
                    risk_level = "medium" if resource.get("resource_type") == "rds" else "low"
                    explanation = f"Rightsizing affects {len(affected)} dependent resource(s)."

        elif action_type in (ActionType.add_lifecycle_policy.value, ActionType.change_storage_class.value):
            # Minimal blast radius for storage changes
            risk_level = "low" if resource.get("is_critical") else "none"
            if risk_level == "low":
                explanation = "Storage class change on a critical resource — verify access patterns."

        return {
            "affected_resources": affected,
            "risk_level": risk_level,
            "explanation": explanation,
        }

    def _is_done(self) -> bool:
        """Check if episode should end."""
        if self.task is None:
            return True
        if self.step_count >= self.task.max_steps:
            return True

        # All resources have been actioned
        actioned_ids = {a.get("resource_id") for a in self.actions_history}
        all_ids = {r["resource_id"] for r in self.current_resources}
        if all_ids and actioned_ids >= all_ids:
            return True

        # >95% of possible savings achieved
        action_savings = self.task.get_action_savings()
        total_possible = sum(action_savings.values())
        actual_savings = self.original_cost - self.current_cost
        if total_possible > 0 and actual_savings / total_possible > 0.95:
            return True

        return False
