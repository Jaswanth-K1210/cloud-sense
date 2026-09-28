"""Hard task: Enterprise FinOps — 40 resources with complex dependencies and blast radius."""

from eval.cloudsense_env.models import ActionType
from eval.cloudsense_env.tasks.base_task import BaseTask


class EnterpriseFinOpsTask(BaseTask):
    task_id = "enterprise-finops"
    difficulty = "hard"
    max_steps = 45
    description = (
        "Full FinOps review of an enterprise AWS account with 40 resources. "
        "Complex dependencies, blast radius considerations, reserved instance management, "
        "and multi-service optimization across prod/staging/dev."
    )
    data_file = "hard_account.json"
    optimal_cost = 7100.0  # approximate after optimizations

    def get_correct_actions(self) -> dict[str, ActionType]:
        return {
            # --- PROD EC2 FLEET behind ELB: SKIP (critical) ---
            "res-hard-001": ActionType.skip_resource,      # prod-web-1 (fleet behind ALB)
            "res-hard-002": ActionType.skip_resource,      # prod-web-2 (fleet behind ALB)
            "res-hard-003": ActionType.skip_resource,      # prod-web-3 (fleet behind ALB)

            # --- DEV/STAGING EC2: OPTIMIZE ---
            # dev-data-science: r5.2xlarge @ 2% -> rightsize to t3.small
            # saves $367.92 - $15.18 = $352.74
            "res-hard-004": ActionType.rightsize_resource,
            # staging-api-server: m5.xlarge @ 8% -> rightsize to t3.small
            # saves $140.16 - $15.18 = $124.98
            "res-hard-005": ActionType.rightsize_resource,
            # dev-build-server: c5.2xlarge @ 12% -> rightsize to c5.large
            # saves $248.20 - $62.05 = $186.15
            "res-hard-006": ActionType.rightsize_resource,
            # prod-batch-processor: fault-tolerant, spot eligible -> purchase spot
            # saves ~70% of $124.10 = $86.87
            "res-hard-007": ActionType.purchase_reservation,
            # dev-sandbox: t3.xlarge @ 1%, rarely used -> terminate
            # saves $121.47
            "res-hard-008": ActionType.terminate_resource,

            # --- LOAD BALANCERS ---
            "res-hard-009": ActionType.skip_resource,      # prod-web-alb: active, critical
            # staging-old-alb: 0 targets -> terminate
            "res-hard-010": ActionType.terminate_resource,  # saves $22.27
            # dev-test-alb: 0 targets -> terminate
            "res-hard-011": ActionType.terminate_resource,  # saves $22.27

            # --- RDS ---
            "res-hard-012": ActionType.skip_resource,      # prod-main-db: active, critical
            "res-hard-013": ActionType.skip_resource,      # prod-db-read-replica: critical, depends on primary
            # dev-analytics-db: db.r5.xlarge + 1TB @ 3%, 15GB used -> rightsize
            # saves $465.40 - ($12.41 + 20*0.10) = $465.40 - $14.41 = $450.99
            "res-hard-014": ActionType.rightsize_resource,
            # staging-app-db: db.m5.xlarge + 500GB @ 10% -> rightsize to db.t3.medium + 100GB
            # saves $308.62 - ($49.64 + 100*0.10) = $308.62 - $59.64 = $248.98
            "res-hard-015": ActionType.rightsize_resource,

            # --- S3 ---
            "res-hard-016": ActionType.skip_resource,      # prod-media-assets: frequently accessed, critical
            # staging-backup-archive: 20TB rarely accessed -> lifecycle policy
            # saves ~70% of $460.00 = $322.00
            "res-hard-017": ActionType.add_lifecycle_policy,
            # dev-log-bucket: 40TB never accessed -> lifecycle policy
            # saves ~70% of $920.00 = $644.00
            "res-hard-018": ActionType.add_lifecycle_policy,

            # --- KUBERNETES ---
            "res-hard-019": ActionType.skip_resource,      # prod-k8s: active, critical, autoscaling
            # dev-k8s: 8 nodes @ 8%, runs 24/7 -> schedule weekday-only
            # saves ~28% of $633.64 = $177.42
            "res-hard-020": ActionType.schedule_uptime,

            # --- NAT GATEWAYS ---
            "res-hard-021": ActionType.skip_resource,      # prod-nat: critical, prod subnet depends on it
            # dev-nat: replaceable with VPC endpoint
            # saves $35.10
            "res-hard-022": ActionType.terminate_resource,

            # --- ELASTICSEARCH ---
            "res-hard-023": ActionType.skip_resource,      # prod-search: active, critical
            # dev-logging-es: 12 m5.xlarge nodes for 200 docs -> rightsize to 1 t3.small
            # saves $2890.80 - $26.28 = $2864.52
            "res-hard-024": ActionType.rightsize_resource,

            # --- RESERVED INSTANCES ---
            "res-hard-025": ActionType.skip_resource,      # prod-app-ri-1: correct region, critical
            "res-hard-026": ActionType.skip_resource,      # prod-app-ri-2: correct region, critical
            # staging-ri-wrong-region-1: RI in us-west-2 but instance in us-east-1
            # -> request_more_info to modify RI region
            "res-hard-027": ActionType.request_more_info,
            # staging-ri-wrong-region-2: RI in eu-west-1 but instance in us-east-1
            # -> request_more_info to modify RI region
            "res-hard-028": ActionType.request_more_info,

            # --- CLOUDWATCH/MONITORING S3 ---
            # cloudwatch-logs-prod: 20TB no lifecycle -> add policy (but prod, non-critical)
            # saves ~70% of $460.00 = $322.00
            "res-hard-029": ActionType.add_lifecycle_policy,
            # cloudwatch-logs-dev: 15TB never accessed -> lifecycle policy
            # saves ~70% of $345.00 = $241.50
            "res-hard-030": ActionType.add_lifecycle_policy,
            # metrics-archive-staging: 8TB rarely accessed -> lifecycle policy
            # saves ~70% of $184.00 = $128.80
            "res-hard-031": ActionType.add_lifecycle_policy,
            # cloudtrail-logs: compliance audit trail, critical -> skip
            "res-hard-032": ActionType.skip_resource,

            # --- ADDITIONAL RESOURCES ---
            # orphaned-ebs-volume-1: detached, unused -> terminate
            # saves $500.00
            "res-hard-033": ActionType.terminate_resource,
            # orphaned-ebs-volume-2: detached, unused -> terminate
            # saves $375.00
            "res-hard-034": ActionType.terminate_resource,
            # unused-eip-1 -> terminate (saves $3.65)
            "res-hard-035": ActionType.terminate_resource,
            # unused-eip-2 -> terminate (saves $3.65)
            "res-hard-036": ActionType.terminate_resource,
            # prod-data-sync: redundant replication (DR handled by RDS multi-AZ)
            # -> terminate replication, keep instance
            # saves data transfer: $600.00
            "res-hard-037": ActionType.terminate_resource,
            # dev-etl-worker: idle, rarely used -> terminate
            # saves $60.74
            "res-hard-038": ActionType.terminate_resource,
            # prod-backup-replica-eu: redundant cross-region backup
            # -> change_storage_class to Glacier Deep Archive
            # saves most of $430.00 (keep at ~$10)
            "res-hard-039": ActionType.change_storage_class,
            # dev-legacy-monolith: r5.xlarge @ 3%, scheduled for decommission -> terminate
            # saves $183.96
            "res-hard-040": ActionType.terminate_resource,
        }

    def get_critical_resources(self) -> set[str]:
        return {
            "res-hard-001", "res-hard-002", "res-hard-003",  # prod web fleet
            "res-hard-009",                                    # prod ALB
            "res-hard-012", "res-hard-013",                   # prod RDS
            "res-hard-016",                                    # prod S3 media
            "res-hard-019",                                    # prod K8s
            "res-hard-021",                                    # prod NAT GW
            "res-hard-023",                                    # prod ES
            "res-hard-025", "res-hard-026",                   # prod RI correct region
            "res-hard-032",                                    # cloudtrail compliance
        }

    def get_action_savings(self) -> dict[str, float]:
        return {
            "res-hard-001": 0.0,       # skip
            "res-hard-002": 0.0,       # skip
            "res-hard-003": 0.0,       # skip
            "res-hard-004": 352.74,    # rightsize
            "res-hard-005": 124.98,    # rightsize
            "res-hard-006": 186.15,    # rightsize
            "res-hard-007": 86.87,     # spot/reservation
            "res-hard-008": 121.47,    # terminate
            "res-hard-009": 0.0,       # skip
            "res-hard-010": 22.27,     # terminate
            "res-hard-011": 22.27,     # terminate
            "res-hard-012": 0.0,       # skip
            "res-hard-013": 0.0,       # skip
            "res-hard-014": 450.99,    # rightsize
            "res-hard-015": 248.98,    # rightsize
            "res-hard-016": 0.0,       # skip
            "res-hard-017": 322.00,    # lifecycle
            "res-hard-018": 644.00,    # lifecycle
            "res-hard-019": 0.0,       # skip
            "res-hard-020": 177.42,    # schedule
            "res-hard-021": 0.0,       # skip
            "res-hard-022": 35.10,     # terminate NAT -> VPC endpoint
            "res-hard-023": 0.0,       # skip
            "res-hard-024": 2864.52,   # rightsize ES massively
            "res-hard-025": 0.0,       # skip
            "res-hard-026": 0.0,       # skip
            "res-hard-027": 0.0,       # request_more_info (no direct savings)
            "res-hard-028": 0.0,       # request_more_info (no direct savings)
            "res-hard-029": 322.00,    # lifecycle
            "res-hard-030": 241.50,    # lifecycle
            "res-hard-031": 128.80,    # lifecycle
            "res-hard-032": 0.0,       # skip
            "res-hard-033": 500.00,    # terminate orphaned EBS
            "res-hard-034": 375.00,    # terminate orphaned EBS
            "res-hard-035": 3.65,      # terminate unused EIP
            "res-hard-036": 3.65,      # terminate unused EIP
            "res-hard-037": 600.00,    # terminate redundant replication
            "res-hard-038": 60.74,     # terminate idle
            "res-hard-039": 420.00,    # change to Glacier Deep Archive
            "res-hard-040": 183.96,    # terminate decommission target
        }
