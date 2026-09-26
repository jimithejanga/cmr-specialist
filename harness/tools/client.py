"""Thin client: the ONLY way harness code calls the tool module (PDF v3 §8).

Collects approval refs + evidence refs from the case/task, fires via
module.fire with the service token, and returns the envelope. Holds no
credentials and no DB handles.
"""
from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import select

SERVICE_TOKEN = None  # resolved from settings per call


def _token() -> str:
    from configs.settings import settings

    return settings.TOOL_MODULE_TOKEN


def _approval_ref(db, task_id: str) -> str | None:
    from harness.store import models as M
    ap = db.scalar(select(M.Approval).where(
        M.Approval.task_id == task_id, M.Approval.decision == "approved")
        .order_by(M.Approval.decided_at.desc()))
    return f"approval:{ap.id}" if ap else None


def _evidence_refs(db, task_id: str) -> list:
    """Evidence refs recorded on this task's steps so far."""
    from harness.store import models as M
    refs = []
    steps = db.scalars(select(M.RunStep).where(M.RunStep.task_id == task_id)).all()
    import json
    for s in steps:
        try:
            res = json.loads(s.result_json) if s.result_json else {}
        except Exception:
            continue
        if isinstance(res, dict):
            if res.get("evidence_ref"):
                refs.append(res["evidence_ref"])
            data = res.get("data") or {}
            if isinstance(data, dict):
                for k in ("status", "verdict"):
                    if data.get(k):
                        refs.append(f"{k}={data[k]}")
    return refs


def call_formulation(db, *, formulation_id: str, arguments: dict,
                     run_id: str | None = None, task_id: str | None = None,
                     case_id: str | None = None) -> dict[str, Any]:
    from harness.tools import module as M_
    from harness.tools import formulations as F

    form = F.CATALOG.get(formulation_id, None)
    key = None
    if form is not None and form.idempotency == "required" and task_id:
        key = hashlib.sha256(
            f"{task_id}|{formulation_id}|{sorted((arguments or {}).items())}".encode()
        ).hexdigest()[:16]
        key = f"{task_id}-{key}"
    return M_.fire(
        formulation_id=formulation_id, arguments=arguments or {},
        service_token=_token(), run_id=run_id, case_id=case_id,
        approval_ref=_approval_ref(db, task_id) if task_id else None,
        evidence_refs=_evidence_refs(db, task_id) if task_id else [],
        idempotency_key=key, audit_db=db)
