#!/usr/bin/env python3
"""
Generate CloudSense account JSON files from AWS pricing data.
Run once to generate, then freeze the output. Not used at runtime.

Usage:
    python -m eval.cloudsense_env.data.generate_accounts
"""

import json
from collections import deque
from pathlib import Path

from backend.candidates import PRICING_FILE

DATA_DIR = Path(__file__).parent

with open(PRICING_FILE) as f:
    PRICING = json.load(f)


def ec2_cost(instance_type: str) -> float:
    return PRICING["ec2"][instance_type]


def rds_cost(instance_type: str) -> float:
    return PRICING["rds"][instance_type]


def s3_cost(size_gb: float, tier: str = "standard") -> float:
    return round(size_gb * PRICING["s3"][f"{tier}_per_gb"], 2)


def nat_gw_cost(gb_processed: float = 0) -> float:
    return round(PRICING["nat_gateway"]["base"] + gb_processed * PRICING["nat_gateway"]["per_gb_processed"], 2)


def es_cost(instance_type: str, nodes: int = 1) -> float:
    return round(PRICING["elasticsearch"][instance_type] * nodes, 2)


def k8s_cost(node_type: str, node_count: int) -> float:
    key = f"per_node_{node_type.replace('.', '_')}"
    return round(PRICING["kubernetes"]["cluster_base"] + PRICING["kubernetes"][key] * node_count, 2)


def alb_cost() -> float:
    return PRICING["load_balancer"]["alb_base"]


