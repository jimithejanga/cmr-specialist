"""Tool module: formulator + firer (PDF v3 §6).

Sole executor against the database. Five stages per call:
validate → authorize → fire → respond → audit.
Owns all credentials; harness callers authenticate with a service token.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
import uuid

from harness.tools import formulations as F
from harness.tools.mockdb import MockDB, TerminalError, TransientError
from registry import feed as _feed

# Module-owned database handle. Nothing outside this module may import it.
# Two backends, one contract: the legacy dict backend (default while the
# relational twin proves itself) and the relational registry database.
# MOCKDB_BACKEND=relational flips the switch; nothing else moves.
_BACKEND = os.getenv("MOCKDB_BACKEND", None)
if _BACKEND is None:
    from configs.settings import settings as _settings

    _BACKEND = _settings.MOCKDB_BACKEND


def _build_backend(name: str):
    if name == "relational":
        from harness.tools.connector import RelationalDB

        return RelationalDB()
    return MockDB.seeded()


_db = _build_backend(_BACKEND)


def select_backend(name: str):
    """Switch backends in-process (tests/conformance). Returns the handle."""
    global _db, _BACKEND
    _BACKEND = name
    _db = _build_backend(name)
    return _db


def backend_name() -> str:
    return "relational" if not isinstance(_db, MockDB) else "legacy"


def simulate_restart():
    """Drop in-process memory without touching durable state: legacy keeps
    the overlay file (reapplied lazily, exactly like a real restart);
    relational reconnects to the same database file."""
    global _db
    _db = _build_backend(_BACKEND)
    return _db


def _service_token() -> str:
    from configs.settings import settings

    return settings.TOOL_MODULE_TOKEN


def _mask(value) -> str:
    """PII masking: long digit strings keep last-4 only."""
    s = value if isinstance(value, str) else json.dumps(value, default=str)
    return re.sub(r"\b(\d{6,})(\d{4})\b", lambda m: "*" * (len(m.group(1))) + m.group(2), s)


def _masked_args(arguments: dict) -> str:
    return json.dumps({k: _mask(v) for k, v in (arguments or {}).items()}, default=str)[:2000]


def _check_token(token: str | None) -> bool:
    return bool(token) and hmac.compare_digest(str(token), _service_token())


# formulation id -> backend method + arg mapping (both backends share it)
def _dispatch(db, fid: str, a: dict, idem: str | None):
    if fid == "CHECK.profile.lookup":
        return db.lookup_profile(phone=a.get("phone"), email=a.get("email"))
    if fid == "CHECK.nin.verify":
        return db.verify_nin(nin=a["nin"])
    if fid == "CHECK.nimc.health":
        return db.nimc_health()
    if fid == "CHECK.vehicle.lookup":
        return db.lookup_vehicle(plate=a.get("plate"), chassis=a.get("chassis"))
    if fid == "CHECK.owner.lookup":
        return db.lookup_owner(vehicle_id=a.get("vehicle_id"), plate=a.get("plate"))
    if fid == "CHECK.buyer.search":
        return db.search_buyer(phone=a.get("phone"), email=a.get("email"),
                               nin=a.get("nin"), tin=a.get("tin"))
    if fid == "CHECK.receipt.lookup":
        return db.lookup_receipt(rrr=a["rrr"])
    if fid == "CHECK.certificate.lookup":
        return db.lookup_certificate(plate=a["plate"])
    if fid == "WRITE.token.resend":
        return db.resend_token(profile_id=a["profile_id"], medium=a["medium"],
                               idempotency_key=idem)
    if fid == "WRITE.transfer.initiate":
        return db.initiate_transfer(vehicle_id=a["vehicle_id"],
                                    buyer_profile_id=a["buyer_profile_id"],
                                    doc_ref=a["doc_ref"], idempotency_key=idem)
    if fid == "WRITE.payment.confirm":
        return db.confirm_payment(request_ref=a["request_ref"], rrr=a["rrr"],
                                  idempotency_key=idem)
    if fid == "WRITE.payment.link":
        return db.link_payment(rrr=a["rrr"], account=a["account"], idempotency_key=idem)
    if fid == "WRITE.certificate.resend":
        return db.resend_certificate(plate=a["plate"], email=a["email"],
                                     idempotency_key=idem)
    if fid == "WRITE.certificate.renew":
        return db.renew_certificate(plate=a["plate"], state=a["state"], rrr=a["rrr"],
                                    idempotency_key=idem)
    if fid == "WRITE.certificate.correct":
        return db.correct_certificate(
            plate=a["plate"], field=a["field"], old_value=a.get("old_value"),
            new_value=a["new_value"], reason=a["reason"],
            request_age_days=a.get("request_age_days"), idempotency_key=idem)
    raise TerminalError(f"no adapter for {fid}")


def _validate_schema(form: F.Formulation, arguments: dict) -> str | None:
    """Returns error string or None. Stage 1."""
    for name, spec in form.inputs.items():
        v = (arguments or {}).get(name)
        if spec.get("required") and (v is None or v == ""):
            return f"missing required field: {name}"
        if v is not None and spec.get("pattern") and not re.match(spec["pattern"], str(v)):
            return f"field {name} fails pattern {spec['pattern']}"
    return None


def fire(*, formulation_id: str, arguments: dict | None = None,
         service_token: str | None = None, run_id: str | None = None,
         case_id: str | None = None, approval_ref: str | None = None,
         evidence_refs: list | None = None, idempotency_key: str | None = None,
         audit_db=None) -> dict:
    """Fire one formulated call. Always returns a typed envelope; never raises
    caller-visible DB errors. Audit row is written before the response returns."""
    started = time.perf_counter()
    arguments = arguments or {}
    evidence_refs = evidence_refs or []
    if isinstance(_db, MockDB):
        _apply_overlay(_db)
    envelope: dict = {"status": "failed", "error_ref": None, "data": None,
                      "evidence_ref": None, "audit_id": None}
    audit_error: str | None = None
    form = F.CATALOG.get(formulation_id)  # bound before _audit closure uses it

    def _audit(result_summary: str, error: str | None):
        if audit_db is None:
            return None
        from harness.store import models as M
        row = M.ToolAudit(
            formulation_id=formulation_id, verb=form.verb if form else "?",
            run_id=run_id, case_id=case_id, arguments_masked=_masked_args(arguments),
            result_summary=result_summary[:2000], evidence_refs=json.dumps(evidence_refs),
            approval_ref=approval_ref,
            latency_ms=int((time.perf_counter() - started) * 1000), error=error)
        audit_db.add(row)
        audit_db.commit()
        return row.id

    # ── auth ──────────────────────────────────────────────────────────────
    if not _check_token(service_token):
        envelope["error_ref"] = "unauthorized: bad service token"
        envelope["audit_id"] = _audit("rejected: unauthorized", envelope["error_ref"])
        return envelope

    # ── stage 0: catalog membership ───────────────────────────────────────
    if form is None:
        envelope["error_ref"] = f"not formulated: {formulation_id}"
        envelope["audit_id"] = _audit("rejected: unknown formulation", envelope["error_ref"])
        return envelope

    # ── stage 1: validate ─────────────────────────────────────────────────
    err = _validate_schema(form, arguments)
    if err:
        envelope["error_ref"] = err
        envelope["audit_id"] = _audit("rejected: schema", err)
        return envelope

    # ── stage 2: authorize ────────────────────────────────────────────────
    if form.verb == "WRITE":
        if not approval_ref:
            envelope["error_ref"] = "write parked: approval required"
            envelope["audit_id"] = _audit("parked: no approval", envelope["error_ref"])
            envelope["status"] = "parked"
            return envelope
        if not idempotency_key:
            envelope["error_ref"] = "write refused: idempotency key required"
            envelope["audit_id"] = _audit("refused: no idempotency key", envelope["error_ref"])
            return envelope
        if form.evidence and not any(form.evidence in str(e) for e in evidence_refs):
            envelope["error_ref"] = f"write refused: missing evidence {form.evidence}"
            envelope["audit_id"] = _audit("refused: no evidence", envelope["error_ref"])
            return envelope

    # ── stage 2b: durable idempotency (Phase-3 rule) ────────────────────
    # Memory `_once` is a cache; this table is the truth. A key fired before
    # a restart returns the stored outcome instead of re-firing.
    if idempotency_key and audit_db is not None:
        dup = _idem_lookup(audit_db, idempotency_key)
        if dup is not None:
            data = dict(dup)
            data["duplicate"] = True
            envelope["status"] = "ok"
            envelope["data"] = data
            envelope["audit_id"] = _audit("duplicate: served stored outcome", None)
            return envelope

    # ── stage 3: fire (reads retry on transient; writes never retry) ─────
    attempts = 1 + (form.retries if form.verb == "CHECK" else 0)
    last_err: str | None = None
    for _ in range(attempts):
        try:
            with _feed.acting(f"agent:{formulation_id}"):
                data = _dispatch(_db, formulation_id, arguments, idempotency_key)
            envelope["status"] = "ok"
            envelope["data"] = data
            ref = f"{formulation_id}:{hashlib.sha256(json.dumps(data, default=str).encode()).hexdigest()[:8]}"
            envelope["evidence_ref"] = ref
            if idempotency_key and audit_db is not None:
                _idem_store(audit_db, idempotency_key, formulation_id, data)
            envelope["audit_id"] = _audit(json.dumps(data, default=str)[:2000], None)
            return envelope
        except TransientError as exc:
            last_err = f"transient: {exc}"
            continue
        except TerminalError as exc:
            last_err = f"terminal: {exc}"
            break
        except Exception as exc:  # never leak raw internals
            last_err = f"terminal: internal error ({type(exc).__name__})"
            break
    envelope["error_ref"] = last_err or "terminal: unknown failure"
    envelope["audit_id"] = _audit("failed", envelope["error_ref"])
    return envelope


def _idem_lookup(audit_db, key: str) -> dict | None:
    """Stored outcome for a previously fired key, if any."""
    from harness.store import models as M

    row = audit_db.get(M.ToolIdempotency, key)
    if not row:
        return None
    try:
        return json.loads(row.result_json)
    except Exception:
        return None


def _idem_store(audit_db, key: str, formulation_id: str, data: dict) -> None:
    """Persist a fired outcome. Lost races re-read as duplicates."""
    from sqlalchemy.exc import IntegrityError

    from harness.store import models as M

    try:
        audit_db.add(M.ToolIdempotency(
            idempotency_key=key, formulation_id=formulation_id,
            result_json=json.dumps(data, default=str)[:4000]))
        audit_db.commit()
    except IntegrityError:
        audit_db.rollback()


def reset_mock(**faults) -> None:
    """Test/chaos helper: reseed backend + set fault switches."""
    global _db
    if isinstance(_db, MockDB):
        _db = MockDB.seeded()
        _db.faults = dict(faults)
        clear_overlay()
        return
    from registry import repository as _repo
    from registry import seed as _seed
    from registry.database import RegistrySession

    with RegistrySession() as s:
        _repo.clear_all(s)
        s.commit()
    with RegistrySession() as s:
        with _feed.acting("system:seed"):
            _seed.seed_all(s)
        s.commit()
    with RegistrySession() as s:
        with _feed.acting("system:reset"):
            _feed.record(s, table="registry", row_key="all", action="reseed",
                         after={"backend": "relational"})
        s.commit()
    _db.faults = dict(faults)
    _db._once_cache = {}


# ── backend-agnostic inspection + writes (tests, conformance, admin) ─────
def dump_state() -> dict:
    """Whole backend in legacy shapes: the admin explorer and the exam
    paper never learn which backend is underneath."""
    if isinstance(_db, MockDB):
        return {"profiles": dict(_db.profiles), "vehicles": dict(_db.vehicles),
                "receipts": dict(_db.receipts),
                "certificates": dict(_db.certificates),
                "transfers": dict(_db.transfers),
                "tokens_sent": list(_db.tokens_sent),
                "faults": dict(_db.faults)}
    from registry import repository as _repo
    from registry.database import RegistrySession
    from registry.models import Certificate, Profile, Receipt, Token, Transfer, Vehicle
    from sqlalchemy import select

    with RegistrySession() as s:
        profiles = {}
        for p in s.scalars(select(Profile)).all():
            profiles[p.phone or p.email or p.profile_id] = {
                "profile_id": p.profile_id, "phone": p.phone, "email": p.email,
                "name": p.full_name, "nin": p.nin, "synthetic": p.is_synthetic}
        vehicles = {}
        for v in s.scalars(select(Vehicle)).all():
            owner = s.get(Profile, v.owner_profile_id)
            vehicles[v.plate] = {
                "vehicle_id": v.vehicle_id, "plate": v.plate,
                "chassis": v.chassis, "owner": owner.full_name if owner else None,
                "cert_state": {"issued": "valid"}.get(v.cert_state, v.cert_state),
                "owner_history": _repo.history_count(s, v.vehicle_id),
                "synthetic": v.is_synthetic}
        receipts = {}
        for r in s.scalars(select(Receipt)).all():
            receipts[r.rrr] = {
                "rrr": r.rrr, "status": r.status,
                "amount": (r.amount_kobo or 0) // 100,
                "date": r.paid_at.date().isoformat() if r.paid_at else None,
                "linked_account": r.linked_account, "synthetic": r.is_synthetic}
        certificates = {}
        for c in s.scalars(select(Certificate).where(
                Certificate.status == "active")).all():
            v = s.get(Vehicle, c.vehicle_id)
            if v is None:
                continue
            certificates[v.plate] = {
                "plate": v.plate, "status": "approved",
                "request_age_h": c.request_age_h,
                "expiry": c.expires_at.date().isoformat() if c.expires_at else None,
                "cert_no": c.cert_no, "synthetic": c.is_synthetic}
        transfers = {t.transfer_ref: {"vehicle_id": t.vehicle_id,
                                      "buyer": t.buyer_profile_id,
                                      "doc_ref": t.doc_ref}
                     for t in s.scalars(select(Transfer)).all()}
        tokens = [{"profile_id": t.profile_id,
                   "medium": {"sms": "phone"}.get(t.channel, t.channel)}
                  for t in s.scalars(select(Token)).all()]
        return {"profiles": profiles, "vehicles": vehicles,
                "receipts": receipts, "certificates": certificates,
                "transfers": transfers, "tokens_sent": tokens,
                "faults": dict(_db.faults)}


def token_log() -> list:
    return dump_state()["tokens_sent"]


def feed_changes(*, table=None, actor=None, row_key=None, limit=100) -> list:
    """Newest-first change feed (relational backend; legacy has no feed)."""
    if isinstance(_db, MockDB):
        return []
    import json as _json

    from registry import feed as _feed_mod
    from registry.database import RegistrySession

    def _parse(v):
        try:
            return _json.loads(v) if v else None
        except Exception:
            return v

    with RegistrySession() as s:
        rows = _feed_mod.list_changes(s, table=table, actor=actor,
                                      row_key=row_key, limit=limit)
        return [{"id": r.id, "at": r.at.isoformat() if r.at else None,
                 "actor": r.actor, "action": r.action, "table": r.table_name,
                 "row": r.row_key, "before": _parse(r.before_json),
                 "after": _parse(r.after_json)} for r in rows]


def receipt_account(rrr: str):
    row = dump_state()["receipts"].get(rrr) or {}
    return row.get("linked_account")


def vehicle_owner_id(plate: str):
    """Current owner's profile_id (post-transfer both backends agree)."""
    if isinstance(_db, MockDB):
        return (_db.vehicles.get(plate) or {}).get("owner")
    from registry import repository as _repo
    from registry.database import RegistrySession

    with RegistrySession() as s:
        v = _repo.find_vehicle(s, plate=plate)
        return v.owner_profile_id if v else None


