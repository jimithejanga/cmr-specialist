"""Observability admin site: gating, mockDB explorer, queue monitor."""
import os
import tempfile

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from harness.api.main import app  # noqa: E402
from harness.store import models as M  # noqa: E402
from harness.store.database import init_db  # noqa: E402

init_db()
client = TestClient(app)


def _login(username, password, headers=None):
    """Register as machine actor (works whether or not users exist), then log in."""
    client.post("/auth/users", json={"username": username, "password": password},
                headers=headers or {"X-API-Key": "cmr-secret-key-2026"})
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _bootstrap_admin():
    h = _login("boss", "admin-pass-1")
    # order-independent: ensure admin flag directly (test privilege only)
    from harness.store.database import SessionLocal

    db = SessionLocal()
    try:
        u = db.scalar(select(M.User).where(M.User.username == "boss"))
        u.is_admin = 1
        db.commit()
    finally:
        db.close()
    me = client.get("/auth/me", headers=h).json()
    assert me["is_admin"] is True, me
    return h


def _make_plain(h):
    return _login("clerk", "clerk-pass-1", headers=h)


def test_gating():
    h = _bootstrap_admin()
    p = _make_plain(h)
    assert client.get("/admin/mockdb").status_code == 401
    assert client.get("/admin/mockdb", headers=p).status_code == 403
    assert client.get("/admin/mockdb", headers=h).status_code == 200
    assert client.get("/admin/queue", headers=p).status_code == 403
    assert client.get("/admin/queue", headers=h).status_code == 200


def test_mockdb_insert_is_synthetic_and_reset():
    h = _bootstrap_admin()
    bad = client.post("/admin/mockdb/receipts", json={}, headers=h)
    assert bad.status_code == 400
    bad = client.post("/admin/mockdb/nonexistent", json={"a": 1}, headers=h)
    assert bad.status_code == 400
    r = client.post("/admin/mockdb/receipts",
                    json={"rrr": "999900001111", "status": "paid", "amount": 5000},
                    headers=h)
    assert r.status_code == 200 and r.json()["synthetic"] is True
    dump = client.get("/admin/mockdb", headers=h).json()
    row = dump["tables"]["receipts"]["999900001111"]
    assert row["synthetic"] is True
    # authorship lives in the change feed now, not the tables
    r = client.post("/admin/mockdb/reset", headers=h)
    assert r.status_code == 200
    dump = client.get("/admin/mockdb", headers=h).json()
    assert "999900001111" not in dump["tables"]["receipts"]
    assert "123456789012" in dump["tables"]["receipts"]  # seed restored


def test_admin_pages_served():
    for p in ("", "/mockdb.html", "/harness.html", "/worker.html",
              "/knowledge.html", "/shared.js", "/shared.css"):
        r = client.get(f"/admin{p}")
        assert r.status_code == 200, p
    assert client.get("/admin/evil.html").status_code == 404
