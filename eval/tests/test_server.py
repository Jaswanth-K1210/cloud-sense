"""Tests for FastAPI server endpoints."""

import pytest
from fastapi.testclient import TestClient

from eval.cloudsense_env.server.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "CloudSense" in r.text


def test_status(client):
    r = client.get("/status")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["name"] == "cloudsense"


def test_reset_default_task(client):
    """Validator pings POST /reset with no params — must return 200."""
    r = client.post("/reset")
    assert r.status_code == 200
    data = r.json()
    assert "task_id" in data
    assert "resources" in data


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_tasks(client):
    r = client.get("/tasks")
    assert r.status_code == 200
    tasks = r.json()
    assert len(tasks) == 3
    ids = {t["id"] for t in tasks}
    assert "startup-cleanup" in ids
    assert "mid-size-audit" in ids
    assert "enterprise-finops" in ids


def test_reset(client):
    r = client.post("/reset?task_id=startup-cleanup")
    assert r.status_code == 200
    data = r.json()
    assert data["task_id"] == "startup-cleanup"
    assert len(data["resources"]) == 7 


def test_reset_invalid_task(client):
    r = client.post("/reset?task_id=nonexistent")
    assert r.status_code == 400


def test_step(client):
    client.post("/reset?task_id=startup-cleanup")
    r = client.post("/step", json={
        "action_type": "rightsize_resource",
        "resource_id": "res-easy-001",
        "new_config": {"instance_type": "t3.small"},
        "reasoning": "test",
    })
    assert r.status_code == 200
    data = r.json()
    assert "reward" in data
    assert "done" in data
    assert "observation" in data
    assert "info" in data


def test_state(client):
    client.post("/reset?task_id=startup-cleanup")
    r = client.get("/state")
    assert r.status_code == 200
    data = r.json()
    assert "resources" in data
    assert "current_cost" in data


def test_close(client):
    client.post("/reset?task_id=startup-cleanup")
    r = client.post("/close")
    assert r.status_code == 200
    assert r.json()["status"] == "closed"


def test_full_episode(client):
    """Run a complete easy episode through the API."""
    client.post("/reset?task_id=startup-cleanup")
    actions = [
        {"action_type": "rightsize_resource", "resource_id": "res-easy-001", "new_config": {"instance_type": "t3.small"}, "reasoning": "test"},
        {"action_type": "rightsize_resource", "resource_id": "res-easy-002", "new_config": {"instance_type": "db.t3.medium", "storage_gb": 50}, "reasoning": "test"},
        {"action_type": "terminate_resource", "resource_id": "res-easy-003", "reasoning": "unused"},
        {"action_type": "terminate_resource", "resource_id": "res-easy-004", "reasoning": "unused"},
        {"action_type": "add_lifecycle_policy", "resource_id": "res-easy-005", "reasoning": "rare access"},
        {"action_type": "rightsize_resource", "resource_id": "res-easy-006", "new_config": {"instance_type": "t3.micro"}, "reasoning": "test"},
    ]
    for action in actions:
        r = client.post("/step", json=action)
        assert r.status_code == 200

    # Last step should be done
    data = r.json()
    assert data["done"] is True
    assert "task_score" in data.get("info", {})

    client.post("/close")
