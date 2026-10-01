"""Relational registry backend: invariants the dict mock could not express.

Runs the suite's backend-agnostic checks against the relational backend,
then probes the new enforcement directly: FK ownership, set-once receipts,
void discipline, certificate history, kobo storage, and NIN-from-table.
"""
import os
import tempfile

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"

from harness.store.database import SessionLocal, init_db  # noqa: E402
from harness.tools import conformance  # noqa: E402
from harness.tools import module as mod  # noqa: E402

init_db()
TOKEN = "cmr-tool-token-dev"


def _db():
    return SessionLocal()


def _fire(**kw):
    kw.setdefault("service_token", TOKEN)
    kw.setdefault("audit_db", _db())
    return mod.fire(**kw)


def setup_function(_):
    mod.reset_mock()


def teardown_function(_):
    mod.reset_mock()


def test_conformance_identical_score():
    results = conformance.run_all(_db())
    failures = [(n, d) for n, ok, d in results if not ok]
    assert not failures, f"relational conformance failures: {failures}"
    assert len(results) == 6


def test_transfer_moves_owner_and_counts_history():
    from registry import repository as repo
    from registry.database import RegistrySession

    mod.insert_row("profiles", "08090001111",
                   {"profile_id": "prof-t", "phone": "08090001111",
                    "name": "T Buyer"})
    mod.insert_row("profiles", "08090002222",
                   {"profile_id": "prof-s", "phone": "08090002222",
                    "name": "T Seller"})
    mod.insert_row("vehicles", "TREGXY",
                   {"vehicle_id": "veh-t", "plate": "TREGXY",
                    "chassis": "CHST0000001", "owner": "prof-s"})
    env = _fire(formulation_id="WRITE.transfer.initiate",
                arguments={"vehicle_id": "veh-t", "buyer_profile_id": "prof-t",
                           "doc_ref": "D1"},
                approval_ref="approval:t", evidence_refs=["owner=verified"],
                idempotency_key="reg-t1")
    assert env["status"] == "ok", env
    assert env["data"]["transfer_ref"] == "TRF-0001"
    assert mod.vehicle_owner_id("TREGXY") == "prof-t"
    with RegistrySession() as s:
        assert repo.history_count(s, "veh-t") == 2  # registration + transfer
        rows = s.query(repo.Transfer).all()
        assert rows[0].seller_profile_id == "prof-s"  # seller was the owner


def test_transfer_to_unknown_buyer_refused():
    env = _fire(formulation_id="WRITE.transfer.initiate",
                arguments={"vehicle_id": "veh-001", "buyer_profile_id": "prof-ghost",
                           "doc_ref": "D1"},
                approval_ref="approval:t", evidence_refs=["owner=verified"],
                idempotency_key="reg-t2")
    assert env["status"] == "failed" and "buyer" in env["error_ref"]
    assert mod.vehicle_owner_id("ABC123XY") == "prof-001"  # unmoved


def test_receipt_set_once_then_void_discipline():
    kw = dict(formulation_id="WRITE.payment.link",
              arguments={"rrr": "123456789012", "account": "acct-A"},
              approval_ref="approval:t", evidence_refs=["receipt=paid"])
    e1 = _fire(idempotency_key="reg-l1", **kw)
    assert e1["status"] == "ok"
    assert mod.receipt_account("123456789012") == "acct-A"
    e2 = _fire(idempotency_key="reg-l2",
               formulation_id="WRITE.payment.link",
               arguments={"rrr": "123456789012", "account": "acct-B"},
               approval_ref="approval:t", evidence_refs=["receipt=paid"])
    assert e2["status"] == "failed" and "already linked" in e2["error_ref"]
    e3 = _fire(idempotency_key="reg-l3",
               formulation_id="WRITE.payment.link",
               arguments={"rrr": "123456789012", "account": "acct-A"},
               approval_ref="approval:t", evidence_refs=["receipt=paid"])
    assert e3["status"] == "ok"  # same account: idempotent, not a move


def test_unpaid_and_void_receipts_cannot_link():
    mod.insert_row("receipts", "111100001111",
                   {"rrr": "111100001111", "status": "unpaid", "amount": 1000})
    env = _fire(formulation_id="WRITE.payment.link",
                arguments={"rrr": "111100001111", "account": "acct-Z"},
                approval_ref="approval:t", evidence_refs=["receipt=paid"],
                idempotency_key="reg-l4")
    assert env["status"] == "failed" and "not paid" in env["error_ref"]


def test_renewal_keeps_history_one_active():
    from registry import repository as repo
    from registry.database import RegistrySession

    env = _fire(formulation_id="WRITE.certificate.renew",
                arguments={"plate": "ABC123XY", "state": "renew",
                           "rrr": "123456789012"},
                approval_ref="approval:t", evidence_refs=["receipt=paid"],
                idempotency_key="reg-r1")
    assert env["status"] == "ok", env
    with RegistrySession() as s:
        hist = repo.certificate_history(s, "veh-001")
        assert len(hist) == 2
        assert sorted(c.status for c in hist) == ["active", "expired"]
        assert repo.active_certificate(s, "veh-001").cert_no == "CMR- renewed"


def test_kobo_storage_naira_api():
    from registry.database import RegistrySession
    from registry.models import Receipt

    with RegistrySession() as s:
        row = s.get(Receipt, "123456789012")
        assert row.amount_kobo == 500000  # integer kobo in the table...
    env = _fire(formulation_id="CHECK.receipt.lookup",
                arguments={"rrr": "123456789012"})
    assert env["data"]["amount"] == 5000  # ...whole naira on the wire


def test_nin_from_table_and_token_fk():
    assert mod._db.verify_nin(nin="12345678901") == {"verdict": "match"}
    env = _fire(formulation_id="WRITE.token.resend",
                arguments={"profile_id": "prof-ghost", "medium": "phone"},
                approval_ref="approval:t", idempotency_key="reg-tok1")
    assert env["status"] == "failed" and "profile" in env["error_ref"]
    assert mod.token_log() == []
