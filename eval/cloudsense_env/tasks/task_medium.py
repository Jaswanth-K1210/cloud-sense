"""Medium task: Mid-size audit — 15 resources, mix of prod (skip) and dev/staging (optimize)."""

from eval.cloudsense_env.models import ActionType
from eval.cloudsense_env.tasks.base_task import BaseTask


class MidSizeAuditTask(BaseTask):
    task_id = "mid-size-audit"
    difficulty = "medium"
    max_steps = 20
    description = (
        "Audit a mid-size company's mixed prod/dev AWS account with 15 resources. "
        "Must identify which resources to optimize and which to leave alone. "
        "Prod resources are critical and should be skipped."
    )
    data_file = "medium_account.json"
    optimal_cost = 1700.0  # approximate after optimizations

    def get_correct_actions(self) -> dict[str, ActionType]:
        return {
            # --- PROD: SKIP (5 resources) ---
            # prod-web-primary: 5% CPU but seasonal spikes, critical -> skip
            "res-med-001": ActionType.skip_resource,
            # prod-db-replica: read replica for failover, critical -> skip
            "res-med-002": ActionType.skip_resource,
            # prod-db-primary: active prod DB, critical -> skip
            "res-med-003": ActionType.skip_resource,
            # prod-api-gateway: in ASG, 65% CPU, critical -> skip
            "res-med-004": ActionType.skip_resource,
            # prod-main-alb: active with 4 targets, critical -> skip
            "res-med-005": ActionType.skip_resource,

            # --- DEV/STAGING: OPTIMIZE (10 resources) ---
            # dev-ml-training: r5.2xlarge @ 3% -> rightsize to t3.medium
            # saves $367.92 - $30.37 = $337.55
            "res-med-006": ActionType.rightsize_resource,
            # staging-batch-worker: m5.2xlarge @ 6% -> rightsize to t3.medium
            # saves $280.32 - $30.37 = $249.95
            "res-med-007": ActionType.rightsize_resource,
            # dev-k8s-cluster: 8 nodes @ 10% util, runs 24/7 -> schedule weekday-only
            # saves ~28% of $633.64 = $177.42
            "res-med-008": ActionType.schedule_uptime,
            # dev-test-db: db.r5.xlarge + 500GB @ 2%, 5GB used -> rightsize to db.t3.micro + 20GB
            # saves $407.90 - ($12.41 + 20*0.10) = $407.90 - $14.41 = $393.49
            "res-med-009": ActionType.rightsize_resource,
            # staging-data-lake: 20TB S3 standard rarely accessed -> lifecycle policy
            # saves ~70% of $460.00 = $322.00
            "res-med-010": ActionType.add_lifecycle_policy,
            # staging-unused-alb: 0 targets -> terminate
            # saves $22.27
            "res-med-011": ActionType.terminate_resource,
            # dev-jenkins-ci: m5.xlarge @ 15% -> rightsize to t3.medium
            # saves $140.16 - $30.37 = $109.79
            "res-med-012": ActionType.rightsize_resource,
            # dev-monitoring: t3.xlarge @ 8% -> rightsize to t3.small
            # saves $121.47 - $15.18 = $106.29
            "res-med-013": ActionType.rightsize_resource,
            # staging-cache-server: RI expiring, still needed -> purchase_reservation
            # saves ~30% of $91.98 = $27.59 (RI discount)
            "res-med-014": ActionType.purchase_reservation,
            # cloudwatch-log-exports: 3TB S3 never accessed -> lifecycle policy
            # saves ~70% of $69.00 = $48.30
            "res-med-015": ActionType.add_lifecycle_policy,
        }

    def get_critical_resources(self) -> set[str]:
        return {"res-med-001", "res-med-002", "res-med-003", "res-med-004", "res-med-005"}

    def get_action_savings(self) -> dict[str, float]:
        return {
            "res-med-001": 0.0,       # skip (prod)
            "res-med-002": 0.0,       # skip (prod)
            "res-med-003": 0.0,       # skip (prod)
            "res-med-004": 0.0,       # skip (prod)
            "res-med-005": 0.0,       # skip (prod)
            "res-med-006": 337.55,    # r5.2xlarge -> t3.medium
            "res-med-007": 249.95,    # m5.2xlarge -> t3.medium
            "res-med-008": 177.42,    # schedule K8s weekday-only
            "res-med-009": 393.49,    # db.r5.xlarge -> db.t3.micro
            "res-med-010": 322.00,    # S3 lifecycle
            "res-med-011": 22.27,     # terminate unused ALB
            "res-med-012": 109.79,    # m5.xlarge -> t3.medium
            "res-med-013": 106.29,    # t3.xlarge -> t3.small
            "res-med-014": 27.59,     # purchase reservation
            "res-med-015": 48.30,     # S3 lifecycle
        }
