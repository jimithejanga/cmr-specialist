"""Tool module tests (PDF v3): formulator catalog, firing pipeline,
append-only audit, harness integration, and the conformance gate."""
import os
import tempfile

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"

from sqlalchemy import func, select  # noqa: E402

from harness.agent import planner as planner_mod  # noqa: E402
from harness.agent import policy as policy_mod  # noqa: E402
from harness.agent.schemas import Plan, PlanStep  # noqa: E402
from harness.store import models as M  # noqa: E402
from harness.store.database import SessionLocal, init_db  # noqa: E402
from harness.tools import client as client_mod  # noqa: E402
from harness.tools import conformance  # noqa: E402
from harness.tools import formulations as F  # noqa: E402
from harness.tools import module as mod  # noqa: E402

init_db()
TOKEN = "cmr-tool-token-dev"


def _db():
    return SessionLocal()


def test_catalog_two_verbs():
    checks = [f for f in F.CATALOG.values() if f.verb == "CHECK"]
    writes = [f for f in F.CATALOG.values() if f.verb == "WRITE"]
    assert len(checks) == 8 and len(writes) == 7
    assert all(w.approval != "none" and w.idempotency == "required" for w in writes)
    assert all(c.approval == "none" for c in checks)
    assert all(w.retries == 0 for w in writes)  # writes never blind-retry


def test_check_known_receipt():
    mod.reset_mock()
    env = mod.fire(formulation_id="CHECK.receipt.lookup",
                   arguments={"rrr": "123456789012"},
                   service_token=TOKEN, audit_db=_db())
    assert env["status"] == "ok"
    assert env["data"]["status"] == "paid"
    assert env["evidence_ref"] and env["audit_id"]


def test_check_unknown_is_envelope_not_crash():
    mod.reset_mock()
    env = mod.fire(formulation_id="CHECK.vehicle.lookup",
                   arguments={"plate": "NOPE0000"},
                   service_token=TOKEN, audit_db=_db())
    assert env["status"] == "failed"
    assert "not-found" in env["error_ref"]


def test_rejects_bad_token_unknown_formulation_bad_schema():
    mod.reset_mock()
    db = _db()
    bad = mod.fire(formulation_id="CHECK.receipt.lookup",
                   arguments={"rrr": "123456789012"},
                   service_token="wrong", audit_db=db)
    assert bad["status"] == "failed" and "unauthorized" in bad["error_ref"]
    unknown = mod.fire(formulation_id="NOPE.nope", arguments={},
                       service_token=TOKEN, audit_db=db)
    assert "not formulated" in unknown["error_ref"]
    schema = mod.fire(formulation_id="CHECK.receipt.lookup",
                      arguments={"rrr": "123"}, service_token=TOKEN, audit_db=db)
    assert "pattern" in schema["error_ref"]


def test_write_parked_without_approval_no_side_effect():
    mod.reset_mock()
    env = mod.fire(formulation_id="WRITE.token.resend",
                   arguments={"profile_id": "prof-001", "medium": "phone"},
                   service_token=TOKEN, idempotency_key="t-nokey", audit_db=_db())
    assert env["status"] == "parked"
    assert mod._db.tokens_sent == []


def test_write_idempotent_single_side_effect():
    mod.reset_mock()
    kw = dict(formulation_id="WRITE.token.resend",
              arguments={"profile_id": "prof-001", "medium": "phone"},
              service_token=TOKEN, approval_ref="approval:t",
              idempotency_key="t-dup")
    db = _db()
    e1 = mod.fire(audit_db=db, **kw)
    e2 = mod.fire(audit_db=db, **kw)
    assert e1["status"] == "ok" and e2["status"] == "ok"
    assert e2["data"]["duplicate"] is True
    assert len(mod._db.tokens_sent) == 1


