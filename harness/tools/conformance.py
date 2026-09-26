"""Conformance suite (PDF v3 §9): the exam paper any backend must pass.

Mock today, real CMR database tomorrow — identical score required before
cutover. Each exam returns (passed: bool, detail: str).
"""
from __future__ import annotations


def _fire(audit_db, **kw):
    from harness.tools import module as M
    kw.setdefault("service_token", "cmr-tool-token-dev")
    kw.setdefault("audit_db", audit_db)
    return M.fire(**kw)


def exam_1_known_receipt(audit_db):
    from harness.tools import module as M
    M.reset_mock()
    env = _fire(audit_db, formulation_id="CHECK.receipt.lookup",
                arguments={"rrr": "123456789012"})
    d = env.get("data") or {}
    ok = (env["status"] == "ok" and d.get("status") == "paid"
          and d.get("amount") == 5000 and d.get("linked_account") == "acct-X")
    return ok, f"status={env['status']} data={d}"


def exam_2_unknown_plate(audit_db):
    from harness.tools import module as M
    M.reset_mock()
    env = _fire(audit_db, formulation_id="CHECK.vehicle.lookup",
                arguments={"plate": "ZZZ000NOPE"})
    ok = env["status"] == "failed" and "not-found" in (env.get("error_ref") or "")
    return ok, f"status={env['status']} err={env.get('error_ref')}"


def exam_3_double_link(audit_db):
    from harness.tools import module as M
    M.reset_mock()
    kw = dict(formulation_id="WRITE.payment.link",
              arguments={"rrr": "123456789012", "account": "acct-Y"},
              approval_ref="approval:test", evidence_refs=["receipt=paid"],
              idempotency_key="exam3-key")
    e1 = _fire(audit_db, **kw)
    e2 = _fire(audit_db, **kw)
    d2 = (e2.get("data") or {})
    ok = (e1["status"] == "ok" and e2["status"] == "ok"
          and d2.get("duplicate") is True
          and M._db.receipts["123456789012"]["linked_account"] == "acct-Y")
    return ok, f"first={e1['status']} second_dup={d2.get('duplicate')}"


def exam_4_write_without_approval(audit_db):
    from harness.tools import module as M
    M.reset_mock()
    before = list(M._db.tokens_sent)
    env = _fire(audit_db, formulation_id="WRITE.token.resend",
                arguments={"profile_id": "prof-001", "medium": "phone"},
                idempotency_key="exam4-key")
    from harness.store import models as SM
    from sqlalchemy import select, func
    audits = audit_db.scalar(select(func.count()).select_from(SM.ToolAudit)) or 0
    ok = (env["status"] == "parked" and M._db.tokens_sent == before and audits >= 1)
    return ok, f"status={env['status']} side_effects={len(M._db.tokens_sent) - len(before)} audits={audits}"


def exam_5_write_without_evidence(audit_db):
    from harness.tools import module as M
    M.reset_mock()
    env = _fire(audit_db, formulation_id="WRITE.payment.link",
                arguments={"rrr": "123456789012", "account": "acct-Y"},
                approval_ref="approval:test", evidence_refs=[],
                idempotency_key="exam5-key")
    ok = env["status"] == "failed" and "receipt=paid" in (env.get("error_ref") or "")
    return ok, f"status={env['status']} err={env.get('error_ref')}"


def exam_6_check_timeout(audit_db):
    import time
    from harness.tools import module as M
    M.reset_mock(nimc="down")  # transient fault on verify path
    t0 = time.perf_counter()
    env = _fire(audit_db, formulation_id="CHECK.nin.verify",
                arguments={"nin": "12345678901"})
    dt = time.perf_counter() - t0
    ok = env["status"] == "failed" and "transient" in (env.get("error_ref") or "") and dt < 5.0
    M.reset_mock()
    return ok, f"status={env['status']} err={env.get('error_ref')} dt={dt:.2f}s"


EXAMS = [exam_1_known_receipt, exam_2_unknown_plate, exam_3_double_link,
         exam_4_write_without_approval, exam_5_write_without_evidence,
         exam_6_check_timeout]


def run_all(audit_db) -> list[tuple[str, bool, str]]:
    out = []
    for ex in EXAMS:
        try:
            passed, detail = ex(audit_db)
        except Exception as exc:  # exam itself must never crash the gate
            passed, detail = False, f"exam raised {type(exc).__name__}: {exc}"
        out.append((ex.__name__, passed, detail))
    return out
