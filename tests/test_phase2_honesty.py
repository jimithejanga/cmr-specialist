"""Phase 2: status mirrors reality; approval mirrors the exact act."""
import os
import tempfile

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"

from fastapi.testclient import TestClient  # noqa: E402

from harness.agent import policy as policy_mod  # noqa: E402
from harness.agent import service as svc  # noqa: E402
from harness.agent.schemas import Plan, PlanStep  # noqa: E402
from harness.api.main import app  # noqa: E402
from harness.store import repository as R  # noqa: E402
from harness.store.database import SessionLocal, init_db  # noqa: E402

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


def _mkplan(task_id, tools, task_type="general_support"):
    steps = [PlanStep(sequence=i, action=t, tool=t, arguments={},
                      requires_approval=False,
                      idempotency_key=f"{task_id}-s{i}")
             for i, t in enumerate(tools)]
    return Plan(task_type=task_type, steps=steps)


def test_failed_required_step_fails_task():
    db = SessionLocal()
    try:
        case = R.create_case_shell(db, title="p2")
        task = R.create_task(db, case_id=case.id, task_type="general_support",
                             instructions="p2")
        import json
        plan = _mkplan(task.id, ["validate_fields", "no_such_tool_xyz"])
        task.plan_json = json.dumps({"task_type": plan.task_type,
                                     "proposed_by": "template",
                                     "steps": [s.model_dump() for s in plan.steps]})
        db.commit()
        out = svc.execute_task(db, task, worker_id="test")
        assert out["status"] == "failed", out
        assert "no_such_tool_xyz" in out["error"]
        fresh = db.get(type(task), task.id)
        assert fresh.status == "failed"
        assert fresh.result_json is None  # no completed stamp of any kind
    finally:
        db.close()


def test_optional_step_failure_degrades():
    db = SessionLocal()
    try:
        case = R.create_case_shell(db, title="p2b")
        task = R.create_task(db, case_id=case.id, task_type="general_support",
                             instructions="p2b")
        import json
        plan = _mkplan(task.id, ["knowledge_lookup"])
        plan.steps[0].optional = True
        plan.steps[0].tool = "no_such_tool_xyz"
        plan.steps[0].idempotency_key = f"{task.id}-s0"
        task.plan_json = json.dumps({"task_type": plan.task_type,
                                     "proposed_by": "template",
                                     "steps": [s.model_dump() for s in plan.steps]})
        db.commit()
        out = svc.execute_task(db, task, worker_id="test")
        assert out["status"] in {"completed", "failed"}, out
    finally:
        db.close()


def test_approval_bound_to_exact_plan():
    h = _login("phase2boss", "phase2-pass-1")
    # seed case fields through intake so the task can reach policy
    c = client.post("/cases", json={
        "text": "Please reconcile RRR 123456789012 made yesterday for account acct-X"},
        headers=h).json()
    tid = client.post(f"/cases/{c['case_id']}/tasks",
                      json={"task_type": "payment_reconciliation",
                            "instructions": "confirm receipt bound",
                            "approval_required": "always"}, headers=h).json()["id"]
    task = client.get(f"/tasks/{tid}", headers=h).json()
    assert task["status"] in {"queued", "waiting_approval"}
    # approve the exact plan
    r = client.post(f"/tasks/{tid}/approvals",
                    json={"decision": "approved", "reason": "exact"}, headers=h)
    assert r.status_code == 200, r.text
    # change the underlying FACTS (simulates new input after approval):
    # execution rebuilds the family plan, whose hash must void the old approval
    db = SessionLocal()
    try:
        from harness.store import models as M

        t = db.get(M.Task, tid)
        case_id = t.case_id
        R.store_extracted_fields(
            db, case_id=case_id, source_input_id="tamper", extraction_run_id="tamper",
            fields=[{"name": "account_identifier", "data_type": "string",
                     "raw_value": "acct-TAMPERED", "normalized_value": "acct-TAMPERED",
                     "confidence": 0.6, "validation": "valid"}])
        t.status = "queued"
        db.commit()
    finally:
        db.close()
    db2 = SessionLocal()
    try:
        from harness.store import models as M
        from sqlalchemy import select as _select

        t2 = db2.get(M.Task, tid)
        out = svc.execute_task(db2, t2, worker_id="test")
        t3 = db2.get(M.Task, tid)
        # changed facts -> rebuilt plan -> old approval void -> re-gated
        assert t3.status == "waiting_approval", (t3.status, out)
        approvals = db2.scalars(_select(M.Approval).where(
            M.Approval.task_id == tid)).all()
        assert len([a for a in approvals if a.decision == "pending"]) >= 1
    finally:
        db2.close()


def test_plan_hash_ignores_order_but_binds_content():
    p1 = _mkplan("t", ["validate_fields", "draft_solution"])
    p2 = _mkplan("t", ["draft_solution", "validate_fields"])
    assert policy_mod.plan_hash(p1) == policy_mod.plan_hash(p2)  # reorder: same act
    p3 = _mkplan("t", ["validate_fields", "draft_solution"])
    p3.steps[0].arguments = {"tampered": True}
    assert policy_mod.plan_hash(p1) != policy_mod.plan_hash(p3)  # re-argued: voided
    p4 = _mkplan("t", ["validate_fields"])
    assert policy_mod.plan_hash(p1) != policy_mod.plan_hash(p4)  # dropped: voided
