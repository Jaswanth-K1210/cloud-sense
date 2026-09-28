from backend.graph.blast_radius import blast_radius
from eval.cloudsense_env.environment import CloudSenseEnv


def test_transitive_chain() -> None:
    # lb <- ec2 <- rds  (ec2 depends on lb, rds-client depends on ec2)
    graph = {"lb": ["ec2-a", "ec2-b"], "ec2-a": ["worker"]}
    assert blast_radius(graph, "lb") == ["ec2-a", "ec2-b", "worker"]


def test_no_dependents() -> None:
    assert blast_radius({"a": ["b"]}, "b") == []
    assert blast_radius({}, "missing") == []


def test_cycle_terminates_and_excludes_start() -> None:
    graph = {"a": ["b"], "b": ["c"], "c": ["a"]}
    assert blast_radius(graph, "a") == ["b", "c"]


def test_diamond_visits_once() -> None:
    graph = {"a": ["b", "c"], "b": ["d"], "c": ["d"]}
    assert blast_radius(graph, "a") == ["b", "c", "d"]


def test_env_uses_shared_function() -> None:
    env = CloudSenseEnv()
    env.reset("enterprise-finops")
    graph = env._dependents_graph()
    for r in env.current_resources:
        rid = r["resource_id"]
        direct = {x["resource_id"] for x in env.current_resources if rid in x.get("dependencies", [])}
        assert direct <= set(blast_radius(graph, rid))
