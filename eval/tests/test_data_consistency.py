"""Tests for account data JSON consistency."""

import json
from collections import deque
from pathlib import Path

import pytest

DATA_DIR = Path(__file__).parent.parent / "cloudsense_env" / "data"

ACCOUNT_FILES = [
    ("easy_account.json", "easy", 7),
    ("medium_account.json", "med-", 15),
    ("hard_account.json", "hard", 40),
]


@pytest.fixture(params=ACCOUNT_FILES, ids=lambda x: x[0])
def account(request):
    filename, prefix, expected_count = request.param
    path = DATA_DIR / filename
    with open(path) as f:
        data = json.load(f)
    return data, prefix, expected_count


def test_resource_count(account):
    data, _, expected = account
    assert len(data) == expected


def test_required_fields(account):
    data, _, _ = account
    required = ["resource_id", "resource_type", "name", "environment", "current_config",
                 "utilization", "monthly_cost", "has_backups", "is_critical",
                 "dependencies", "usage_pattern"]
    for r in data:
        for field in required:
            assert field in r, f"{r['resource_id']} missing {field}"


def test_resource_id_format(account):
    data, prefix, _ = account
    for r in data:
        assert r["resource_id"].startswith(f"res-{prefix}"), (
            f"Bad resource_id: {r['resource_id']} (expected prefix res-{prefix})"
        )


def test_no_orphaned_dependencies(account):
    data, _, _ = account
    ids = {r["resource_id"] for r in data}
    for r in data:
        for dep in r["dependencies"]:
            assert dep in ids, f"{r['resource_id']} depends on non-existent {dep}"


def test_no_circular_dependencies(account):
    data, _, _ = account
    lookup = {r["resource_id"]: r for r in data}

    for r in data:
        visited = set()
        queue = deque(r["dependencies"])
        while queue:
            dep_id = queue.popleft()
            assert dep_id != r["resource_id"], f"Circular dependency: {r['resource_id']}"
            if dep_id in visited:
                continue
            visited.add(dep_id)
            if dep_id in lookup:
                queue.extend(lookup[dep_id]["dependencies"])


def test_positive_costs(account):
    data, _, _ = account
    for r in data:
        assert r["monthly_cost"] >= 0, f"{r['resource_id']} has negative cost"


def test_unique_resource_ids(account):
    data, _, _ = account
    ids = [r["resource_id"] for r in data]
    assert len(ids) == len(set(ids)), "Duplicate resource IDs found"


def test_valid_environments(account):
    data, _, _ = account
    valid = {"prod", "staging", "dev"}
    for r in data:
        assert r["environment"] in valid, f"{r['resource_id']} has invalid env: {r['environment']}"


def test_valid_resource_types(account):
    data, _, _ = account
    valid = {"ec2", "rds", "s3", "load_balancer", "kubernetes", "nat_gateway", "elasticsearch", "ebs", "eip"}
    for r in data:
        assert r["resource_type"] in valid, f"{r['resource_id']} has invalid type: {r['resource_type']}"
