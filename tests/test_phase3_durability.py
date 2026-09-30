"""Phase 3: one winner per race; guarantees survive restarts."""
import os
import tempfile

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"

import threading  # noqa: E402

from harness.store import repository as R  # noqa: E402
from harness.store.database import SessionLocal, init_db  # noqa: E402
from harness.tools import module as mod  # noqa: E402

init_db()


def test_lease_race_has_one_winner():
    db = SessionLocal()
    try:
        case = R.create_case_shell(db, title="race")
        task = R.create_task(db, case_id=case.id, task_type="general_support",
                             instructions="race-task")
        db.commit()
        task_id = task.id
    finally:
        db.close()
    winners = []
    barrier = threading.Barrier(8)

    def grab(i):
        d = SessionLocal()
        try:
            barrier.wait(timeout=10)
            t = R.lease_pending_task(d, worker_id=f"w{i}", timeout_s=600)
            if t is not None and t.status == "leased":
                winners.append((i, t.id))
        finally:
            d.close()

    threads = [threading.Thread(target=grab, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    mine = [w for w in winners if w[1] == task_id]
    assert len(mine) == 1, winners
    db = SessionLocal()
    try:
        t = db.get(R.M.Task, task_id)
        assert t.status == "leased" and t.attempts == 1
    finally:
        db.close()


def test_write_survives_mock_restart():
    db = SessionLocal()
    try:
        mod.reset_mock()
        e1 = mod.fire(formulation_id="WRITE.payment.link",
                      arguments={"rrr": "123456789012", "account": "acct-phase3"},
                      service_token="cmr-tool-token-dev",
                      approval_ref="approval:test",
                      evidence_refs=["receipt=paid"],
                      idempotency_key="phase3-key", audit_db=db)
        assert e1["status"] == "ok", e1
        linked = mod._db.receipts["123456789012"]["linked_account"]
        assert linked == "acct-phase3", linked
        # simulate process restart: fresh memory, same database
        mod._db = mod.MockDB.seeded()
        e2 = mod.fire(formulation_id="WRITE.payment.link",
                      arguments={"rrr": "123456789012", "account": "acct-phase3"},
                      service_token="cmr-tool-token-dev",
                      approval_ref="approval:test",
                      evidence_refs=["receipt=paid"],
                      idempotency_key="phase3-key", audit_db=db)
        assert e2["status"] == "ok", e2
        assert (e2.get("data") or {}).get("duplicate") is True
        # side effect NOT re-fired: fresh seed still points at the old account
        assert mod._db.receipts["123456789012"]["linked_account"] != "acct-phase3"
    finally:
        db.close()
        mod.reset_mock()
