"""Repository: typed persistence + durable job leasing + versioned extraction."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Iterable

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from harness.store import models as M


def _now():
    return datetime.now(timezone.utc)


# ── cases ────────────────────────────────────────────────────────────────────

def create_case_shell(
    db: Session,
    *,
    title: str | None = None,
    source_channel: str = "api",
    owner: str | None = None,
    external_reference: str | None = None,
) -> M.Case:
    """Create a case row without an input (caller stores input via add_message)."""
    case = M.Case(
        title=title or "Untitled case",
        status="open",
        source_channel=source_channel,
        owner=owner,
        external_reference=external_reference,
    )
    db.add(case)
    db.flush()
    db.add(M.CaseEvent(case_id=case.id, actor="system", event_type="case.created",
                       new_state="open", payload_json=json.dumps({})))
    db.commit()
    db.refresh(case)
    return case


def create_case(
    db: Session,
    *,
    title: str | None = None,
    raw_text: str,
    sender: str | None = None,
    source_channel: str = "api",
    owner: str | None = None,
    external_reference: str | None = None,
) -> tuple[M.Case, M.CaseInput]:
    case = M.Case(
        title=title or (raw_text[:80] if raw_text else "Untitled case"),
        status="open",
        source_channel=source_channel,
        owner=owner,
        external_reference=external_reference,
    )
    db.add(case)
    db.flush()
    inp = M.CaseInput(case_id=case.id, raw_text=raw_text, sender=sender)
    db.add(inp)
    db.flush()
    db.add(M.CaseEvent(case_id=case.id, actor=sender or "user", event_type="case.created",
                       new_state="open", payload_json=json.dumps({"input_id": inp.id})))
    db.commit()
    db.refresh(case)
    return case, inp


def add_message(db: Session, *, case_id: str, raw_text: str, sender: str | None = None) -> M.CaseInput:
    inp = M.CaseInput(case_id=case_id, raw_text=raw_text, sender=sender)
    db.add(inp)
    case = db.get(M.Case, case_id)
    if case:
        case.updated_at = _now()
    db.add(M.CaseEvent(case_id=case_id, actor=sender or "user", event_type="case.message_added",
                       payload_json=json.dumps({"input_id": inp.id})))
    db.commit()
    db.refresh(inp)
    return inp


def _decode_norm(value: str | None) -> Any:
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return value  # legacy plain-string storage


def get_case_state(db: Session, case_id: str) -> dict[str, Any] | None:
    case = db.get(M.Case, case_id)
    if not case:
        return None
    inputs = db.scalars(select(M.CaseInput).where(M.CaseInput.case_id == case_id)
                        .order_by(M.CaseInput.received_at.asc())).all()
    # latest revision per field name
    fields = db.scalars(select(M.ExtractedField).where(M.ExtractedField.case_id == case_id)
                        .order_by(M.ExtractedField.name, M.ExtractedField.version.desc())).all()
    latest: dict[str, M.ExtractedField] = {}
    history: dict[str, int] = {}
    for f in fields:
        history[f.name] = history.get(f.name, 0) + 1
        if f.name not in latest:
            latest[f.name] = f
    tasks = db.scalars(select(M.Task).where(M.Task.case_id == case_id)
                       .order_by(M.Task.created_at.desc())).all()
    events = db.scalars(select(M.CaseEvent).where(M.CaseEvent.case_id == case_id)
                        .order_by(M.CaseEvent.created_at.desc()).limit(50)).all()
    return {
        "case": {
            "id": case.id, "title": case.title, "status": case.status,
            "source_channel": case.source_channel, "owner": case.owner,
            "external_reference": case.external_reference,
            "created_at": case.created_at.isoformat() if case.created_at else None,
            "updated_at": case.updated_at.isoformat() if case.updated_at else None,
        },
        "messages": [{"id": i.id, "raw_text": i.raw_text, "sender": i.sender,
                      "received_at": i.received_at.isoformat() if i.received_at else None} for i in inputs],
        "fields": {name: {
            "name": f.name, "data_type": f.data_type, "raw_value": f.raw_value,
            "normalized_value": _decode_norm(f.normalized_value),
            "confidence": f.confidence, "validation": f.validation, "version": f.version,
            "accepted_by": f.accepted_by, "source_input_id": f.source_input_id,
            "extraction_run_id": f.extraction_run_id, "revisions": history.get(name, 1),
        } for name, f in latest.items()},
        "tasks": [{"id": t.id, "task_type": t.task_type, "status": t.status,
                   "waiting_reason": t.waiting_reason, "error_ref": t.error_ref,
                   "created_at": t.created_at.isoformat() if t.created_at else None} for t in tasks],
        "recent_events": [{"event_type": e.event_type, "actor": e.actor,
                           "created_at": e.created_at.isoformat() if e.created_at else None} for e in events],
    }


# ── versioned extraction ─────────────────────────────────────────────────────

def store_extracted_fields(
    db: Session,
    *,
    case_id: str,
    source_input_id: str,
    extraction_run_id: str,
    fields: Iterable[dict[str, Any]],
    accepted_by: str = "model",
) -> list[M.ExtractedField]:
    out: list[M.ExtractedField] = []
    for fd in fields:
        name = fd["name"]
        max_v = db.scalar(select(func.max(M.ExtractedField.version))
                          .where(M.ExtractedField.case_id == case_id, M.ExtractedField.name == name)) or 0
        norm = fd.get("normalized_value")
        row = M.ExtractedField(
            case_id=case_id, source_input_id=source_input_id,
            extraction_run_id=extraction_run_id, name=name,
            data_type=fd.get("data_type", "string"), raw_value=fd.get("raw_value"),
            normalized_value=json.dumps(norm, default=str) if norm is not None else None,
            confidence=fd.get("confidence"), validation=fd.get("validation", "pending"),
            version=max_v + 1, accepted_by=accepted_by,
        )
        db.add(row)
        out.append(row)
    db.add(M.CaseEvent(case_id=case_id, actor=accepted_by, event_type="case.fields_extracted",
                       payload_json=json.dumps({"count": len(out), "run_id": extraction_run_id})))
    db.commit()
    return out


# ── tasks / durable queue ────────────────────────────────────────────────────

def _idem_key(case_id: str, task_type: str, instructions: str | None) -> str:
    h = hashlib.sha256(f"{case_id}|{task_type}|{instructions or ''}".encode()).hexdigest()[:16]
    return f"{task_type}-{h}"


def create_task(
    db: Session, *, case_id: str, task_type: str,
    instructions: str | None = None, approval_required: str = "never",
    idempotency_key: str | None = None, max_attempts: int = 3,
) -> M.Task:
    key = idempotency_key or _idem_key(case_id, task_type, instructions)
    existing = db.scalar(select(M.Task).where(M.Task.idempotency_key == key))
    if existing:
        return existing
    task = M.Task(case_id=case_id, task_type=task_type, instructions=instructions,
                  status="queued", approval_required=approval_required,
                  idempotency_key=key, max_attempts=max_attempts)
    db.add(task)
    db.add(M.CaseEvent(case_id=case_id, actor="system", event_type="task.created",
                       new_state="queued", payload_json=json.dumps({"task_id": task.id, "task_type": task_type})))
    db.commit()
    db.refresh(task)
    return task


def lease_pending_task(db: Session, *, worker_id: str, timeout_s: int = 600) -> M.Task | None:
    """Lease one queued task, or reclaim an expired lease. Single-row, restart-safe."""
    cutoff = _now() - timedelta(seconds=timeout_s)
    task = db.scalar(select(M.Task).where(M.Task.status == "queued")
                     .order_by(M.Task.created_at.asc()).limit(1))
    if task is None:
        task = db.scalar(select(M.Task).where(
            M.Task.status.in_(["leased", "running"]), M.Task.leased_at < cutoff)
            .order_by(M.Task.leased_at.asc()).limit(1))
        if task is None:
            return None
    task.status = "leased"
    task.leased_by = worker_id
    task.leased_at = _now()
    task.attempts = (task.attempts or 0) + 1
    db.commit()
    db.refresh(task)
    return task


def set_task_status(db: Session, task: M.Task, status: str, **extra: Any) -> M.Task:
    prev = task.status
    task.status = status
    for k, v in extra.items():
        if hasattr(task, k):
            setattr(task, k, v)
    task.updated_at = _now()
    db.add(M.CaseEvent(case_id=task.case_id, actor="worker", event_type=f"task.{status}",
                       previous_state=prev, new_state=status,
                       payload_json=json.dumps({"task_id": task.id, **{k: str(v)[:200] for k, v in extra.items()}})))
    db.commit()
    db.refresh(task)
    return task


# ── runs / steps / citations / approvals ─────────────────────────────────────

def create_run(db: Session, *, case_id: str | None, task_id: str | None,
               intent: str | None, model: str = "harness", prompt_version: str = "v2") -> M.AgentRun:
    run = M.AgentRun(case_id=case_id, task_id=task_id, intent=intent, model=model, prompt_version=prompt_version)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def add_step(db: Session, *, run_id: str, task_id: str | None, sequence: int,
             action: str, tool: str | None = None, arguments: Any = None,
             result: Any = None, status: str = "ok", retry_count: int = 0,
             idempotency_key: str | None = None) -> M.RunStep:
    def _dump(v):
        if v is None:
            return None
        return v if isinstance(v, str) else json.dumps(v, default=str)
    step = M.RunStep(run_id=run_id, task_id=task_id, sequence=sequence, action=action,
                     tool=tool, arguments_json=_dump(arguments), result_json=_dump(result),
                     status=status, retry_count=retry_count,
                     idempotency_key=idempotency_key or f"{run_id}-{sequence}-{uuid.uuid4().hex[:6]}")
    db.add(step)
    db.commit()
    return step


def add_citations(db: Session, *, run_id: str, task_id: str | None, hits: list[dict]) -> None:
    for h in hits:
        db.add(M.Citation(run_id=run_id, task_id=task_id,
                          document_version_id=h.get("version_id", ""),
                          chunk_id=h.get("chunk_id", ""),
                          quoted_span=(h.get("text", "") or "")[:500],
                          score=h.get("score")))
    db.commit()


def request_approval(db: Session, *, task_id: str, requested_action: str, requester: str = "worker") -> M.Approval:
    ap = M.Approval(task_id=task_id, requested_action=requested_action, requester=requester)
    db.add(ap)
    db.commit()
    db.refresh(ap)
    return ap
