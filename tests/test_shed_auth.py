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


def test_bootstrap_login_and_me():
    r = client.post("/auth/users", json={"username": "ada", "password": "s3cure-pass"})
    assert r.status_code == 200, r.text
    r = client.post("/auth/login", json={"username": "ada", "password": "wrong-pass"})
    assert r.status_code == 401
    r = client.post("/auth/login", json={"username": "ada", "password": "s3cure-pass"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["actor"] == "ada"
    r = client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_second_user_requires_auth_and_short_password_rejected():
    r = client.post("/auth/users", json={"username": "musa", "password": "another-pass"})
    assert r.status_code == 401  # no longer bootstrap: login required
    r = client.post("/auth/login", json={"username": "ada", "password": "s3cure-pass"})
    token = r.json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    r = client.post("/auth/users", json={"username": "x", "password": "short"}, headers=h)
    assert r.status_code in (400, 422)
    r = client.post("/auth/users", json={"username": "musa", "password": "another-pass"}, headers=h)
    assert r.status_code == 200, r.text


def test_approval_carries_actor_name():
    r = client.post("/auth/login", json={"username": "ada", "password": "s3cure-pass"})
    h = {"Authorization": f"Bearer {r.json()['token']}"}
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
