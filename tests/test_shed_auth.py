"""Shed locks: bootstrap user, login, wrong-password refusal, actor on approvals."""
import os
import tempfile

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"

from fastapi.testclient import TestClient  # noqa: E402

from harness.api.main import app  # noqa: E402
from harness.store.database import init_db  # noqa: E402

init_db()
client = TestClient(app)


_API = {"X-API-Key": "cmr-secret-key-2026"}


def _login(username, password, headers=None):
    """Register as machine actor, then log in (suite shares one test DB)."""
    client.post("/auth/users", json={"username": username, "password": password},
                headers=headers or _API)
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_bootstrap_login_and_me():
    h = _login("ada", "s3cure-pass")
    token = h["Authorization"].split(" ", 1)[1]
    r = client.post("/auth/login", json={"username": "ada", "password": "wrong-pass"})
    assert r.status_code == 401
    r = client.get("/auth/me", headers=h)
    assert r.status_code == 200 and r.json()["actor"] == "ada"
    r = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_second_user_requires_auth_and_short_password_rejected():
    _login("seed", "seed-pass-1")  # guarantee users exist
    h = _login("ada", "s3cure-pass")
    r = client.post("/auth/users", json={"username": "musa-fresh", "password": "another-pass"})
    assert r.status_code == 401  # users exist: login required
    r = client.post("/auth/users", json={"username": "x", "password": "short"}, headers=h)
    assert r.status_code in (400, 422)
    r = client.post("/auth/users", json={"username": "musa-fresh", "password": "another-pass"}, headers=h)
    assert r.status_code == 200, r.text


def test_approval_carries_actor_name():
    h = _login("ada", "s3cure-pass")
    c = client.post("/cases", json={"text": "confirm receipt 123456789012"})
    tid = client.post(f"/cases/{c.json()['case_id']}/tasks",
                      json={"task_type": "payment_reconciliation",
                            "instructions": "confirm receipt",
                            "approval_required": "always"}, headers=h).json()["id"]
    r = client.post(f"/tasks/{tid}/approvals",
                    json={"decision": "approved", "reason": "shed test"}, headers=h)
    assert r.status_code == 200, r.text
    task = client.get(f"/tasks/{tid}").json()
    assert task["approvals"][0]["approver"] == "ada"
