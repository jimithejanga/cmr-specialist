"""Observability admin API (separate admin site, same backend).

Read-mostly: mockDB explorer, queue monitor, recent-case listing.
The ONE write (mockDB insert) is admin-gated, synthetic-tagged, and can only
ever touch the mock adapter - it cannot reach a real backend.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from harness.api import auth as auth_mod
from harness.store import models as M
from harness.store.database import SessionLocal, init_db

router = APIRouter(prefix="/admin", tags=["Admin"])

_MOCK_TABLES = ("profiles", "vehicles", "receipts", "certificates")


def get_db():
    init_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _heartbeat():
    from harness.api.main import WORKER_HEARTBEAT

    return WORKER_HEARTBEAT.get("last_seen") or "unknown"


def _db():
    from harness.tools import module as _mod

    return _mod._db


def _admin(db: Session, authorization: Optional[str], x_api_key: Optional[str]) -> M.User:
    return auth_mod.require_admin(db, authorization=authorization, x_api_key=x_api_key)


@router.get("/mockdb")
def mockdb_dump(authorization: Optional[str] = Header(default=None),
                x_api_key: Optional[str] = Header(default=None),
                db: Session = Depends(get_db)):
    _admin(db, authorization, x_api_key)
    m = _db()
    return {"process": "web", "note": "web-process view; worker holds its own copy",
            "tables": {t: getattr(m, t) for t in _MOCK_TABLES},
            "transfers": m.transfers, "tokens_sent": m.tokens_sent,
            "faults": m.faults}


@router.post("/mockdb/reset")
def mockdb_reset(authorization: Optional[str] = Header(default=None),
                 x_api_key: Optional[str] = Header(default=None),
                 db: Session = Depends(get_db)):
    _admin(db, authorization, x_api_key)
    from harness.tools import module as _mod

    _mod._db = _mod.MockDB.seeded()
    return {"ok": True, "note": "web-process mockDB reseeded"}


@router.post("/mockdb/{table}")
def mockdb_insert(table: str, record: dict[str, Any],
                  authorization: Optional[str] = Header(default=None),
                  x_api_key: Optional[str] = Header(default=None),
                  db: Session = Depends(get_db)):
    admin = _admin(db, authorization, x_api_key)
    if table not in _MOCK_TABLES:
        raise HTTPException(status_code=400, detail=f"table must be one of {_MOCK_TABLES}")
    if not isinstance(record, dict) or not record:
        raise HTTPException(status_code=400, detail="non-empty JSON object required")
    keys = {"profiles": ("phone", "email"), "vehicles": ("plate",),
            "receipts": ("rrr",), "certificates": ("plate",)}[table]
    key = next((str(record[k]) for k in keys if record.get(k)), None)
    if not key:
        raise HTTPException(status_code=400, detail=f"record needs one of {keys}")
    row = dict(record)
    row["synthetic"] = True
    row["inserted_by"] = admin.username
    row["inserted_at"] = datetime.now(timezone.utc).isoformat()
    getattr(_db(), table)[key] = row
    return {"ok": True, "table": table, "key": key, "synthetic": True}


@router.get("/queue")
def queue_stats(authorization: Optional[str] = Header(default=None),
                x_api_key: Optional[str] = Header(default=None),
                db: Session = Depends(get_db)):
    _admin(db, authorization, x_api_key)
    by_status = dict(db.execute(
        select(M.Task.status, func.count()).group_by(M.Task.status)).all())
    oldest = db.scalar(select(func.min(M.Task.created_at)).where(M.Task.status == "queued"))
    age = None
    if oldest is not None:
        if getattr(oldest, "tzinfo", None) is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        age = int((datetime.now(timezone.utc) - oldest).total_seconds())
    recent = db.scalars(select(M.Task).order_by(M.Task.created_at.desc()).limit(10)).all()
    return {"by_status": by_status, "oldest_queued_age_s": age,
            "worker_heartbeat": _heartbeat(),
            "recent": [{"id": t.id[:8], "type": t.task_type, "status": t.status,
                        "attempts": t.attempts} for t in recent]}


@router.get("/cases/recent")
def recent_cases(limit: int = 20,
                 authorization: Optional[str] = Header(default=None),
                 x_api_key: Optional[str] = Header(default=None),
                 db: Session = Depends(get_db)):
    _admin(db, authorization, x_api_key)
    cases = db.scalars(select(M.Case).order_by(M.Case.created_at.desc()).limit(limit)).all()
    out = []
    for c in cases:
        tasks = db.scalars(select(M.Task).where(M.Task.case_id == c.id)).all()
        out.append({"id": c.id, "title": c.title,
                    "tasks": [{"id": t.id, "type": t.task_type, "status": t.status}
                              for t in tasks]})
    return {"cases": out}
