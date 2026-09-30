"""Tool module: formulator + firer (PDF v3 §6).

Sole executor against the database. Five stages per call:
validate → authorize → fire → respond → audit.
Owns all credentials; harness callers authenticate with a service token.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
import uuid

from harness.tools import formulations as F
from harness.tools.mockdb import MockDB, TerminalError, TransientError

# Module-owned database handle. Nothing outside this module may import it.
_db = MockDB.seeded()


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


# formulation id -> mockdb method + arg mapping
def _dispatch(db: MockDB, fid: str, a: dict, idem: str | None):
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
    """Test/chaos helper: reseed mock + set fault switches."""
    global _db
    _db = MockDB.seeded()
    _db.faults = dict(faults)
    clear_overlay()


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