def _resolve_owner(session, owner_value: str | None) -> str | None:
    """Legacy seeds/admin rows name owners by id OR by name; the tables need
    a profile FK. Resolve either, else create a synthetic stub profile."""
    from registry import repository as _repo

    if not owner_value:
        return None
    hit = (_repo.find_profile_by_id(session, owner_value)
           or _repo.find_profile_by_name(session, owner_value))
    if hit is not None:
        return hit.profile_id
    n = session.query(_repo.Profile).count() + 1
    stub = _repo.create_profile(session, profile_id=f"prof-{n:03d}",
                                full_name=owner_value, synthetic=True)
    return stub.profile_id


def insert_row(table: str, key: str, row: dict) -> None:
    """Admin/test upsert of one synthetic row (legacy: dict + overlay file;
    relational: straight into the tables, synthetic-flagged)."""
    if isinstance(_db, MockDB):
        row = dict(row)
        if table == "vehicles":
            row.setdefault("owner_history", 1)
            row.setdefault("cert_state", "valid")
        getattr(_db, table)[key] = row
        save_overlay_row(table, key, row)
        return
    from datetime import datetime

    from harness.tools.connector import _CERT_STATE_IN
    from registry import repository as _repo
    from registry.database import RegistrySession

    with RegistrySession() as s:
        if table == "profiles":
            pid = row.get("profile_id") or f"prof-{s.query(_repo.Profile).count() + 1:03d}"
            hit = _repo.find_profile_by_id(s, pid)
            data = dict(name=row.get("name") or row.get("full_name"),
                        phone=row.get("phone"), email=row.get("email"),
                        nin=row.get("nin"))
            if hit is None:
                _repo.create_profile(s, profile_id=pid, full_name=data["name"],
                                     phone=data["phone"], email=data["email"],
                                     nin=data["nin"], synthetic=True)
            else:
                for k, col in (("name", "full_name"), ("phone", "phone"),
                               ("email", "email"), ("nin", "nin")):
                    if data[k] is not None:
                        setattr(hit, col, data[k])
                hit.is_synthetic = True
        elif table == "vehicles":
            owner_id = _resolve_owner(s, row.get("owner"))
            if owner_id is None:
                from harness.tools.mockdb import TerminalError as _TE

                raise _TE("vehicle insert needs an owner (profile id or name)")
            vid = row.get("vehicle_id") or f"veh-{s.query(_repo.Vehicle).count() + 1:03d}"
            hit = _repo.find_vehicle(s, plate=key)
            state = _CERT_STATE_IN.get(row.get("cert_state"), "none")
            if hit is None:
                _repo.create_vehicle(s, vehicle_id=vid, plate=key,
                                     chassis=row.get("chassis"),
                                     owner_profile_id=owner_id,
                                     cert_state=state, synthetic=True)
            else:
                hit.owner_profile_id = owner_id
                if row.get("chassis"):
                    hit.chassis = row["chassis"]
                hit.is_synthetic = True
        elif table == "receipts":
            paid = None
            if row.get("date"):
                try:
                    paid = datetime.fromisoformat(str(row["date"])[:10])
                except ValueError:
                    paid = None
            hit = _repo.find_receipt(s, key)
            if hit is None:
                _repo.create_receipt(s, rrr=key,
                                     status=row.get("status", "unpaid"),
                                     amount_kobo=int(row.get("amount", 0)) * 100,
                                     paid_at=paid, synthetic=True)
                if row.get("linked_account"):
                    _repo.link_receipt(s, key, row["linked_account"])
            else:
                hit.status = row.get("status", hit.status)
                hit.is_synthetic = True
        elif table == "certificates":
            v = _repo.find_vehicle(s, plate=key)
            if v is None:
                from harness.tools.mockdb import TerminalError as _TE

                raise _TE("not-found: vehicle for certificate")
            status = {"approved": "active", "active": "active"}.get(
                row.get("status"), "active")
            old = _repo.active_certificate(s, v.vehicle_id)
            if status == "active" and old is not None:
                old.status = "expired"
            cno = row.get("cert_no") or f"CMR-{(s.query(_repo.Certificate).count() + 1):04d}"
            exp = None
            if row.get("expiry"):
                try:
                    exp = datetime.fromisoformat(str(row["expiry"])[:10])
                except ValueError:
                    exp = None
            _repo.renew_certificate(s, vehicle_id=v.vehicle_id, cert_no=cno,
                                    expires_at=exp,
                                    request_age_h=row.get("request_age_h"))
            if status != "active":
                new = s.get(_repo.Certificate, cno)
                if new is not None:
                    new.status = status
        else:
            from harness.tools.mockdb import TerminalError as _TE

            raise _TE(f"unknown table: {table}")
        s.commit()


