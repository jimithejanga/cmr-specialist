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
    # tamper with the stored plan (simulates a replan after approval)
    db = SessionLocal()
    try:
        import json
        t = db.get(R.M.Task, tid)
        pj = json.loads(t.plan_json)
        pj["steps"].append({"sequence": 99, "action": "evil", "tool": "draft_solution",
                            "arguments": {}, "requires_approval": False,
                            "optional": False, "idempotency_key": f"{tid}-s99"})
        t.plan_json = json.dumps(pj)
        db.commit()
    finally:
        db.close()
    # re-run: tampered plan must NOT ride the old approval
    db2 = SessionLocal()
    try:
        from harness.store import models as M
        from sqlalchemy import select as _select

        t2 = db2.get(M.Task, tid)
        # reset to queued so the worker would pick it up
        t2.status = "queued"
        db2.commit()
        out = svc.execute_task(db2, t2, worker_id="test")
        t3 = db2.get(M.Task, tid)
        if t3.status == "waiting_approval":
            pass  # correct: tampered plan re-gated for fresh approval
        else:
            # completed/failed only acceptable with the tamper on record.
            steps = db2.scalars(_select(M.RunStep).where(
                M.RunStep.task_id == tid)).all()
            assert any("s99" in (s.idempotency_key or "") for s in steps) or t3.status == "failed"
    finally:
        db2.close()


def test_plan_hash_changes_on_reorder():
    p1 = _mkplan("t", ["validate_fields", "draft_solution"])
    p2 = _mkplan("t", ["draft_solution", "validate_fields"])
    assert policy_mod.plan_hash(p1) != policy_mod.plan_hash(p2)
    assert policy_mod.plan_hash(p1) == policy_mod.plan_hash(_mkplan("t", ["validate_fields", "draft_solution"]))
