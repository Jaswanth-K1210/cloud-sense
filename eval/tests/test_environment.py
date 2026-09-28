"""Tests for CloudSenseEnv."""

import pytest

from eval.cloudsense_env.environment import CloudSenseEnv


@pytest.fixture
def env():
    e = CloudSenseEnv()
    yield e
    e.close()


class TestReset:
    def test_reset_easy(self, env):
        obs = env.reset("startup-cleanup")
        assert len(obs.resources) == 7
        assert obs.monthly_cost_current > 0
        assert obs.step_number == 0
        assert obs.task_id == "startup-cleanup"

    def test_reset_medium(self, env):
        obs = env.reset("mid-size-audit")
        assert len(obs.resources) == 15

    def test_reset_hard(self, env):
        obs = env.reset("enterprise-finops")
        assert len(obs.resources) == 40

    def test_reset_invalid_task(self, env):
        with pytest.raises(ValueError, match="Unknown task"):
            env.reset("nonexistent")

    def test_reset_clears_state(self, env):
        env.reset("startup-cleanup")
        env.step({"action_type": "skip_resource", "resource_id": "res-easy-001", "reasoning": "test"})
        obs = env.reset("startup-cleanup")
        assert obs.step_number == 0
        assert len(obs.actions_taken) == 0


class TestStep:
    def test_valid_step(self, env):
        env.reset("startup-cleanup")
        result = env.step({
            "action_type": "rightsize_resource",
            "resource_id": "res-easy-001",
            "new_config": {"instance_type": "t3.small"},
            "reasoning": "CPU at 4%, oversized",
        })
        assert result.reward > 0
        assert result.done is False
        assert result.observation.step_number == 1

    def test_invalid_resource(self, env):
        env.reset("startup-cleanup")
        result = env.step({
            "action_type": "skip_resource",
            "resource_id": "nonexistent",
            "reasoning": "test",
        })
        assert result.reward == 0.0
        assert result.observation.last_action_error is not None

    def test_invalid_action_type(self, env):
        env.reset("startup-cleanup")
        result = env.step({
            "action_type": "invalid_action",
            "resource_id": "res-easy-001",
            "reasoning": "test",
        })
        assert result.reward == 0.0
        assert result.observation.last_action_error is not None

    def test_step_without_reset(self, env):
        with pytest.raises(RuntimeError):
            env.step({"action_type": "skip_resource", "resource_id": "x"})

    def test_terminate_reduces_cost(self, env):
        env.reset("startup-cleanup")
        cost_before = env.current_cost
        env.step({
            "action_type": "terminate_resource",
            "resource_id": "res-easy-003",
            "reasoning": "unused ALB",
        })
        assert env.current_cost < cost_before

    def test_skip_no_cost_change(self, env):
        env.reset("startup-cleanup")
        cost_before = env.current_cost
        env.step({
            "action_type": "skip_resource",
            "resource_id": "res-easy-001",
            "reasoning": "skip",
        })
        assert env.current_cost == cost_before

    def test_lifecycle_reduces_s3_cost(self, env):
        env.reset("startup-cleanup")
        cost_before = env.current_cost
        env.step({
            "action_type": "add_lifecycle_policy",
            "resource_id": "res-easy-005",
            "reasoning": "rarely accessed S3",
        })
        assert env.current_cost < cost_before

    def test_done_on_all_actioned(self, env):
        env.reset("startup-cleanup")
        for i in range(1, 8):  # 7 resources including trap
            rid = f"res-easy-{i:03d}"
            result = env.step({"action_type": "skip_resource", "resource_id": rid, "reasoning": "test"})
        assert result.done is True


class TestBlastRadius:
    def test_terminate_with_dependents_hard(self, env):
        """Terminating prod ALB that EC2s depend on should show blast radius."""
        env.reset("enterprise-finops")
        result = env.step({
            "action_type": "terminate_resource",
            "resource_id": "res-hard-009",
            "reasoning": "test blast radius",
        })
        br = result.info.get("blast_radius", {})
        assert br["risk_level"] != "none"
        assert len(br["affected_resources"]) > 0

    def test_skip_no_blast_radius(self, env):
        env.reset("enterprise-finops")
        result = env.step({
            "action_type": "skip_resource",
            "resource_id": "res-hard-001",
            "reasoning": "critical prod",
        })
        br = result.info.get("blast_radius", {})
        assert br["risk_level"] == "none"

    def test_terminate_no_dependents(self, env):
        env.reset("startup-cleanup")
        result = env.step({
            "action_type": "terminate_resource",
            "resource_id": "res-easy-003",
            "reasoning": "unused ALB, no targets",
        })
        br = result.info.get("blast_radius", {})
        assert br["risk_level"] == "none"


class TestState:
    def test_state_returns_dict(self, env):
        env.reset("startup-cleanup")
        s = env.state()
        assert "resources" in s
        assert "current_cost" in s
        assert s["task_id"] == "startup-cleanup"


class TestClose:
    def test_close_resets_state(self, env):
        env.reset("startup-cleanup")
        env.close()
        assert env.task is None
        assert env.current_resources == []
