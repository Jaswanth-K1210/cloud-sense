from datetime import UTC, datetime, timedelta

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy.orm import sessionmaker

from backend.agent.fake_llm import FakeLLM
from backend.app import app
from backend.deps import services
from backend.memory.fake import InMemoryMemoryClient
from backend.store.db import get_session, init_db, make_engine
from backend.store.seed_demo import seed

REGION = "us-east-1"
ADMIN = {"X-User-Id": "u-admin"}
REVIEWER = {"X-User-Id": "u-reviewer"}


def launch_idle(ec2, cw, name: str) -> str:
    ami = ec2.describe_images(Owners=["amazon"])["Images"][0]["ImageId"]
    iid = ec2.run_instances(ImageId=ami, MinCount=1, MaxCount=1, InstanceType="t3.micro", TagSpecifications=[
        {"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": name}]}])["Instances"][0]["InstanceId"]
    now = datetime.now(UTC)
    cw.put_metric_data(Namespace="AWS/EC2", MetricData=[
        {"MetricName": "CPUUtilization", "Dimensions": [{"Name": "InstanceId", "Value": iid}],
         "Timestamp": now - timedelta(hours=h), "Value": 0.4} for h in range(1, 48)])
    return iid


@pytest.fixture
def client():
    engine = make_engine("sqlite://")
    init_db(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as s:
        seed(s)

    def session_override():
        with factory() as s:
            yield s

    old = (services.session_factory, services._memory, services._llm)
    services.session_factory, services.memory, services.llm = factory, InMemoryMemoryClient(), FakeLLM()
    app.dependency_overrides[get_session] = session_override
    with mock_aws():
        yield TestClient(app)
    app.dependency_overrides.clear()
    services.session_factory, services._memory, services._llm = old


def scan(client: TestClient) -> dict:
    sid = client.post("/orgs/acme/scans", headers=REVIEWER).json()["scan_id"]
    body = client.get(f"/orgs/acme/scans/{sid}", headers=REVIEWER).json()
    assert body["status"] == "done", body
    return body


def by_name(body: dict, section: str) -> dict:
    return {c["resource"]["name"]: c for c in body[section]}


def test_reject_teaches_lookalike_suppression(client: TestClient) -> None:
    ec2, cw = boto3.client("ec2", region_name=REGION), boto3.client("cloudwatch", region_name=REGION)
    launch_idle(ec2, cw, "orders-db-standby")
    launch_idle(ec2, cw, "dev-sandbox-3")

    r = client.post("/orgs/acme/accounts", headers=ADMIN, json={
        "alias": "prod", "aws_account_id": "123456789012", "role_arn": "local", "regions": [REGION]})
    assert r.status_code == 201

    first = scan(client)
    recommended = by_name(first, "recommended")
    assert {"orders-db-standby", "dev-sandbox-3"} <= set(recommended)
    standby = recommended["orders-db-standby"]
    assert standby["rule_id"] == "R1" and standby["action"] == "stop"

    # the reviewer rejects with a reason
    v = client.post(f"/candidates/{standby['id']}/verdict", headers=REVIEWER, json={
        "decision": "reject", "reason": "DR standby for orders-db, idle on purpose", "scope": "similar"})
    assert v.status_code == 201, v.text
    verdict = client.get(f"/verdicts/{v.json()['id']}", headers=REVIEWER).json()
    assert verdict["learning_status"] == "learned"
    assert "DR standby" in verdict["learned_rule"]["text"]
    rules = client.get("/orgs/acme/rules", headers=REVIEWER).json()
    assert rules[0]["text"] == "DR standby for orders-db, idle on purpose"

    # a brand-new untagged look-alike appears
    launch_idle(ec2, cw, "payments-db-standby")
    second = scan(client)
    suppressed = by_name(second, "suppressed")
    assert "payments-db-standby" in suppressed
    assert suppressed["payments-db-standby"]["agent"]["cited_memory_ids"] == [f"verdict-{standby['id']}"]
    assert "dev-sandbox-3" in by_name(second, "recommended")

    m = client.get("/orgs/acme/metrics", headers=REVIEWER).json()
    assert m["series"][0]["rejected"] == 1 and m["series"][0]["acceptance_rate"] == 0.0
    assert len([c for c in second["recommended"] if c["resource"]["name"] == "dev-sandbox-3"]) == 1  # deduped
    g = client.get(f"/graph/{second['id']}", headers=REVIEWER).json()
    assert any(n["name"] == "payments-db-standby" and n["status"] == "suppressed" for n in g["nodes"])


def test_auth_and_roles(client: TestClient) -> None:
    assert client.get("/orgs/acme", headers={}).status_code == 401
    assert client.get("/orgs/other", headers=ADMIN).status_code == 404
    r = client.post("/orgs/acme/accounts", headers=REVIEWER, json={
        "alias": "x", "aws_account_id": "1", "role_arn": "local"})
    assert r.status_code == 403
    assert client.delete("/orgs/acme/rules/x", headers=REVIEWER).status_code == 403
    assert client.get("/orgs/acme/users").status_code == 401
    assert len(client.get("/orgs/acme/users", headers=REVIEWER).json()) == 2


def test_scan_records_account_errors(client: TestClient) -> None:
    def boom(_):
        raise RuntimeError("AccessDenied")

    old = services.scan_account
    services.scan_account = boom
    try:
        client.post("/orgs/acme/accounts", headers=ADMIN, json={
            "alias": "broken", "aws_account_id": "1", "role_arn": "local"})
        body = scan(client)
        assert {"sandbox", "broken"} == {e["account"] for e in body["errors"]}
    finally:
        services.scan_account = old


def test_activity_lists_audit_events(client: TestClient) -> None:
    client.post("/orgs/acme/accounts", headers=ADMIN, json={"alias": "x", "aws_account_id": "1", "role_arn": "local"})
    rows = client.get("/orgs/acme/activity", headers=REVIEWER).json()
    assert rows[0]["event"] == "account_connected" and rows[0]["actor"] == "Ada Admin"