def overlay_path() -> str:
    import os

    return os.getenv("MOCKDB_OVERLAY", "var/mockdb_overlay.json")


def _apply_overlay(db: MockDB) -> None:
    """Apply admin-inserted synthetic rows so every process sees them.

    Additive upserts only: overlay rows merge into the live copy on each
    fire, so web inserts are visible to the worker without restarts, while
    in-process writes (transfers, tokens) are never clobbered."""
    import json as _json
    import os as _os

    path = overlay_path()
    if not _os.path.exists(path):
        return
    try:
        with open(path) as fh:
            overlay = _json.load(fh)
    except Exception:
        return
    if not isinstance(overlay, dict):
        return
    for table in ("profiles", "vehicles", "receipts", "certificates"):
        rows = overlay.get(table)
        if isinstance(rows, dict):
            getattr(db, table).update(rows)


def save_overlay_row(table: str, key: str, row: dict) -> None:
    """Persist one admin-inserted row to the shared overlay file."""
    import json as _json
    import os as _os

    path = overlay_path()
    overlay: dict = {}
    if _os.path.exists(path):
        try:
            with open(path) as fh:
                overlay = _json.load(fh) or {}
        except Exception:
            overlay = {}
    overlay.setdefault(table, {})[key] = row
    _os.makedirs(_os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        _json.dump(overlay, fh, indent=1)


def clear_overlay() -> None:
    import os as _os

    path = overlay_path()
    if _os.path.exists(path):
        _os.remove(path)
