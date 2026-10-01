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
        e1 = mod.fire(formulation_id="WRITE.token.resend",
                      arguments={"profile_id": "prof-001", "medium": "phone"},
                      service_token="cmr-tool-token-dev",
                      approval_ref="approval:test",
                      idempotency_key="phase3-key", audit_db=db)
        assert e1["status"] == "ok", e1
        assert len(mod.token_log()) == 1
        # simulate process restart: fresh memory, same database
        mod.simulate_restart()
        e2 = mod.fire(formulation_id="WRITE.token.resend",
                      arguments={"profile_id": "prof-001", "medium": "phone"},
                      service_token="cmr-tool-token-dev",
                      approval_ref="approval:test",
                      idempotency_key="phase3-key", audit_db=db)
        assert e2["status"] == "ok", e2
        assert (e2.get("data") or {}).get("duplicate") is True
        # side effect NOT re-fired: legacy memory was wiped (0 tokens on the
        # fresh copy); the relational database kept exactly the one write
        assert len(mod.token_log()) == (1 if mod.backend_name() == "relational" else 0)
    finally:
        db.close()
        mod.reset_mock()
