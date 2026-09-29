import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy.orm import sessionmaker

from backend.agent.fake_llm import FakeLLM
from backend.app import app
from backend.auth import check_password, hash_password
from backend.deps import services
from backend.memory.fake import InMemoryMemoryClient
from backend.store.db import add_missing_columns, get_session, init_db, make_engine

PW = "correct horse battery"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("backend.config.settings.ALLOW_USER_HEADER", False)  # real login only
    engine = make_engine("sqlite://")
    init_db(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def session_override():
        with factory() as s:
            yield s

    old = (services.session_factory, services._memory, services._llm)
    services.session_factory, services.memory, services.llm = factory, InMemoryMemoryClient(), FakeLLM()
    app.dependency_overrides[get_session] = session_override
    with mock_aws():  # connecting an account verifies it against (simulated) AWS
        yield TestClient(app)
    app.dependency_overrides.clear()
    services.session_factory, services._memory, services._llm = old


def signup(c: TestClient, email="ravi@acme.io", name="Ravi Kumar") -> dict:
    r = c.post("/auth/signup", json={"name": name, "email": email, "password": PW})
    assert r.status_code == 201, r.text
    return r.json()


def H(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_password_hashing() -> None:
    h = hash_password(PW)
    assert h.startswith("scrypt$") and PW not in h
    assert check_password(PW, h) and not check_password("wrong password!", h) and not check_password(PW, None)


def test_signup_login_logout(client: TestClient) -> None:
    me = signup(client)
    assert me["user"]["role"] == "admin" and me["org"]["name"] == "Acme"
    assert me["org"]["settings"]["onboarding_step"] == 1
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"X-User-Id": me["user"]["id"]}).status_code == 401  # header disabled
    assert client.get("/auth/me", headers=H(me["token"])).json()["user"]["email"] == "ravi@acme.io"

    assert client.post("/auth/signup", json={"name": "x", "email": "RAVI@acme.io", "password": PW}).status_code == 409
    assert client.post("/auth/signup", json={"name": "x", "email": "a@b.io", "password": "short"}).status_code == 422
    assert client.post("/auth/login", json={"email": "ravi@acme.io", "password": "nope nope nope"}).status_code == 401
    tok = client.post("/auth/login", json={"email": "Ravi@Acme.io", "password": PW}).json()["token"]
    assert client.post("/auth/logout", headers=H(tok)).status_code == 204
    assert client.get("/auth/me", headers=H(tok)).status_code == 401
    assert client.get("/auth/me", headers=H(me["token"])).status_code == 200  # other session unaffected


def test_profile_and_password(client: TestClient) -> None:
    me = signup(client)
    other = client.post("/auth/login", json={"email": "ravi@acme.io", "password": PW}).json()["token"]
    r = client.put("/me", headers=H(me["token"]), json={"name": "Ravi K", "email": "ravi.k@acme.io"})
    assert r.json()["user"]["name"] == "Ravi K"
    bad = client.post("/me/password", headers=H(me["token"]), json={"current": "wrong wrong", "new": "x" * 12})
    assert bad.status_code == 400
    ok = client.post("/me/password", headers=H(me["token"]), json={"current": PW, "new": "new password 123"})
    assert ok.status_code == 204
    assert client.get("/auth/me", headers=H(other)).status_code == 401  # other devices signed out
    relogin = client.post("/auth/login", json={"email": "ravi.k@acme.io", "password": "new password 123"})
    assert relogin.status_code == 200


def test_workspaces_are_isolated(client: TestClient) -> None:
    a, b = signup(client), signup(client, email="sam@other.io", name="Sam")
    assert client.get(f"/orgs/{a['org']['id']}", headers=H(b["token"])).status_code == 404


def test_onboarding_flow(client: TestClient) -> None:
    me = signup(client)
    org, h = me["org"]["id"], H(me["token"])
    r = client.put(f"/orgs/{org}/workspace", headers=h,
                   json={"name": "Acme Corp", "role": "Platform", "team_size": "21–50", "spend": "$20k – $50k"})
    assert r.json()["name"] == "Acme Corp" and r.json()["memory_ready"] is True
    acct = client.post(f"/orgs/{org}/accounts", headers=h, json={"alias": "acme-prod", "role_arn": "local"})
    assert acct.status_code == 201
    assert client.patch(f"/accounts/{acct.json()['id']}", headers=h,
                        json={"alias": "prod", "regions": ["us-east-1", "ap-south-1"]}).json()["alias"] == "prod"
    s = client.put(f"/orgs/{org}/settings", headers=h, json={
        "services": ["ec2", "ebs"], "schedule": "daily", "slack": {"channel": "#cost"},
        "safety": {"mode": "recommend", "dry_run": True, "type_confirm": True}, "onboarding_step": 7,
        "onboarded": True}).json()
    assert s["settings"]["services"] == ["ec2", "ebs"] and s["dry_run"] is True
    assert client.put(f"/orgs/{org}/settings", headers=h, json={"evil": 1}).status_code == 400
    got = client.get(f"/orgs/{org}", headers=h).json()
    assert got["name"] == "Acme Corp" and got["settings"]["profile"]["role"] == "Platform"
    assert got["accounts"][0]["regions"] == ["us-east-1", "ap-south-1"]
    users = client.get(f"/orgs/{org}/users", headers=h).json()
    upd = client.patch(f"/orgs/{org}/users/{users[0]['id']}", headers=h, json={"slack_id": "U123"})
    assert upd.json()["slack_id"] == "U123"
    assert client.patch(f"/orgs/{org}/users/{users[0]['id']}", headers=h, json={"role": "viewer"}).status_code == 400


