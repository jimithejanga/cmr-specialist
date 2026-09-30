"""Phase 1: fail-closed auth. No anonymous actions; names only from sessions."""
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
    client.post("/auth/users", json={"username": username, "password": password},
                headers=headers or _API)
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}",
            "X-API-Key": "cmr-secret-key-2026"}


def test_strict_rejects_anonymous(monkeypatch):
    monkeypatch.setenv("STRICT_AUTH", "1")
    assert client.post("/cases", json={"text": "hello"}).status_code == 401
    assert client.get("/auth/me").status_code == 401
    assert client.post("/cases", json={"text": "hello"}, headers=_API).status_code != 401


def test_strict_approval_needs_session_user(monkeypatch):
    monkeypatch.setenv("STRICT_AUTH", "1")
    h = _login("phase1boss", "phase1-pass-1")
    c = client.post("/cases", json={"text": "confirm receipt 123456789012"}, headers=h)
    tid = client.post(f"/cases/{c.json()['case_id']}/tasks",
                      json={"task_type": "payment_reconciliation",
                            "instructions": "confirm", "approval_required": "always"},
                      headers=h).json()["id"]
    # forged name in body must NOT win; machine key alone must NOT decide
    r = client.post(f"/tasks/{tid}/approvals",
                    json={"decision": "approved", "approver": "Mallory",
                          "reason": "forged"}, headers=_API)
    assert r.status_code == 401
    r = client.post(f"/tasks/{tid}/approvals",
                    json={"decision": "approved", "approver": "Mallory",
                          "reason": "real"}, headers=h)
    assert r.status_code == 200, r.text
    task = client.get(f"/tasks/{tid}", headers=h).json()
    assert task["approvals"][0]["approver"] == "phase1boss"


def test_startup_gate_refuses_defaults(monkeypatch):
    import importlib

    SM = importlib.import_module("configs.settings")  # module, not the shadowed attr

    monkeypatch.setenv("STRICT_AUTH", "1")
    monkeypatch.setattr(SM.settings, "HARNESS_API_KEY", SM.DEFAULT_API_KEY)
    try:
        SM.assert_pilot_secrets()
        raised = False
    except RuntimeError:
        raised = True
    assert raised
