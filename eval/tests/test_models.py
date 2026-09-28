"""Tests for Pydantic models."""

import pytest
from pydantic import ValidationError

from eval.cloudsense_env.models import (
    ActionType,
    CloudAction,
    CloudObservation,
    CloudResource,
    CloudReward,
    Environment,
    ResourceType,
    StepResult,
)


def test_resource_type_enum():
    assert ResourceType.ec2 == "ec2"
    assert ResourceType.s3 == "s3"


def test_environment_enum():
    assert Environment.prod == "prod"
    assert Environment.dev == "dev"


def test_action_type_enum():
    assert ActionType.rightsize_resource == "rightsize_resource"
    assert ActionType.skip_resource == "skip_resource"


def test_cloud_resource_valid():
    r = CloudResource(
        resource_id="res-test-001",
        resource_type=ResourceType.ec2,
        name="test-server",
        environment=Environment.dev,
        current_config={"instance_type": "t3.large"},
        utilization={"cpu_percent": 10.0},
        monthly_cost=60.74,
    )
    assert r.resource_id == "res-test-001"
    assert r.is_critical is False
    assert r.dependencies == []
    assert r.subnet is None


def test_cloud_resource_all_fields():
    r = CloudResource(
        resource_id="res-test-002",
        resource_type=ResourceType.rds,
        name="prod-db",
        environment=Environment.prod,
        current_config={"instance_type": "db.r5.large"},
        utilization={"cpu_percent": 40.0},
        monthly_cost=175.20,
        tags={"team": "data"},
        has_backups=True,
        is_critical=True,
        dependencies=["res-test-001"],
        usage_pattern="always_on",
        subnet="subnet-prod-a",
    )
    assert r.is_critical is True
    assert r.dependencies == ["res-test-001"]
    assert r.subnet == "subnet-prod-a"


def test_cloud_action_valid():
    a = CloudAction(
        action_type=ActionType.rightsize_resource,
        resource_id="res-test-001",
        new_config={"instance_type": "t3.small"},
        reasoning="CPU too low",
    )
    assert a.action_type == ActionType.rightsize_resource


def test_cloud_action_minimal():
    a = CloudAction(
        action_type=ActionType.skip_resource,
        resource_id="res-test-001",
    )
    assert a.new_config is None
    assert a.reasoning == ""


def test_cloud_observation():
    obs = CloudObservation(
        task_id="test",
        goal="test goal",
        account_id="acc-1",
        resources=[],
        monthly_cost_current=100.0,
        monthly_cost_optimized=50.0,
        total_possible_savings=50.0,
    )
    assert obs.step_number == 0
    assert obs.last_action_error is None


def test_cloud_reward_bounds():
    r = CloudReward(value=0.5, cost_saved=100.0)
    assert r.value == 0.5

    with pytest.raises(ValidationError):
        CloudReward(value=1.5)

    with pytest.raises(ValidationError):
        CloudReward(value=-0.1)


def test_step_result():
    obs = CloudObservation(
        task_id="test",
        goal="g",
        account_id="a",
        resources=[],
        monthly_cost_current=100.0,
        monthly_cost_optimized=50.0,
        total_possible_savings=50.0,
    )
    sr = StepResult(observation=obs, reward=0.5, done=False, info={"test": True})
    assert sr.reward == 0.5
    assert sr.done is False