def test_first_scan_progress_and_recommend_only(client: TestClient, monkeypatch) -> None:
    from backend.deps import _offline_scan

    monkeypatch.setattr(services, "scan_account", _offline_scan)
    me = signup(client)
    org, h = me["org"]["id"], H(me["token"])
    client.post(f"/orgs/{org}/accounts", headers=h, json={"alias": "eval", "role_arn": "local"})
    client.put(f"/orgs/{org}/settings", headers=h, json={"safety": {"mode": "recommend"}})
    sid = client.post(f"/orgs/{org}/scans", headers=h).json()["scan_id"]
    scan = client.get(f"/orgs/{org}/scans/{sid}", headers=h).json()
    assert scan["status"] == "done" and scan["progress"]["step"] == 7
    assert sum(scan["progress"]["counts"].values()) == scan["resource_count"]
    cand = scan["recommended"][0]
    client.post(f"/candidates/{cand['id']}/verdict", headers=h, json={"decision": "approve"})
    r = client.post(f"/candidates/{cand['id']}/execute", headers=h)
    assert r.status_code == 409 and "Recommend-only" in r.json()["detail"]


def test_add_missing_columns_is_additive() -> None:
    from sqlalchemy import create_engine, inspect, text

    eng = create_engine("sqlite://")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE orgs (id VARCHAR(64) PRIMARY KEY, name VARCHAR(200), "
                       "hindsight_bank VARCHAR(200))"))
        c.execute(text("INSERT INTO orgs VALUES ('keep', 'Keep me', 'org-keep')"))
    added = add_missing_columns(eng)
    assert "orgs.settings_json" in added
    assert "settings_json" in {col["name"] for col in inspect(eng).get_columns("orgs")}
    with eng.connect() as c:
        assert c.execute(text("select name from orgs")).scalar() == "Keep me"


async def test_scheduler_runs_due_orgs_only(client: TestClient, monkeypatch) -> None:
    from backend import scheduler
    from backend.deps import _offline_scan

    monkeypatch.setattr(services, "scan_account", _offline_scan)
    daily, manual = signup(client), signup(client, email="m@other.io")
    for me, sched in ((daily, "daily"), (manual, "manual")):
        client.post(f"/orgs/{me['org']['id']}/accounts", headers=H(me["token"]),
                    json={"alias": "a", "role_arn": "local"})
        client.put(f"/orgs/{me['org']['id']}/settings", headers=H(me["token"]),
                   json={"schedule": sched, "onboarded": True})
    assert await scheduler.run_due(services) == [daily["org"]["id"]]
    assert await scheduler.run_due(services) == []  # just scanned: not due again for a day


def test_candidate_detail_override_rules_and_activity(client: TestClient, monkeypatch) -> None:
    from backend.deps import _offline_scan

    monkeypatch.setattr(services, "scan_account", _offline_scan)
    me = signup(client)
    org, h = me["org"]["id"], H(me["token"])
    client.post(f"/orgs/{org}/accounts", headers=h, json={"alias": "eval", "role_arn": "local"})
    sid = client.post(f"/orgs/{org}/scans", headers=h).json()["scan_id"]
    scan = client.get(f"/orgs/{org}/scans/{sid}", headers=h).json()
    cand = scan["recommended"][0]
    assert "metrics" in cand["resource"] and "instance_type" in cand["resource"]

    detail = client.get(f"/candidates/{cand['id']}", headers=h).json()
    assert detail["candidate"]["id"] == cand["id"] and detail["plan"]["steps"]
    assert all(step["text"] for step in detail["plan"]["steps"])

    # reject -> learned rule; rescan -> look-alike skipped; rules show what they protected
    client.post(f"/candidates/{cand['id']}/verdict", headers=h,
                json={"decision": "reject", "reason": "Nightly batch worker, spikes at 2am", "scope": "similar"})
    sid2 = client.post(f"/orgs/{org}/scans", headers=h).json()["scan_id"]
    scan2 = client.get(f"/orgs/{org}/scans/{sid2}", headers=h).json()
    skipped = scan2["suppressed"][0]
    rules = client.get(f"/orgs/{org}/rules", headers=h).json()
    assert any(skipped["resource"]["name"] in r["protected"] for r in rules)
    report = client.post(f"/orgs/{org}/rules/{rules[0]['id']}/report", headers=h, json={"reason": "wrong"})
    assert report.status_code == 204

    over = client.post(f"/candidates/{skipped['id']}/override", headers=h)
    assert over.status_code == 200 and over.json()["status"] == "pending"
    assert client.post(f"/candidates/{skipped['id']}/override", headers=h).status_code == 409

    events = [e["event"] for e in client.get(f"/orgs/{org}/activity", headers=h).json()]
    for ev in ("scan_started", "scan_finished", "rule_learned", "override", "rule_reported"):
        assert ev in events, ev