def test_write_refused_without_evidence():
    mod.reset_mock()
    env = mod.fire(formulation_id="WRITE.payment.link",
                   arguments={"rrr": "123456789012", "account": "acct-Y"},
                   service_token=TOKEN, approval_ref="approval:t",
                   evidence_refs=[], idempotency_key="t-noev", audit_db=_db())
    assert env["status"] == "failed"
    assert "receipt=paid" in env["error_ref"]
    assert mod._db.receipts["123456789012"]["linked_account"] == "acct-X"


def test_write_fires_with_approval_and_evidence():
    mod.reset_mock()
    env = mod.fire(formulation_id="WRITE.payment.link",
                   arguments={"rrr": "123456789012", "account": "acct-Y"},
                   service_token=TOKEN, approval_ref="approval:t",
                   evidence_refs=["receipt=paid"],
                   idempotency_key="t-ok", audit_db=_db())
    assert env["status"] == "ok"
    assert mod._db.receipts["123456789012"]["linked_account"] == "acct-Y"


def test_audit_append_only_and_masked():
    mod.reset_mock()
    db = _db()
    before = db.scalar(select(func.count()).select_from(M.ToolAudit)) or 0
    mod.fire(formulation_id="CHECK.receipt.lookup",
             arguments={"rrr": "123456789012"},
             service_token=TOKEN, run_id="run-1", case_id="case-1", audit_db=db)
    rows = db.scalars(select(M.ToolAudit).order_by(M.ToolAudit.created_at.desc())).all()
    assert len(rows) >= before + 1
    latest = rows[0]
    assert latest.verb == "CHECK" and latest.run_id == "run-1"
    assert "123456789012" not in (latest.arguments_masked or "")  # masked to last-4
    assert "9012" in (latest.arguments_masked or "")
    assert not hasattr(mod, "update_audit") and not hasattr(mod, "delete_audit")


def test_policy_two_rules():
    check_plan = Plan(task_type="t", steps=[
        PlanStep(sequence=0, action="a", tool="CHECK.receipt.lookup",
                 arguments={}, idempotency_key="k1")])
    d = policy_mod.check(check_plan)
    assert d.allowed and not d.needs_approval  # Rule 1: checks pass freely
    write_plan = Plan(task_type="t", steps=[
        PlanStep(sequence=0, action="a", tool="WRITE.payment.link",
                 arguments={}, requires_approval=True, idempotency_key="k2")])
    d2 = policy_mod.check(write_plan)
    assert d2.allowed and d2.needs_approval  # Rule 2: writes need approval


def test_family_plan_names_formulations():
    plan = planner_mod.build_family_plan(
        "payment_issue", "task-1",
        {"remita_rrr": "123456789012", "account_identifier": "acct-Y"})
    assert [s.tool for s in plan.steps] == F.FAMILY_PLANS["payment_issue"]
    assert all(s.tool in F.CATALOG for s in plan.steps)


def test_client_end_to_end_with_approval():
    mod.reset_mock()
    db = SessionLocal()
    try:
        from harness.store import repository as R
        case, _ = R.create_case(db, raw_text="paid RRR 123456789012", sender="t")
        task = R.create_task(db, case_id=case.id, task_type="payment_reconciliation",
                             instructions="link it")
        ap = R.request_approval(db, task_id=task.id, requested_action="link")
        ap.decision = "approved"
        from datetime import datetime, timezone
        ap.decided_at = datetime.now(timezone.utc)
        db.commit()
        env = client_mod.call_formulation(
            db, formulation_id="CHECK.receipt.lookup",
            arguments={"rrr": "123456789012"},
            run_id="run-e2e", task_id=task.id, case_id=case.id)
        assert env["status"] == "ok"
        audits = db.scalars(select(M.ToolAudit).where(M.ToolAudit.case_id == case.id)).all()
        assert len(audits) >= 1
    finally:
        db.close()


def test_conformance_gate_green():
    mod.reset_mock()
    results = conformance.run_all(_db())
    failures = [(n, d) for n, ok, d in results if not ok]
    assert not failures, f"conformance failures: {failures}"
    assert len(results) == 6
