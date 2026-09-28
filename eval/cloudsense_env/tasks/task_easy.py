"""Easy task: Startup cleanup — 7 resources (6 dev/staging + 1 critical trap)."""

from eval.cloudsense_env.models import ActionType
from eval.cloudsense_env.tasks.base_task import BaseTask


class StartupCleanupTask(BaseTask):
    task_id = "startup-cleanup"
    difficulty = "easy"
    max_steps = 10
    description = (
        "Optimize a small startup's AWS account with 7 resources. "
        "Most are oversized or unused dev/staging — but watch out for critical production resources."
    )
    data_file = "easy_account.json"
    optimal_cost = 240.0  # approximate after optimizations

    def get_correct_actions(self) -> dict[str, ActionType]:
        return {
            # t3.2xlarge @ 4% CPU -> t3.small (saves $242.94 - $15.18 = $227.76)
            "res-easy-001": ActionType.rightsize_resource,
            # db.r5.large + 500GB storage @ 3% CPU, 12GB used -> db.t3.medium + 50GB
            # saves $232.70 - ($49.64 + 50*0.10) = $232.70 - $54.64 = $178.06
            "res-easy-002": ActionType.rightsize_resource,
            # Unused ALB with 0 targets -> terminate (saves $22.27)
            "res-easy-003": ActionType.terminate_resource,
            # Unused NLB with 0 targets -> terminate (saves $22.27)
            "res-easy-004": ActionType.terminate_resource,
            # 2TB S3 Standard rarely accessed -> lifecycle policy (saves ~70% = $32.20)
            "res-easy-005": ActionType.add_lifecycle_policy,
            # t3.large @ 2% CPU -> t3.micro (saves $60.74 - $7.59 = $53.15)
            "res-easy-006": ActionType.rightsize_resource,
            # TRAP: t3.medium @ 3% CPU looks idle — but is_critical=True, runs nightly
            # batch ETL pipeline. Agent must read criticality flag and SKIP.
            "res-easy-007": ActionType.skip_resource,
        }

    def get_critical_resources(self) -> set[str]:
        return {"res-easy-007"}  # Critical batch runner — must be skipped

    def get_action_savings(self) -> dict[str, float]:
        return {
            "res-easy-001": 227.76,   # t3.2xlarge -> t3.small
            "res-easy-002": 178.06,   # db.r5.large+500GB -> db.t3.medium+50GB
            "res-easy-003": 22.27,    # terminate unused ALB
            "res-easy-004": 22.27,    # terminate unused NLB
            "res-easy-005": 32.20,    # S3 lifecycle policy (~70% savings)
            "res-easy-006": 53.15,    # t3.large -> t3.micro
            "res-easy-007": 0.0,      # skip (critical trap)
        }
