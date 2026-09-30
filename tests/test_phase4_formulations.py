"""Phase 4: formulation routing end to end + evidence rules."""
import os
import tempfile

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"

from fastapi.testclient import TestClient  # noqa: E402

from harness.agent import service as svc  # noqa: E402
from harness.agent import validator as validator_mod  # noqa: E402
from harness.agent.schemas import CitationHit  # noqa: E402
from harness.api.main import app  # noqa: E402
from harness.store import models as M  # noqa: E402
from harness.store import repository as R  # noqa: E402
from harness.store.database import SessionLocal, init_db  # noqa: E402
from harness.tools import module as mod  # noqa: E402
from sqlalchemy import select  # noqa: E402

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


def _fields(db, case_id, pairs):
    R.store_extracted_fields(
        db, case_id=case_id, source_input_id="t", extraction_run_id="t",
        fields=[{"name": n, "data_type": "string", "raw_value": v,
                 "normalized_value": v, "confidence": 0.8, "validation": "valid"}
                for n, v in pairs])


def test_ownership_writes_end_to_end():
    h = _login("phase4boss", "phase4-pass-1")
    mod.reset_mock()
    # synthetic world: seller owns the car, buyer exists with a phone
    mod._db.profiles["08090001111"] = {"profile_id": "prof-p4", "phone": "08090001111",
                                       "name": "P4 Buyer", "synthetic": True}
    mod._db.vehicles["P4TESTXY"] = {"vehicle_id": "veh-p4", "plate": "P4TESTXY",
                                    "chassis": "CHSP4000001", "owner": "P4 Seller",
                                    "cert_state": "valid", "owner_history": 1,
                                    "synthetic": True}
    db = SessionLocal()
    try:
        case = R.create_case_shell(db, title="p4 ownership")
        _fields(db, case.id, [("plate_number", "P4TESTXY"),
                              ("buyer_name", "P4 Buyer"),
                              ("seller_name", "P4 Seller"),
                              ("phone", "08090001111")])
        task = svc.queue_task(db, case_id=case.id, task_type="change_of_ownership",
                              instructions="transfer it", approval_required="always")
        db.commit()
        tid = task.id
    finally:
        db.close()
    from unittest.mock import patch

    with patch("harness.agent.llm.propose_json", return_value=None):
        db = SessionLocal()
        try:
            t = db.get(M.Task, tid)
            out = svc.execute_task(db, t, worker_id="test")
            assert out["status"] == "waiting_approval", out
        finally:
            db.close()
        r = client.post(f"/tasks/{tid}/approvals",
                        json={"decision": "approved", "reason": "p4 e2e"}, headers=h)
        assert r.status_code == 200, r.text
        db = SessionLocal()
        try:
            t = db.get(M.Task, tid)
            t.status = "queued"
            db.commit()
            out = svc.execute_task(db, t, worker_id="test")
            assert out["status"] == "completed", out
            assert mod._db.vehicles["P4TESTXY"]["owner"] == "prof-p4", \
                mod._db.vehicles["P4TESTXY"]
            audits = db.scalars(select(M.ToolAudit).where(
                M.ToolAudit.formulation_id == "WRITE.transfer.initiate")).all()
            assert len(audits) >= 1
            assert any(a.case_id == case.id for a in audits)
        finally:
            db.close()
            mod.reset_mock()


def test_unsupported_figure_falls_back():
    hits = [CitationHit(version_id="v", chunk_id="c", document_id="d",
                        text="Renewal requires a payment receipt.", page=1,
                        locator="1", score=0.9)]
    bad = validator_mod.validate_knowledge_answer(
        "The fee of 12500 NGN is verified and approved.", hits)
    assert not bad.valid and bad.fallback and "12500" in bad.reason
    good = validator_mod.validate_knowledge_answer(
        "Bring your payment receipt to renew.", hits)
    assert good.valid


def test_viability_prunes_unresolvable():
    from harness.tools import formulations as F

    assert F.viable_family_plan("payment_issue", {}) == []
    assert F.viable_family_plan("payment_issue",
                                {"remita_rrr": "123456789012",
                                 "account_identifier": "a"}) == [
        "CHECK.receipt.lookup", "WRITE.payment.link"]
    assert F.viable_family_plan(
        "change_of_ownership",
        {"plate_number": "P", "buyer_name": "B", "seller_name": "S",
         "phone": "0801"}) == F.FAMILY_PLANS["change_of_ownership"]


def test_pruned_writes_wait_with_prompts():
    from harness.tools import formulations as F

    assert F.blocking_inputs("change_of_ownership",
                             {"plate_number": "P", "buyer_name": "B",
                              "seller_name": "S"}) == ["phone", "email", "nin", "tin"]
    assert F.blocking_inputs("payment_issue", {"remita_rrr": "R"}) == ["account"]
    db = SessionLocal()
    try:
        case = R.create_case_shell(db, title="p4 blocked")
        _fields(db, case.id, [("plate_number", "P4X"), ("buyer_name", "B"),
                              ("seller_name", "S")])
        task = R.create_task(db, case_id=case.id, task_type="change_of_ownership",
                             instructions="blocked transfer")
        db.commit()
        out = svc.execute_task(db, task, worker_id="test")
        assert out["status"] == "waiting_for_input", out
        assert "phone" in out["missing"]
        assert "phone" in out["prompts"]
        fresh = db.get(M.Task, task.id)
        assert fresh.status == "waiting_for_input"
        assert fresh.result_json is None
    finally:
        db.close()
