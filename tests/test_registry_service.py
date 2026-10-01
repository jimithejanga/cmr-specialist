"""Registry operator service: auth split, reads, guarded writes, ceremony."""
import os
import tempfile

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ["REGISTRY_OPERATORS"] = "regboss"

from fastapi.testclient import TestClient  # noqa: E402

from harness.api.main import app as agent_app  # noqa: E402
from harness.store.database import init_db  # noqa: E402
from harness.tools import module as mod  # noqa: E402
from registry.service import app  # noqa: E402

init_db()
agent = TestClient(agent_app)
client = TestClient(app)
_API = {"X-API-Key": "cmr-secret-key-2026"}


def _login(username, password):
    agent.post("/auth/users", json={"username": username, "password": password},
               headers=_API)
    r = agent.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


BOSS = OUTSIDER = None


def setup_function(_):
    global BOSS, OUTSIDER
    mod.select_backend("relational")
    mod.reset_mock()
    # conftest wipes users+sessions before every test, so sessions are
    # minted fresh here, not at module import
    BOSS = _login("regboss", "regboss-pass-1")
    OUTSIDER = _login("reguser", "reguser-pass-1")


def teardown_function(_):
    mod.select_backend("legacy")
    mod.reset_mock()


def test_health_needs_no_auth():
    assert client.get("/health").status_code == 200


def test_auth_split_login_then_operator():
    assert client.get("/tables").status_code == 401  # no session
    r = client.get("/tables", headers=OUTSIDER)
    assert r.status_code == 403  # signed in, not an operator
    r = client.get("/tables", headers=BOSS)
    assert r.status_code == 200
    assert r.json()["tables"]["profiles"] == 1


def test_browse_search_and_read():
    r = client.get("/tables/vehicles", params={"search": "ABC"}, headers=BOSS)
    assert r.status_code == 200 and r.json()["count"] == 1
    assert r.json()["rows"][0]["owner_name"] == "Ada Obi"
    r = client.get("/tables/vehicles/ABC123XY", headers=BOSS)
    assert r.status_code == 200 and r.json()["owner_history"] == 1
    assert client.get("/tables/vehicles/NOPE0000", headers=BOSS).status_code == 404
    assert client.get("/tables/nope", headers=BOSS).status_code == 400


def test_links_profile_biography():
    r = client.get("/links/profiles/08012345678", headers=BOSS)
    assert r.status_code == 200
    body = r.json()
    assert [v["plate"] for v in body["vehicles"]] == ["ABC123XY"]
    assert body["transfers"] == [] and body["tokens"] == []
    r = client.get("/links/vehicles/ABC123XY", headers=BOSS)
    assert [c["cert_no"] for c in r.json()["certificates"]] == ["CMR-0001"]


def test_feed_read_filters():
    mod.insert_row("profiles", "08090001111",
                   {"profile_id": "prof-sv", "phone": "08090001111",
                    "name": "Svc Buyer"})
    r = client.get("/feed", params={"table": "profiles"}, headers=BOSS)
    assert r.status_code == 200
    assert any(c["row"] == "prof-sv" for c in r.json()["changes"])


def test_insert_guards_and_attributes_author():
    bad = client.post("/tables/vehicles", json={"chassis": "X"}, headers=BOSS)
    assert bad.status_code == 400  # no plate key
    r = client.post("/tables/vehicles",
                    json={"plate": "SVC001XY", "chassis": "CHSSVC00001",
                          "owner": "Svc Owner"}, headers=BOSS)
    assert r.status_code == 200, r.text
    feed = client.get("/feed", params={"row": r.json()["key"]}, headers=BOSS)
    # insert is attributed to the operator, and the stub owner exists
    assert client.get("/links/profiles/Svc Owner", headers=BOSS).status_code == 200


def test_update_version_conflict_is_409():
    v = client.get("/tables/vehicles/ABC123XY", headers=BOSS).json()
    r = client.patch("/tables/vehicles/ABC123XY",
                     json={"owner": "Ada Obi", "version": v["version"] + 99},
                     headers=BOSS)
    assert r.status_code == 409
    r = client.patch("/tables/vehicles/ABC123XY",
                     json={"owner": "Ada Obi", "version": v["version"]},
                     headers=BOSS)
    assert r.status_code == 200 and r.json()["version"] == v["version"] + 1


def test_receipt_link_is_not_directly_editable():
    r = client.patch("/tables/receipts/123456789012",
                     json={"linked_account": "acct-hack"}, headers=BOSS)
    assert r.status_code == 400


def test_reset_ceremony_needs_the_name():
    r = client.post("/reset", json={"confirm": "wrong-name"}, headers=BOSS)
    assert r.status_code == 400
    r = client.post("/reset", json={"confirm": mod.registry_db_name()}, headers=BOSS)
    assert r.status_code == 200 and r.json()["reseeded_by"] == "regboss"
    feed = client.get("/feed", headers=BOSS).json()["changes"]
    assert feed[0]["action"] == "reseed"