# ============================================================
# EASY ACCOUNT: 6 resources, all dev/staging
# ============================================================
def generate_easy_account() -> list[dict]:
    resources = [
        {
            "resource_id": "res-easy-001",
            "resource_type": "ec2",
            "name": "dev-api-server",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"instance_type": "t3.2xlarge", "vcpus": 8, "memory_gb": 32},
            "utilization": {"cpu_percent": 4.0, "memory_percent": 8.0, "network_mbps": 0.5},
            "monthly_cost": ec2_cost("t3.2xlarge"),
            "tags": {"team": "backend", "project": "api-v2"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": None,
        },
        {
            "resource_id": "res-easy-002",
            "resource_type": "rds",
            "name": "staging-analytics-db",
            "environment": "staging",
            "region": "us-east-1",
            "current_config": {"instance_type": "db.r5.large", "storage_gb": 500, "engine": "postgres", "multi_az": False},
            "utilization": {"cpu_percent": 3.0, "connections": 2, "storage_used_gb": 12, "iops": 10},
            "monthly_cost": round(rds_cost("db.r5.large") + 500 * 0.115, 2),  # instance + gp2 storage
            "tags": {"team": "data", "project": "analytics"},
            "has_backups": True,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": None,
        },
        {
            "resource_id": "res-easy-003",
            "resource_type": "load_balancer",
            "name": "old-staging-alb",
            "environment": "staging",
            "region": "us-east-1",
            "current_config": {"type": "ALB", "listeners": 1, "target_groups": 0, "active_targets": 0},
            "utilization": {"requests_per_second": 0, "active_connections": 0, "healthy_targets": 0},
            "monthly_cost": alb_cost(),
            "tags": {"team": "platform", "project": "legacy-migration"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": None,
        },
        {
            "resource_id": "res-easy-004",
            "resource_type": "load_balancer",
            "name": "test-nlb-unused",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"type": "NLB", "listeners": 0, "target_groups": 0, "active_targets": 0},
            "utilization": {"requests_per_second": 0, "active_connections": 0, "healthy_targets": 0},
            "monthly_cost": PRICING["load_balancer"]["nlb_base"],
            "tags": {"team": "backend", "project": "load-test"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": None,
        },
        {
            "resource_id": "res-easy-005",
            "resource_type": "s3",
            "name": "dev-log-archive",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"storage_class": "STANDARD", "size_gb": 2000, "versioning": False, "lifecycle_policy": None},
            "utilization": {"access_frequency": "rare", "last_accessed_days_ago": 90, "get_requests_per_day": 5},
            "monthly_cost": s3_cost(2000, "standard"),
            "tags": {"team": "devops", "project": "logging"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "write_heavy_read_rare",
            "subnet": None,
        },
        {
            "resource_id": "res-easy-006",
            "resource_type": "ec2",
            "name": "staging-worker",
            "environment": "staging",
            "region": "us-east-1",
            "current_config": {"instance_type": "t3.large", "vcpus": 2, "memory_gb": 8},
            "utilization": {"cpu_percent": 2.0, "memory_percent": 5.0, "network_mbps": 0.1},
            "monthly_cost": ec2_cost("t3.large"),
            "tags": {"team": "backend", "project": "batch-jobs"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "business_hours",
            "subnet": None,
        },
    ]
    return resources


# ============================================================
# MEDIUM ACCOUNT: 15 resources, mix of prod/dev/staging
# ============================================================
def generate_medium_account() -> list[dict]:
    resources = [
        # --- PROD RESOURCES (should be SKIPPED) ---
        {
            "resource_id": "res-med-001",
            "resource_type": "ec2",
            "name": "prod-web-primary",
            "environment": "prod",
            "region": "us-east-1",
            "current_config": {"instance_type": "m5.xlarge", "vcpus": 4, "memory_gb": 16},
            "utilization": {"cpu_percent": 5.0, "memory_percent": 12.0, "network_mbps": 2.0},
            "monthly_cost": ec2_cost("m5.xlarge"),
            "tags": {"team": "platform", "project": "web-app", "note": "DO NOT TOUCH - seasonal traffic spikes"},
            "has_backups": True,
            "is_critical": True,
            "dependencies": ["res-med-005"],
            "usage_pattern": "seasonal_spikes",
            "subnet": None,
        },
        {
            "resource_id": "res-med-002",
            "resource_type": "rds",
            "name": "prod-db-replica",
            "environment": "prod",
            "region": "us-east-1",
            "current_config": {"instance_type": "db.r5.large", "storage_gb": 200, "engine": "mysql", "multi_az": False, "role": "read_replica"},
            "utilization": {"cpu_percent": 8.0, "connections": 5, "storage_used_gb": 180, "iops": 50},
            "monthly_cost": round(rds_cost("db.r5.large") + 200 * 0.115, 2),
            "tags": {"team": "data", "project": "core-db", "purpose": "failover-replica"},
            "has_backups": True,
            "is_critical": True,
            "dependencies": ["res-med-003"],
            "usage_pattern": "always_on",
            "subnet": None,
        },
        {
            "resource_id": "res-med-003",
            "resource_type": "rds",
            "name": "prod-db-primary",
            "environment": "prod",
            "region": "us-east-1",
            "current_config": {"instance_type": "db.r5.xlarge", "storage_gb": 500, "engine": "mysql", "multi_az": True},
            "utilization": {"cpu_percent": 45.0, "connections": 120, "storage_used_gb": 420, "iops": 3000},
            "monthly_cost": round(rds_cost("db.r5.xlarge") + 500 * 0.115, 2),
            "tags": {"team": "data", "project": "core-db"},
            "has_backups": True,
            "is_critical": True,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": None,
        },
        {
            "resource_id": "res-med-004",
            "resource_type": "ec2",
            "name": "prod-api-gateway",
            "environment": "prod",
            "region": "us-east-1",
            "current_config": {"instance_type": "c5.xlarge", "vcpus": 4, "memory_gb": 8, "in_asg": True, "asg_name": "prod-api-asg"},
            "utilization": {"cpu_percent": 65.0, "memory_percent": 55.0, "network_mbps": 150.0},
            "monthly_cost": ec2_cost("c5.xlarge"),
            "tags": {"team": "platform", "project": "api", "aws:autoscaling:groupName": "prod-api-asg"},
            "has_backups": True,
            "is_critical": True,
            "dependencies": ["res-med-005"],
            "usage_pattern": "always_on",
            "subnet": None,
        },
        # --- LOAD BALANCER (prod, skip) ---
        {
            "resource_id": "res-med-005",
            "resource_type": "load_balancer",
            "name": "prod-main-alb",
            "environment": "prod",
            "region": "us-east-1",
            "current_config": {"type": "ALB", "listeners": 2, "target_groups": 3, "active_targets": 4},
            "utilization": {"requests_per_second": 500, "active_connections": 200, "healthy_targets": 4},
            "monthly_cost": alb_cost(),
            "tags": {"team": "platform", "project": "web-app"},
            "has_backups": False,
            "is_critical": True,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": None,
        },
        # --- DEV/STAGING RESOURCES (should be OPTIMIZED) ---
        {
            "resource_id": "res-med-006",
            "resource_type": "ec2",
            "name": "dev-ml-training",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"instance_type": "r5.2xlarge", "vcpus": 8, "memory_gb": 64},
            "utilization": {"cpu_percent": 3.0, "memory_percent": 4.0, "network_mbps": 0.2},
            "monthly_cost": ec2_cost("r5.2xlarge"),
            "tags": {"team": "ml", "project": "experiment-v3"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "business_hours",
            "subnet": None,
        },
        {
            "resource_id": "res-med-007",
            "resource_type": "ec2",
            "name": "staging-batch-worker",
            "environment": "staging",
            "region": "us-east-1",
            "current_config": {"instance_type": "m5.2xlarge", "vcpus": 8, "memory_gb": 32},
            "utilization": {"cpu_percent": 6.0, "memory_percent": 10.0, "network_mbps": 1.0},
            "monthly_cost": ec2_cost("m5.2xlarge"),
            "tags": {"team": "backend", "project": "batch-processing"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "business_hours",
            "subnet": None,
        },
        {
            "resource_id": "res-med-008",
            "resource_type": "kubernetes",
            "name": "dev-k8s-cluster",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"node_type": "m5.large", "node_count": 8, "autoscaling": False},
            "utilization": {"cpu_percent": 10.0, "memory_percent": 15.0, "pod_count": 8, "pod_capacity": 160},
            "monthly_cost": k8s_cost("m5.large", 8),
            "tags": {"team": "platform", "project": "microservices-dev"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": None,
        },
        {
            "resource_id": "res-med-009",
            "resource_type": "rds",
            "name": "dev-test-db",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"instance_type": "db.r5.xlarge", "storage_gb": 500, "engine": "postgres", "multi_az": False},
            "utilization": {"cpu_percent": 2.0, "connections": 1, "storage_used_gb": 5, "iops": 5},
            "monthly_cost": round(rds_cost("db.r5.xlarge") + 500 * 0.115, 2),
            "tags": {"team": "backend", "project": "testing"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "business_hours",
            "subnet": None,
        },
        {
            "resource_id": "res-med-010",
            "resource_type": "s3",
            "name": "staging-data-lake",
            "environment": "staging",
            "region": "us-east-1",
            "current_config": {"storage_class": "STANDARD", "size_gb": 20000, "versioning": True, "lifecycle_policy": None},
            "utilization": {"access_frequency": "rare", "last_accessed_days_ago": 60, "get_requests_per_day": 10},
            "monthly_cost": s3_cost(20000, "standard"),
            "tags": {"team": "data", "project": "data-lake"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "write_heavy_read_rare",
            "subnet": None,
        },
        {
            "resource_id": "res-med-011",
            "resource_type": "load_balancer",
            "name": "staging-unused-alb",
            "environment": "staging",
            "region": "us-east-1",
            "current_config": {"type": "ALB", "listeners": 1, "target_groups": 0, "active_targets": 0},
            "utilization": {"requests_per_second": 0, "active_connections": 0, "healthy_targets": 0},
            "monthly_cost": alb_cost(),
            "tags": {"team": "platform", "project": "old-staging"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": None,
        },
        {
            "resource_id": "res-med-012",
            "resource_type": "ec2",
            "name": "dev-jenkins-ci",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"instance_type": "m5.xlarge", "vcpus": 4, "memory_gb": 16},
            "utilization": {"cpu_percent": 15.0, "memory_percent": 20.0, "network_mbps": 5.0},
            "monthly_cost": ec2_cost("m5.xlarge"),
            "tags": {"team": "devops", "project": "ci-cd"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "business_hours",
            "subnet": None,
        },
        {
            "resource_id": "res-med-013",
            "resource_type": "ec2",
            "name": "dev-monitoring",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"instance_type": "t3.xlarge", "vcpus": 4, "memory_gb": 16},
            "utilization": {"cpu_percent": 8.0, "memory_percent": 12.0, "network_mbps": 0.5},
            "monthly_cost": ec2_cost("t3.xlarge"),
            "tags": {"team": "devops", "project": "monitoring"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": None,
        },
        # --- TRICKY: Reserved instance expiring soon ---
        {
            "resource_id": "res-med-014",
            "resource_type": "ec2",
            "name": "staging-cache-server",
            "environment": "staging",
            "region": "us-east-1",
            "current_config": {"instance_type": "r5.large", "vcpus": 2, "memory_gb": 16, "reservation_status": "expiring_30_days"},
            "utilization": {"cpu_percent": 35.0, "memory_percent": 60.0, "network_mbps": 10.0},
            "monthly_cost": ec2_cost("r5.large"),
            "tags": {"team": "backend", "project": "caching", "ri_expiry": "2025-04-15"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": None,
        },
        # --- CloudWatch logs with no retention ---
        {
            "resource_id": "res-med-015",
            "resource_type": "s3",
            "name": "cloudwatch-log-exports",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"storage_class": "STANDARD", "size_gb": 3000, "versioning": False, "lifecycle_policy": None, "purpose": "cloudwatch-log-archive"},
            "utilization": {"access_frequency": "never", "last_accessed_days_ago": 180, "get_requests_per_day": 0},
            "monthly_cost": s3_cost(3000, "standard"),
            "tags": {"team": "devops", "project": "logging", "retention": "none"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "write_only",
            "subnet": None,
        },
    ]
    return resources


# ============================================================
# HARD ACCOUNT: 40 resources across prod/staging/dev
# ============================================================
def generate_hard_account() -> list[dict]:
    resources = [
        # --- EC2 INSTANCES (8) ---
        {
            "resource_id": "res-hard-001",
            "resource_type": "ec2",
            "name": "prod-web-1",
            "environment": "prod",
            "region": "us-east-1",
            "current_config": {"instance_type": "m5.2xlarge", "vcpus": 8, "memory_gb": 32, "fleet_id": "fleet-web"},
            "utilization": {"cpu_percent": 55.0, "memory_percent": 60.0, "network_mbps": 80.0},
            "monthly_cost": ec2_cost("m5.2xlarge"),
            "tags": {"team": "platform", "project": "web-app", "fleet": "web"},
            "has_backups": True,
            "is_critical": True,
            "dependencies": ["res-hard-009"],
            "usage_pattern": "always_on",
            "subnet": "subnet-prod-a",
        },
        {
            "resource_id": "res-hard-002",
            "resource_type": "ec2",
            "name": "prod-web-2",
            "environment": "prod",
            "region": "us-east-1",
            "current_config": {"instance_type": "m5.2xlarge", "vcpus": 8, "memory_gb": 32, "fleet_id": "fleet-web"},
            "utilization": {"cpu_percent": 50.0, "memory_percent": 55.0, "network_mbps": 75.0},
            "monthly_cost": ec2_cost("m5.2xlarge"),
            "tags": {"team": "platform", "project": "web-app", "fleet": "web"},
            "has_backups": True,
            "is_critical": True,
            "dependencies": ["res-hard-009"],
            "usage_pattern": "always_on",
            "subnet": "subnet-prod-a",
        },
        {
            "resource_id": "res-hard-003",
            "resource_type": "ec2",
            "name": "prod-web-3",
            "environment": "prod",
            "region": "us-east-1",
            "current_config": {"instance_type": "m5.2xlarge", "vcpus": 8, "memory_gb": 32, "fleet_id": "fleet-web"},
            "utilization": {"cpu_percent": 52.0, "memory_percent": 58.0, "network_mbps": 70.0},
            "monthly_cost": ec2_cost("m5.2xlarge"),
            "tags": {"team": "platform", "project": "web-app", "fleet": "web"},
            "has_backups": True,
            "is_critical": True,
            "dependencies": ["res-hard-009"],
            "usage_pattern": "always_on",
            "subnet": "subnet-prod-a",
        },
        {
            "resource_id": "res-hard-004",
            "resource_type": "ec2",
            "name": "dev-data-science",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"instance_type": "r5.2xlarge", "vcpus": 8, "memory_gb": 64},
            "utilization": {"cpu_percent": 2.0, "memory_percent": 3.0, "network_mbps": 0.1},
            "monthly_cost": ec2_cost("r5.2xlarge"),
            "tags": {"team": "ml", "project": "experiments"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "business_hours",
            "subnet": "subnet-dev-a",
        },
        {
            "resource_id": "res-hard-005",
            "resource_type": "ec2",
            "name": "staging-api-server",
            "environment": "staging",
            "region": "us-east-1",
            "current_config": {"instance_type": "m5.xlarge", "vcpus": 4, "memory_gb": 16},
            "utilization": {"cpu_percent": 8.0, "memory_percent": 12.0, "network_mbps": 2.0},
            "monthly_cost": ec2_cost("m5.xlarge"),
            "tags": {"team": "backend", "project": "api"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "business_hours",
            "subnet": "subnet-dev-a",
        },
        {
            "resource_id": "res-hard-006",
            "resource_type": "ec2",
            "name": "dev-build-server",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"instance_type": "c5.2xlarge", "vcpus": 8, "memory_gb": 16},
            "utilization": {"cpu_percent": 12.0, "memory_percent": 18.0, "network_mbps": 5.0},
            "monthly_cost": ec2_cost("c5.2xlarge"),
            "tags": {"team": "devops", "project": "ci-cd"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "business_hours",
            "subnet": "subnet-dev-a",
        },
        {
            "resource_id": "res-hard-007",
            "resource_type": "ec2",
            "name": "prod-batch-processor",
            "environment": "prod",
            "region": "us-east-1",
            "current_config": {"instance_type": "c5.xlarge", "vcpus": 4, "memory_gb": 8, "spot_eligible": True},
            "utilization": {"cpu_percent": 70.0, "memory_percent": 45.0, "network_mbps": 20.0},
            "monthly_cost": ec2_cost("c5.xlarge"),
            "tags": {"team": "data", "project": "batch", "workload": "fault-tolerant"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "batch_nightly",
            "subnet": "subnet-prod-a",
        },
        {
            "resource_id": "res-hard-008",
            "resource_type": "ec2",
            "name": "dev-sandbox",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"instance_type": "t3.xlarge", "vcpus": 4, "memory_gb": 16},
            "utilization": {"cpu_percent": 1.0, "memory_percent": 2.0, "network_mbps": 0.0},
            "monthly_cost": ec2_cost("t3.xlarge"),
            "tags": {"team": "engineering", "project": "sandbox", "owner": "intern"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "rarely_used",
            "subnet": "subnet-dev-a",
        },

        # --- LOAD BALANCERS (3) ---
        {
            "resource_id": "res-hard-009",
            "resource_type": "load_balancer",
            "name": "prod-web-alb",
            "environment": "prod",
            "region": "us-east-1",
            "current_config": {"type": "ALB", "listeners": 2, "target_groups": 2, "active_targets": 3},
            "utilization": {"requests_per_second": 800, "active_connections": 350, "healthy_targets": 3},
            "monthly_cost": alb_cost(),
            "tags": {"team": "platform", "project": "web-app"},
            "has_backups": False,
            "is_critical": True,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": "subnet-prod-a",
        },
        {
            "resource_id": "res-hard-010",
            "resource_type": "load_balancer",
            "name": "staging-old-alb",
            "environment": "staging",
            "region": "us-east-1",
            "current_config": {"type": "ALB", "listeners": 1, "target_groups": 0, "active_targets": 0},
            "utilization": {"requests_per_second": 0, "active_connections": 0, "healthy_targets": 0},
            "monthly_cost": alb_cost(),
            "tags": {"team": "platform", "project": "deprecated"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": "subnet-dev-a",
        },
        {
            "resource_id": "res-hard-011",
            "resource_type": "load_balancer",
            "name": "dev-test-alb",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"type": "ALB", "listeners": 1, "target_groups": 0, "active_targets": 0},
            "utilization": {"requests_per_second": 0, "active_connections": 0, "healthy_targets": 0},
            "monthly_cost": alb_cost(),
            "tags": {"team": "qa", "project": "test-harness"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": "subnet-dev-a",
        },

        # --- RDS INSTANCES (4) ---
        {
            "resource_id": "res-hard-012",
            "resource_type": "rds",
            "name": "prod-main-db",
            "environment": "prod",
            "region": "us-east-1",
            "current_config": {"instance_type": "db.r5.xlarge", "storage_gb": 2000, "engine": "postgres", "multi_az": True},
            "utilization": {"cpu_percent": 40.0, "connections": 200, "storage_used_gb": 1600, "iops": 5000},
            "monthly_cost": round(rds_cost("db.r5.xlarge") + 2000 * 0.115, 2),
            "tags": {"team": "data", "project": "core"},
            "has_backups": True,
            "is_critical": True,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": "subnet-prod-a",
        },
        {
            "resource_id": "res-hard-013",
            "resource_type": "rds",
            "name": "prod-db-read-replica",
            "environment": "prod",
            "region": "us-east-1",
            "current_config": {"instance_type": "db.r5.large", "storage_gb": 2000, "engine": "postgres", "multi_az": False, "role": "read_replica"},
            "utilization": {"cpu_percent": 15.0, "connections": 50, "storage_used_gb": 1600, "iops": 1000},
            "monthly_cost": round(rds_cost("db.r5.large") + 2000 * 0.115, 2),
            "tags": {"team": "data", "project": "core", "purpose": "read-replica"},
            "has_backups": True,
            "is_critical": True,
            "dependencies": ["res-hard-012"],
            "usage_pattern": "always_on",
            "subnet": "subnet-prod-a",
        },
        {
            "resource_id": "res-hard-014",
            "resource_type": "rds",
            "name": "dev-analytics-db",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"instance_type": "db.r5.xlarge", "storage_gb": 1000, "engine": "postgres", "multi_az": False},
            "utilization": {"cpu_percent": 3.0, "connections": 2, "storage_used_gb": 15, "iops": 10},
            "monthly_cost": round(rds_cost("db.r5.xlarge") + 1000 * 0.115, 2),
            "tags": {"team": "data", "project": "analytics"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "business_hours",
            "subnet": "subnet-dev-a",
        },
        {
            "resource_id": "res-hard-015",
            "resource_type": "rds",
            "name": "staging-app-db",
            "environment": "staging",
            "region": "us-east-1",
            "current_config": {"instance_type": "db.m5.xlarge", "storage_gb": 500, "engine": "mysql", "multi_az": False},
            "utilization": {"cpu_percent": 10.0, "connections": 8, "storage_used_gb": 30, "iops": 100},
            "monthly_cost": round(rds_cost("db.m5.xlarge") + 500 * 0.115, 2),
            "tags": {"team": "backend", "project": "app"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "business_hours",
            "subnet": "subnet-dev-a",
        },

        # --- S3 BUCKETS (3) ---
        {
            "resource_id": "res-hard-016",
            "resource_type": "s3",
            "name": "prod-media-assets",
            "environment": "prod",
            "region": "us-east-1",
            "current_config": {"storage_class": "STANDARD", "size_gb": 500, "versioning": True, "lifecycle_policy": None},
            "utilization": {"access_frequency": "frequent", "last_accessed_days_ago": 1, "get_requests_per_day": 50000},
            "monthly_cost": s3_cost(500, "standard"),
            "tags": {"team": "frontend", "project": "media"},
            "has_backups": True,
            "is_critical": True,
            "dependencies": [],
            "usage_pattern": "read_heavy",
            "subnet": None,
        },
        {
            "resource_id": "res-hard-017",
            "resource_type": "s3",
            "name": "staging-backup-archive",
            "environment": "staging",
            "region": "us-east-1",
            "current_config": {"storage_class": "STANDARD", "size_gb": 20000, "versioning": False, "lifecycle_policy": None},
            "utilization": {"access_frequency": "rare", "last_accessed_days_ago": 120, "get_requests_per_day": 2},
            "monthly_cost": s3_cost(20000, "standard"),
            "tags": {"team": "devops", "project": "backups"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "write_heavy_read_rare",
            "subnet": None,
        },
        {
            "resource_id": "res-hard-018",
            "resource_type": "s3",
            "name": "dev-log-bucket",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"storage_class": "STANDARD", "size_gb": 40000, "versioning": False, "lifecycle_policy": None},
            "utilization": {"access_frequency": "never", "last_accessed_days_ago": 200, "get_requests_per_day": 0},
            "monthly_cost": s3_cost(40000, "standard"),
            "tags": {"team": "devops", "project": "logging", "retention": "none"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "write_only",
            "subnet": None,
        },

        # --- KUBERNETES CLUSTERS (2) ---
        {
            "resource_id": "res-hard-019",
            "resource_type": "kubernetes",
            "name": "prod-k8s-cluster",
            "environment": "prod",
            "region": "us-east-1",
            "current_config": {"node_type": "m5.large", "node_count": 15, "autoscaling": True, "min_nodes": 8, "max_nodes": 20},
            "utilization": {"cpu_percent": 60.0, "memory_percent": 65.0, "pod_count": 120, "pod_capacity": 300},
            "monthly_cost": k8s_cost("m5.large", 15),
            "tags": {"team": "platform", "project": "microservices"},
            "has_backups": True,
            "is_critical": True,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": "subnet-prod-a",
        },
        {
            "resource_id": "res-hard-020",
            "resource_type": "kubernetes",
            "name": "dev-k8s-cluster",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"node_type": "m5.large", "node_count": 8, "autoscaling": False},
            "utilization": {"cpu_percent": 8.0, "memory_percent": 12.0, "pod_count": 5, "pod_capacity": 160},
            "monthly_cost": k8s_cost("m5.large", 8),
            "tags": {"team": "platform", "project": "microservices-dev"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": "subnet-dev-a",
        },

        # --- NAT GATEWAYS (2) ---
        {
            "resource_id": "res-hard-021",
            "resource_type": "nat_gateway",
            "name": "prod-nat-gateway",
            "environment": "prod",
            "region": "us-east-1",
            "current_config": {"type": "managed", "elastic_ip": True},
            "utilization": {"gb_processed_monthly": 5000},
            "monthly_cost": nat_gw_cost(5000),
            "tags": {"team": "network", "project": "vpc"},
            "has_backups": False,
            "is_critical": True,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": "subnet-prod-a",
        },
        {
            "resource_id": "res-hard-022",
            "resource_type": "nat_gateway",
            "name": "dev-nat-gateway",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"type": "managed", "elastic_ip": True, "replaceable_with_vpc_endpoint": True},
            "utilization": {"gb_processed_monthly": 50},
            "monthly_cost": nat_gw_cost(50),
            "tags": {"team": "network", "project": "vpc"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": "subnet-dev-a",
        },

        # --- ELASTICSEARCH CLUSTERS (2) ---
        {
            "resource_id": "res-hard-023",
            "resource_type": "elasticsearch",
            "name": "prod-search-cluster",
            "environment": "prod",
            "region": "us-east-1",
            "current_config": {"instance_type": "m5.large", "node_count": 3, "storage_gb": 500},
            "utilization": {"cpu_percent": 35.0, "memory_percent": 50.0, "documents": 5000000, "queries_per_second": 100},
            "monthly_cost": es_cost("m5.large", 3),
            "tags": {"team": "search", "project": "product-search"},
            "has_backups": True,
            "is_critical": True,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": "subnet-prod-a",
        },
        {
            "resource_id": "res-hard-024",
            "resource_type": "elasticsearch",
            "name": "dev-logging-es",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"instance_type": "m5.xlarge", "node_count": 12, "storage_gb": 2000},
            "utilization": {"cpu_percent": 2.0, "memory_percent": 5.0, "documents": 200, "queries_per_second": 0.1},
            "monthly_cost": es_cost("m5.xlarge", 12),
            "tags": {"team": "devops", "project": "log-analysis"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": "subnet-dev-a",
        },

        # --- RESERVED INSTANCES (4 EC2s with RI status) ---
        {
            "resource_id": "res-hard-025",
            "resource_type": "ec2",
            "name": "prod-app-ri-1",
            "environment": "prod",
            "region": "us-east-1",
            "current_config": {"instance_type": "m5.xlarge", "vcpus": 4, "memory_gb": 16, "reservation": {"type": "1yr-standard", "region": "us-east-1", "expiry": "2026-01-15"}},
            "utilization": {"cpu_percent": 50.0, "memory_percent": 55.0, "network_mbps": 30.0},
            "monthly_cost": ec2_cost("m5.xlarge"),
            "tags": {"team": "platform", "project": "app-tier"},
            "has_backups": True,
            "is_critical": True,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": "subnet-prod-a",
        },
        {
            "resource_id": "res-hard-026",
            "resource_type": "ec2",
            "name": "prod-app-ri-2",
            "environment": "prod",
            "region": "us-east-1",
            "current_config": {"instance_type": "m5.xlarge", "vcpus": 4, "memory_gb": 16, "reservation": {"type": "1yr-standard", "region": "us-east-1", "expiry": "2026-01-15"}},
            "utilization": {"cpu_percent": 48.0, "memory_percent": 52.0, "network_mbps": 28.0},
            "monthly_cost": ec2_cost("m5.xlarge"),
            "tags": {"team": "platform", "project": "app-tier"},
            "has_backups": True,
            "is_critical": True,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": "subnet-prod-a",
        },
        {
            "resource_id": "res-hard-027",
            "resource_type": "ec2",
            "name": "staging-ri-wrong-region-1",
            "environment": "staging",
            "region": "us-east-1",
            "current_config": {"instance_type": "m5.large", "vcpus": 2, "memory_gb": 8, "reservation": {"type": "1yr-standard", "region": "us-west-2", "expiry": "2026-06-01"}},
            "utilization": {"cpu_percent": 20.0, "memory_percent": 25.0, "network_mbps": 5.0},
            "monthly_cost": ec2_cost("m5.large"),
            "tags": {"team": "backend", "project": "api", "note": "RI purchased in wrong region"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": "subnet-dev-a",
        },
        {
            "resource_id": "res-hard-028",
            "resource_type": "ec2",
            "name": "staging-ri-wrong-region-2",
            "environment": "staging",
            "region": "us-east-1",
            "current_config": {"instance_type": "m5.large", "vcpus": 2, "memory_gb": 8, "reservation": {"type": "1yr-standard", "region": "eu-west-1", "expiry": "2026-08-01"}},
            "utilization": {"cpu_percent": 22.0, "memory_percent": 28.0, "network_mbps": 4.0},
            "monthly_cost": ec2_cost("m5.large"),
            "tags": {"team": "backend", "project": "api", "note": "RI purchased in wrong region"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "always_on",
            "subnet": "subnet-dev-a",
        },

        # --- CLOUDWATCH/MONITORING (4) ---
        {
            "resource_id": "res-hard-029",
            "resource_type": "s3",
            "name": "cloudwatch-logs-prod",
            "environment": "prod",
            "region": "us-east-1",
            "current_config": {"storage_class": "STANDARD", "size_gb": 20000, "versioning": False, "lifecycle_policy": None, "purpose": "cloudwatch-log-archive"},
            "utilization": {"access_frequency": "rare", "last_accessed_days_ago": 60, "get_requests_per_day": 5},
            "monthly_cost": s3_cost(20000, "standard"),
            "tags": {"team": "devops", "project": "monitoring", "retention": "none"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "write_heavy_read_rare",
            "subnet": None,
        },
        {
            "resource_id": "res-hard-030",
            "resource_type": "s3",
            "name": "cloudwatch-logs-dev",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"storage_class": "STANDARD", "size_gb": 15000, "versioning": False, "lifecycle_policy": None, "purpose": "cloudwatch-log-archive"},
            "utilization": {"access_frequency": "never", "last_accessed_days_ago": 150, "get_requests_per_day": 0},
            "monthly_cost": s3_cost(15000, "standard"),
            "tags": {"team": "devops", "project": "monitoring", "retention": "none"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "write_only",
            "subnet": None,
        },
        {
            "resource_id": "res-hard-031",
            "resource_type": "s3",
            "name": "metrics-archive-staging",
            "environment": "staging",
            "region": "us-east-1",
            "current_config": {"storage_class": "STANDARD", "size_gb": 8000, "versioning": False, "lifecycle_policy": None},
            "utilization": {"access_frequency": "rare", "last_accessed_days_ago": 90, "get_requests_per_day": 1},
            "monthly_cost": s3_cost(8000, "standard"),
            "tags": {"team": "devops", "project": "metrics"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "write_heavy_read_rare",
            "subnet": None,
        },
        {
            "resource_id": "res-hard-032",
            "resource_type": "s3",
            "name": "cloudtrail-logs",
            "environment": "prod",
            "region": "us-east-1",
            "current_config": {"storage_class": "STANDARD", "size_gb": 10000, "versioning": True, "lifecycle_policy": None, "purpose": "compliance-audit-trail"},
            "utilization": {"access_frequency": "rare", "last_accessed_days_ago": 30, "get_requests_per_day": 10},
            "monthly_cost": s3_cost(10000, "standard"),
            "tags": {"team": "security", "project": "compliance"},
            "has_backups": True,
            "is_critical": True,
            "dependencies": [],
            "usage_pattern": "write_heavy_read_rare",
            "subnet": None,
        },

        # --- ADDITIONAL RESOURCES (8) ---
        # EBS volumes
        {
            "resource_id": "res-hard-033",
            "resource_type": "ec2",
            "name": "orphaned-ebs-volume-1",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"instance_type": "ebs_volume", "volume_type": "gp2", "size_gb": 5000, "attached": False},
            "utilization": {"cpu_percent": 0, "memory_percent": 0, "iops": 0},
            "monthly_cost": round(5000 * PRICING["ebs"]["gp2_per_gb"], 2),
            "tags": {"team": "backend", "project": "old-migration", "note": "detached volume"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "unused",
            "subnet": "subnet-dev-a",
        },
        {
            "resource_id": "res-hard-034",
            "resource_type": "ec2",
            "name": "orphaned-ebs-volume-2",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"instance_type": "ebs_volume", "volume_type": "io1", "size_gb": 3000, "attached": False},
            "utilization": {"cpu_percent": 0, "memory_percent": 0, "iops": 0},
            "monthly_cost": round(3000 * PRICING["ebs"]["io1_per_gb"], 2),
            "tags": {"team": "data", "project": "old-db-migration"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "unused",
            "subnet": "subnet-dev-a",
        },
        # Unused Elastic IPs
        {
            "resource_id": "res-hard-035",
            "resource_type": "ec2",
            "name": "unused-eip-1",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"instance_type": "elastic_ip", "associated": False},
            "utilization": {"cpu_percent": 0, "memory_percent": 0},
            "monthly_cost": PRICING["eip"]["unused_monthly"],
            "tags": {"team": "network", "project": "legacy"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "unused",
            "subnet": None,
        },
        {
            "resource_id": "res-hard-036",
            "resource_type": "ec2",
            "name": "unused-eip-2",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"instance_type": "elastic_ip", "associated": False},
            "utilization": {"cpu_percent": 0, "memory_percent": 0},
            "monthly_cost": PRICING["eip"]["unused_monthly"],
            "tags": {"team": "network", "project": "legacy"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "unused",
            "subnet": None,
        },
        # Data transfer heavy resource
        {
            "resource_id": "res-hard-037",
            "resource_type": "ec2",
            "name": "prod-data-sync",
            "environment": "prod",
            "region": "us-east-1",
            "current_config": {"instance_type": "m5.large", "vcpus": 2, "memory_gb": 8, "data_transfer_gb_monthly": 30000, "cross_region_replication": True, "replication_target": "eu-west-1"},
            "utilization": {"cpu_percent": 15.0, "memory_percent": 20.0, "network_mbps": 50.0},
            "monthly_cost": round(ec2_cost("m5.large") + 30000 * PRICING["data_transfer"]["per_gb_inter_region"], 2),
            "tags": {"team": "data", "project": "multi-region-sync", "note": "redundant replication - DR already handled by RDS multi-AZ"},
            "has_backups": True,
            "is_critical": False,
            "dependencies": ["res-hard-012"],
            "usage_pattern": "always_on",
            "subnet": "subnet-prod-a",
        },
        # Idle Lambda-like resource (represented as EC2 for simplicity)
        {
            "resource_id": "res-hard-038",
            "resource_type": "ec2",
            "name": "dev-etl-worker",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"instance_type": "t3.large", "vcpus": 2, "memory_gb": 8},
            "utilization": {"cpu_percent": 0.5, "memory_percent": 3.0, "network_mbps": 0.0},
            "monthly_cost": ec2_cost("t3.large"),
            "tags": {"team": "data", "project": "etl-pipeline", "status": "idle"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "rarely_used",
            "subnet": "subnet-dev-a",
        },
        # Multi-region S3 replication (redundant)
        {
            "resource_id": "res-hard-039",
            "resource_type": "s3",
            "name": "prod-backup-replica-eu",
            "environment": "prod",
            "region": "eu-west-1",
            "current_config": {"storage_class": "STANDARD", "size_gb": 10000, "versioning": True, "lifecycle_policy": None, "replication_source": "res-hard-016", "purpose": "cross-region-backup"},
            "utilization": {"access_frequency": "never", "last_accessed_days_ago": 365, "get_requests_per_day": 0},
            "monthly_cost": round(s3_cost(10000, "standard") + 10000 * PRICING["data_transfer"]["per_gb_inter_region"], 2),
            "tags": {"team": "devops", "project": "disaster-recovery", "note": "redundant - RDS multi-AZ already covers DR"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": ["res-hard-016"],
            "usage_pattern": "write_only",
            "subnet": None,
        },
        # Oversized dev instance in wrong AZ
        {
            "resource_id": "res-hard-040",
            "resource_type": "ec2",
            "name": "dev-legacy-monolith",
            "environment": "dev",
            "region": "us-east-1",
            "current_config": {"instance_type": "r5.xlarge", "vcpus": 4, "memory_gb": 32},
            "utilization": {"cpu_percent": 3.0, "memory_percent": 5.0, "network_mbps": 0.2},
            "monthly_cost": ec2_cost("r5.xlarge"),
            "tags": {"team": "engineering", "project": "legacy", "note": "scheduled for decommission"},
            "has_backups": False,
            "is_critical": False,
            "dependencies": [],
            "usage_pattern": "rarely_used",
            "subnet": "subnet-dev-a",
        },
    ]
    return resources


# ============================================================
# VALIDATION
# ============================================================
def validate_account(resources: list[dict], task_id: str) -> bool:
    ids = {r["resource_id"] for r in resources}
    errors = []

    for r in resources:
        # Check dependencies exist
        for dep in r["dependencies"]:
            if dep not in ids:
                errors.append(f"{r['resource_id']} depends on non-existent {dep}")

        # Check resource_id format
        task_prefix_map = {
            "startup-cleanup": "easy",
            "mid-size-audit": "med",
            "enterprise-finops": "hard",
        }
        prefix = task_prefix_map.get(task_id, task_id[:4])
        if not r["resource_id"].startswith(f"res-{prefix}"):
            errors.append(f"Bad resource_id format: {r['resource_id']}")

        # Check required fields present
        for field in ["has_backups", "is_critical", "usage_pattern", "dependencies"]:
            if field not in r:
                errors.append(f"{r['resource_id']} missing {field}")

        # Logical consistency warnings
        if r["environment"] == "prod" and not r["is_critical"]:
            # Not all prod resources are critical (e.g., batch processors)
            pass

    # Check no circular dependencies (BFS)
    for r in resources:
        visited = set()
        queue = deque(r["dependencies"])
        while queue:
            dep_id = queue.popleft()
            if dep_id == r["resource_id"]:
                errors.append(f"Circular dependency detected: {r['resource_id']}")
                break
            if dep_id in visited:
                continue
            visited.add(dep_id)
            # Find the dependency resource and add its deps
            for other in resources:
                if other["resource_id"] == dep_id:
                    queue.extend(other["dependencies"])
                    break

    # Verify totals
    total = sum(r["monthly_cost"] for r in resources)
    print(f"[{task_id}] {len(resources)} resources, total: ${total:.2f}")

    if errors:
        for e in errors:
            print(f"  ERROR: {e}")
        raise ValueError(f"{len(errors)} consistency errors found")
    else:
        print("  \u2713 All consistency checks passed")
    return True


# ============================================================
# MAIN
# ============================================================
def main():
    easy = generate_easy_account()
    validate_account(easy, "easy")

    medium = generate_medium_account()
    validate_account(medium, "med-")

    hard = generate_hard_account()
    validate_account(hard, "hard")

    # Write JSON files
    for name, data in [("easy_account.json", easy), ("medium_account.json", medium), ("hard_account.json", hard)]:
        path = DATA_DIR / name
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"  Written {path}")


if __name__ == "__main__":
    main()
