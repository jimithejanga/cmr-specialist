"""Mock CMR registry operator service: separate process, separate port.

Thin by design: it wraps the existing repository functions (no new query
logic) and exists for the operator + console - the AGENT never calls this
service; its path stays connector -> repository -> tables.

Auth: the operator signs in once (shared users table, read-only session
check) AND must be on the REGISTRY_OPERATORS allowlist (usernames, live env
read). Agent admin does not imply registry operator; the split is enforced
here, per request. Every write runs under feed.acting(username), so the
change feed attributes operator edits to their author.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from harness.api import auth as auth_mod
from harness.store.database import SessionLocal as AgentSessionLocal
from harness.store.database import init_db as init_agent_db
from registry import feed as _feed
from registry import repository as _repo
from registry.database import RegistrySession, init_registry_db
from registry.models import Certificate, Profile, Receipt, Token, Transfer, Vehicle

app = FastAPI(title="Mock CMR Registry")

_TABLES = ("profiles", "vehicles", "receipts", "certificates", "transfers", "tokens")
_KEY_COLUMN = {"profiles": "profile_id", "vehicles": "vehicle_id",
               "receipts": "rrr", "certificates": "cert_no",
               "transfers": "transfer_ref", "tokens": "token_id"}
_NATURAL_KEY = {"profiles": ("phone", "email", "profile_id"),
                "vehicles": ("plate",), "receipts": ("rrr",),
                "certificates": ("plate", "cert_no"), "transfers": ("transfer_ref",),
                "tokens": ("token_id",)}


def _operators() -> set[str]:
    return {u.strip() for u in os.getenv("REGISTRY_OPERATORS", "").split(",") if u.strip()}


def get_rdb():
    init_registry_db()
    db = RegistrySession()
    try:
        yield db
    finally:
        db.close()


def _operator(authorization: Optional[str] = Header(default=None)) -> str:
    """Validate the agent session, then the operator allowlist. Returns username."""
    init_agent_db()
    db = AgentSessionLocal()
    try:
        user = auth_mod.session_user(db, authorization)
    finally:
        db.close()
    if user is None:
        raise HTTPException(status_code=401, detail="operator login required")
    if user.username not in _operators():
        raise HTTPException(status_code=403, detail="not a registry operator")
    return user.username


def _iso(v):
    if isinstance(v, datetime):
        return v.isoformat()
    if hasattr(v, "isoformat"):
        try:
            return v.isoformat()
        except Exception:
            return str(v)
    return v


def _serialize(row) -> dict:
    data = {c.name: _iso(getattr(row, c.name)) for c in row.__table__.columns}
    return data


def _vehicle_view(s: Session, v: Vehicle) -> dict:
    d = _serialize(v)
    owner = s.get(Profile, v.owner_profile_id)
    d["owner_name"] = owner.full_name if owner else None
    d["owner_history"] = _repo.history_count(s, v.vehicle_id)
    return d


def _transfer_view(s: Session, t: Transfer) -> dict:
    d = _serialize(t)
    seller = s.get(Profile, t.seller_profile_id)
    buyer = s.get(Profile, t.buyer_profile_id)
    d["seller_name"] = seller.full_name if seller else None
    d["buyer_name"] = buyer.full_name if buyer else None
    return d


def _find_by_natural(s: Session, table: str, key: str):
    if table == "profiles":
        return (_repo.find_profile(s, phone=key, email=key, nin=key)
                or _repo.find_profile_by_id(s, key)
                or _repo.find_profile_by_name(s, key))
    if table == "vehicles":
        return _repo.find_vehicle(s, plate=key, chassis=key) or s.get(Vehicle, key)
    if table == "receipts":
        return _repo.find_receipt(s, key)
    if table == "certificates":
        v = _repo.find_vehicle(s, plate=key)
        if v is not None:
            return _repo.active_certificate(s, v.vehicle_id)
        return s.get(Certificate, key)
    if table == "transfers":
        return s.get(Transfer, key)
    if table == "tokens":
        return s.get(Token, key)
    return None


def _not_found(table: str, key: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"not-found: {table}/{key}")


@app.get("/health")
def health():
    return {"status": "ok", "service": "mock-cmr-registry"}


@app.get("/tables")
def list_tables(rdb: Session = Depends(get_rdb),
                username: str = Depends(_operator)):
    counts = {}
    for model, name in ((Profile, "profiles"), (Vehicle, "vehicles"),
                        (Receipt, "receipts"), (Certificate, "certificates"),
                        (Transfer, "transfers"), (Token, "tokens")):
        counts[name] = rdb.scalar(select(func.count()).select_from(model)) or 0
    return {"tables": counts}


@app.get("/tables/{table}")
def browse_table(table: str, search: str = "", limit: int = 50, offset: int = 0,
                 rdb: Session = Depends(get_rdb),
                 username: str = Depends(_operator)):
    if table not in _TABLES:
        raise HTTPException(status_code=400, detail=f"table must be one of {_TABLES}")
    model = {"profiles": Profile, "vehicles": Vehicle, "receipts": Receipt,
             "certificates": Certificate, "transfers": Transfer,
             "tokens": Token}[table]
    q = select(model).order_by(model.__table__.primary_key.columns.values()[0])
    if search:
        from sqlalchemy import or_

        like = f"%{search}%"
        cols = [c for c in model.__table__.columns
                if str(c.type).startswith(("VARCHAR", "TEXT", "STRING"))]
        if cols:
            q = q.where(or_(*[c.ilike(like) for c in cols]))
    rows = list(rdb.scalars(q.offset(offset).limit(min(limit, 200))).all())
    out = []
    for r in rows:
        if isinstance(r, Vehicle):
            out.append(_vehicle_view(rdb, r))
        elif isinstance(r, Transfer):
            out.append(_transfer_view(rdb, r))
        else:
            out.append(_serialize(r))
    return {"table": table, "count": len(out), "rows": out}


@app.get("/tables/{table}/{key}")
def read_row(table: str, key: str, rdb: Session = Depends(get_rdb),
             username: str = Depends(_operator)):
    if table not in _TABLES:
        raise HTTPException(status_code=400, detail=f"table must be one of {_TABLES}")
    row = _find_by_natural(rdb, table, key)
    if row is None:
        raise _not_found(table, key)
    if isinstance(row, Vehicle):
        return _vehicle_view(rdb, row)
    if isinstance(row, Transfer):
        return _transfer_view(rdb, row)
    return _serialize(row)


@app.get("/links/{table}/{key}")
def linked_rows(table: str, key: str, rdb: Session = Depends(get_rdb),
                username: str = Depends(_operator)):
    """Relations made visible: everything connected to one row."""
    if table == "profiles":
        p = _find_by_natural(rdb, "profiles", key)
        if p is None:
            raise _not_found(table, key)
        vehicles = list(rdb.scalars(select(Vehicle).where(
            Vehicle.owner_profile_id == p.profile_id)).all())
        transfers = list(rdb.scalars(select(Transfer).where(
            (Transfer.seller_profile_id == p.profile_id)
            | (Transfer.buyer_profile_id == p.profile_id))).all())
        tokens = _repo.tokens_for(rdb, p.profile_id)
        return {"profile": _serialize(p),
                "vehicles": [_vehicle_view(rdb, v) for v in vehicles],
                "transfers": [_transfer_view(rdb, t) for t in transfers],
                "tokens": [_serialize(t) for t in tokens]}
    if table == "vehicles":
        v = _find_by_natural(rdb, "vehicles", key)
        if v is None or not isinstance(v, Vehicle):
            raise _not_found(table, key)
        transfers = list(rdb.scalars(select(Transfer).where(
            Transfer.vehicle_id == v.vehicle_id)).all())
        certs = _repo.certificate_history(rdb, v.vehicle_id)
        return {"vehicle": _vehicle_view(rdb, v),
                "transfers": [_transfer_view(rdb, t) for t in transfers],
                "certificates": [_serialize(c) for c in certs]}
    if table == "receipts":
        r = _find_by_natural(rdb, "receipts", key)
        if r is None:
            raise _not_found(table, key)
        return {"receipt": _serialize(r),
                "note": "receipts are standalone by design (no purpose link)"}
    row = _find_by_natural(rdb, table, key)
    if row is None:
        raise _not_found(table, key)
    return {"row": _serialize(row)}


@app.get("/feed")
def read_feed(table: Optional[str] = None, actor: Optional[str] = None,
              row: Optional[str] = None, limit: int = 100,
              username: str = Depends(_operator)):
    from harness.tools import module as _mod

    return {"changes": _mod.feed_changes(table=table, actor=actor,
                                         row_key=row, limit=min(limit, 500))}


@app.post("/tables/{table}")
def insert_row(table: str, record: dict[str, Any],
               rdb: Session = Depends(get_rdb),
               username: str = Depends(_operator)):
    if table not in ("profiles", "vehicles", "receipts", "certificates"):
        raise HTTPException(status_code=400,
                            detail="writes allowed on profiles, vehicles, receipts, certificates")
    if not isinstance(record, dict) or not record:
        raise HTTPException(status_code=400, detail="non-empty JSON object required")
    keys = _NATURAL_KEY[table]
    key = next((str(record[k]) for k in keys if record.get(k)), None)
    if not key:
        raise HTTPException(status_code=400, detail=f"record needs one of {keys}")
    row = dict(record)
    row["synthetic"] = True
    from harness.tools import module as _mod

    try:
        with _feed.acting(username):
            _mod.insert_row(table, key, row)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"insert refused: {exc}")
    return {"ok": True, "table": table, "key": key, "by": username}


@app.patch("/tables/{table}/{key}")
def update_row(table: str, key: str, patch: dict[str, Any],
               rdb: Session = Depends(get_rdb),
               username: str = Depends(_operator)):
    """Guarded updates. Vehicles honor optimistic versions: pass the
    ``version`` you read; a mismatch is 409, never a silent overwrite."""
    if not isinstance(patch, dict) or not patch:
        raise HTTPException(status_code=400, detail="non-empty JSON object required")
    try:
        with _feed.acting(username):
            if table == "profiles":
                out = _repo.update_profile(rdb, key, **{k: patch[k] for k in
                                           ("full_name", "phone", "email", "nin")
                                           if k in patch})
                rdb.commit()
                return _serialize(out)
            if table == "vehicles":
                out = _repo.update_vehicle(rdb, key, owner=patch.get("owner"),
                                           chassis=patch.get("chassis"),
                                           expected_version=patch.get("version"))
                rdb.commit()
                return _vehicle_view(rdb, out)
            if table == "receipts":
                if "linked_account" in patch:
                    raise _repo.TerminalError(
                        "linked_account is set-once; void-and-relink only")
                out = _repo.set_receipt_status(rdb, key, patch.get("status"))
                rdb.commit()
                return _serialize(out)
            if table == "certificates":
                out = _repo.set_certificate_status(rdb, key, patch.get("status"))
                rdb.commit()
                return _serialize(out)
    except _repo.VersionConflict as exc:
        rdb.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    except _repo.TerminalError as exc:
        rdb.rollback()
        msg = str(exc)
        raise HTTPException(status_code=404 if "not-found" in msg else 400,
                            detail=msg)
    except IntegrityError:
        rdb.rollback()
        raise HTTPException(status_code=400, detail="duplicate unique value refused")
    raise HTTPException(status_code=400, detail=f"updates not supported on {table}")


@app.post("/reset")
def reseed(body: dict[str, Any], username: str = Depends(_operator)):
    """Reseed ceremony: pass {"confirm": "<registry db file name>"}.
    The feed records who did it; pre-world rows stay readable above the mark."""
    import os as _os

    from harness.tools import module as _mod

    want = _os.path.basename(
        _mod.registry_db_name() if hasattr(_mod, "registry_db_name")
        else os.getenv("REGISTRY_DATABASE_URL", "registry.db"))
    if not isinstance(body, dict) or body.get("confirm") != want:
        raise HTTPException(status_code=400,
                            detail=f"reseed refused: confirm with {{\"confirm\": \"{want}\"}}")
    with _feed.acting(username):
        _mod.reset_mock()
    return {"ok": True, "reseeded_by": username}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app,
                host=os.getenv("REGISTRY_HOST", "127.0.0.1"),
                port=int(os.getenv("REGISTRY_PORT", "8081")))
