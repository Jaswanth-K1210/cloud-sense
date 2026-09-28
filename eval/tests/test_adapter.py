import pytest

from backend.scanner.models import Resource
from eval.cloudsense_env.adapter import to_resources
from eval.cloudsense_env.tasks import TASKS


@pytest.mark.parametrize("task_id", list(TASKS))
def test_every_resource_converts_and_keeps_edges(task_id: str) -> None:
    raw = TASKS[task_id]().load_account_raw()
    out = to_resources(raw)
    assert len(out) == len(raw)
    by_id = {r.id: r for r in out}
    for src in raw:
        res = by_id[src["resource_id"]]
        assert isinstance(res, Resource)
        assert res.depends_on == src["dependencies"]
        for dep in src["dependencies"]:
            assert res.id in by_id[dep].dependents


def test_iac_managed_from_tags() -> None:
    assert Resource(id="x", type="ec2", tags={"created_by": "terraform"}).iac_managed
    assert Resource(id="x", type="ec2", tags={"aws:cloudformation:stack-name": "s"}).iac_managed
    assert not Resource(id="x", type="ec2").iac_managed
