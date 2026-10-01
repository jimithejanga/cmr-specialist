"""Registry change feed: every mutation leaves an attributable trace."""
import os
import tempfile

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"

from harness.store.database import SessionLocal, init_db  # noqa: E402
from harness.tools import module as mod  # noqa: E402
from registry import feed as feed_mod  # noqa: E402

init_db()
TOKEN = "cmr-tool-token-dev"


def _db():
    return SessionLocal()


def _fire(**kw):
    kw.setdefault("service_token", TOKEN)
    kw.setdefault("audit_db", _db())
    return mod.fire(**kw)


def setup_function(_):
    global _RESEED_ID
    mod.select_backend("relational")
    mod.reset_mock()
    # the reseed ceremony row marks the current world's beginning - everything
    # at or below it belongs to previous worlds and is ignored by these tests
    _RESEED_ID = mod.feed_changes()[0]["id"]


def _current(rows):
    return [c for c in rows if c["id"] > _RESEED_ID]


def teardown_function(_):
    mod.select_backend("legacy")
    mod.reset_mock()


def test_agent_transfer_leaves_attributable_trace():
    mod.insert_row("profiles", "08090001111",
                   {"profile_id": "prof-f", "phone": "08090001111",
                    "name": "Feed Buyer"})
    env = _fire(formulation_id="WRITE.transfer.initiate",
                arguments={"vehicle_id": "veh-001", "buyer_profile_id": "prof-f",
                           "doc_ref": "FEED1"},
                approval_ref="approval:t", evidence_refs=["owner=verified"],
                idempotency_key="feed-t1")
    assert env["status"] == "ok", env
    bio = _current(mod.feed_changes(table="vehicles", row_key="veh-001"))
    moves = [c for c in bio if c["action"] == "transfer"]
    assert len(moves) == 1
    move = moves[0]
    assert move["actor"] == "agent:WRITE.transfer.initiate"
    assert move["before"] == {"owner": "prof-001"}
    assert move["after"]["owner"] == "prof-f"
    assert move["after"]["transfer_ref"] == "TRF-0001"


def test_link_trace_shows_null_to_account():
    env = _fire(formulation_id="WRITE.payment.link",
                arguments={"rrr": "123456789012", "account": "acct-F"},
                approval_ref="approval:t", evidence_refs=["receipt=paid"],
                idempotency_key="feed-l1")
    assert env["status"] == "ok", env
    rows = _current(mod.feed_changes(table="receipts", row_key="123456789012"))
    links = [c for c in rows if c["action"] == "link"]
    assert len(links) == 1
    assert links[0]["actor"] == "agent:WRITE.payment.link"
    assert links[0]["before"] == {"linked_account": None}
    assert links[0]["after"] == {"linked_account": "acct-F"}


def test_failed_write_leaves_no_trace():
    before = len(_current(mod.feed_changes(table="vehicles", row_key="veh-001")))
    env = _fire(formulation_id="WRITE.transfer.initiate",
                arguments={"vehicle_id": "veh-001", "buyer_profile_id": "prof-ghost",
                           "doc_ref": "FEED2"},
                approval_ref="approval:t", evidence_refs=["owner=verified"],
                idempotency_key="feed-t2")
    assert env["status"] == "failed"
    after = len(_current(mod.feed_changes(table="vehicles", row_key="veh-001")))
    assert after == before  # rolled back with the refused transaction


def test_reseed_leaves_ceremony_row():
    rows = mod.feed_changes()
    assert rows[0]["action"] == "reseed" and rows[0]["actor"] == "system:reset"
    seeds = [c for c in rows if c["actor"] == "system:seed"]
    assert len(seeds) >= 4  # the deterministic world, marked as such


def test_feed_is_append_only_by_construction():
    assert not hasattr(feed_mod, "update") and not hasattr(feed_mod, "delete")
    assert not hasattr(feed_mod, "clear")
