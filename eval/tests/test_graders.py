"""Tests for grader determinism and correctness."""

from eval.cloudsense_env.graders.grader import grade_task


def _make_action(action_type: str, resource_id: str) -> dict:
    return {"action_type": action_type, "resource_id": resource_id, "reasoning": "test"}


class TestEasyGrader:
    def test_perfect_score(self):
        actions = [
            _make_action("rightsize_resource", "res-easy-001"),
            _make_action("rightsize_resource", "res-easy-002"),
            _make_action("terminate_resource", "res-easy-003"),
            _make_action("terminate_resource", "res-easy-004"),
            _make_action("add_lifecycle_policy", "res-easy-005"),
            _make_action("rightsize_resource", "res-easy-006"),
        ]
        score = grade_task("startup-cleanup", actions, {}, {})
        assert score > 0.8

    def test_no_actions(self):
        score = grade_task("startup-cleanup", [], {}, {})
        assert score == 0.0

    def test_all_wrong_actions(self):
        actions = [
            _make_action("skip_resource", "res-easy-001"),
            _make_action("skip_resource", "res-easy-002"),
            _make_action("skip_resource", "res-easy-003"),
            _make_action("skip_resource", "res-easy-004"),
            _make_action("skip_resource", "res-easy-005"),
            _make_action("skip_resource", "res-easy-006"),
        ]
        score = grade_task("startup-cleanup", actions, {}, {})
        assert score < 0.2

    def test_determinism(self):
        actions = [
            _make_action("rightsize_resource", "res-easy-001"),
            _make_action("terminate_resource", "res-easy-003"),
        ]
        s1 = grade_task("startup-cleanup", actions, {}, {})
        s2 = grade_task("startup-cleanup", actions, {}, {})
        assert s1 == s2


class TestMediumGrader:
    def test_perfect_score(self):
        actions = [
            _make_action("skip_resource", "res-med-001"),
            _make_action("skip_resource", "res-med-002"),
            _make_action("skip_resource", "res-med-003"),
            _make_action("skip_resource", "res-med-004"),
            _make_action("skip_resource", "res-med-005"),
            _make_action("rightsize_resource", "res-med-006"),
            _make_action("rightsize_resource", "res-med-007"),
            _make_action("schedule_uptime", "res-med-008"),
            _make_action("rightsize_resource", "res-med-009"),
            _make_action("add_lifecycle_policy", "res-med-010"),
            _make_action("terminate_resource", "res-med-011"),
            _make_action("rightsize_resource", "res-med-012"),
            _make_action("rightsize_resource", "res-med-013"),
            _make_action("purchase_reservation", "res-med-014"),
            _make_action("add_lifecycle_policy", "res-med-015"),
        ]
        score = grade_task("mid-size-audit", actions, {}, {})
        assert score > 0.8

    def test_terminate_prod_penalty(self):
        """Terminating prod resources should lower score."""
        bad_actions = [
            _make_action("terminate_resource", "res-med-001"),
            _make_action("terminate_resource", "res-med-003"),
        ]
        good_actions = [
            _make_action("skip_resource", "res-med-001"),
            _make_action("skip_resource", "res-med-003"),
        ]
        bad_score = grade_task("mid-size-audit", bad_actions, {}, {})
        good_score = grade_task("mid-size-audit", good_actions, {}, {})
        assert good_score > bad_score

    def test_determinism(self):
        actions = [_make_action("skip_resource", "res-med-001")]
        s1 = grade_task("mid-size-audit", actions, {}, {})
        s2 = grade_task("mid-size-audit", actions, {}, {})
        assert s1 == s2


class TestHardGrader:
    def test_some_correct_actions(self):
        actions = [
            _make_action("skip_resource", "res-hard-001"),
            _make_action("skip_resource", "res-hard-009"),
            _make_action("rightsize_resource", "res-hard-024"),
            _make_action("terminate_resource", "res-hard-033"),
        ]
        score = grade_task("enterprise-finops", actions, {}, {})
        assert 0.0 < score < 1.0

    def test_unknown_task(self):
        score = grade_task("nonexistent-task", [], {}, {})
        assert score == 0.0

    def test_determinism(self):
        actions = [
            _make_action("skip_resource", "res-hard-001"),
            _make_action("rightsize_resource", "res-hard-004"),
        ]
        s1 = grade_task("enterprise-finops", actions, {}, {})
        s2 = grade_task("enterprise-finops", actions, {}, {})
        assert s1 == s2
