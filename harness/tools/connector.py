"""Registry connector: the ONLY bridge between agent and registry database.

``RelationalDB`` exposes the exact method surface of the legacy dict backend
(``harness/tools/mockdb.py``) so the module's ``_dispatch`` calls it blind -
formulation in, rows out, identical envelopes. Translations live here and
nowhere else:

- money: tables store integer kobo, the API speaks whole naira (x100 on
  write, //100 on read - exact, never float).
- statuses: tables speak ``issued``/``active``, the API keeps the legacy
  words (``valid``/``approved``) so conformance shapes never drift.
- ownership: tables hold a profile FK, the API resolves the current name.
- history: transfer-row count + 1 (initial registration is provenance,
  not a transfer, and owns no row).
- NIMC verification stays a deterministic gateway stub (it is NOT registry
  data): same rules and fault switches as the legacy backend.
"""
from __future__ import annotations

import time
from datetime import date, datetime

from harness.tools.mockdb import TerminalError, TransientError
from registry import repository as repo
from registry.database import RegistrySession, init_registry_db
from registry.models import Certificate, Profile, Receipt, Token, Transfer, Vehicle

_NAIRA = 100

_CERT_STATE_OUT = {"issued": "valid", "pending": "pending",
                   "expired": "expired", "none": "none"}
_CERT_STATE_IN = {v: k for k, v in _CERT_STATE_OUT.items()}
_CERT_STATUS_OUT = {"active": "approved", "expired": "expired",
                    "revoked": "revoked"}
_CHANNEL_OUT = {"phone": "phone", "sms": "sms", "email": "email"}


def _channel_in(medium: str) -> str:
    return {"phone": "sms", "sms": "sms", "email": "email"}.get(
        str(medium or "").lower(), "sms")


def _parse_date(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(str(value)[:19], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


class RelationalDB:
    """SQL-backed twin of ``MockDB``: same methods, same envelopes."""

    def __init__(self) -> None:
        init_registry_db(seed_if_empty=True)
        self.faults: dict = {}
        self._once_cache: dict = {}

    # ── fault helper (identical semantics to the legacy backend) ──────────
    def _maybe_fault(self, op: str):
        spec = self.faults.get(op)
        if spec == "timeout":
            time.sleep(0.01)
            raise TransientError(f"{op}: injected timeout")
        if spec == "down":
            raise TransientError(f"{op}: injected outage")
        if spec == "notfound":
            raise TerminalError(f"{op}: injected not-found")

    def _session(self):
        return RegistrySession()

    # ── CHECKs ────────────────────────────────────────────────────────────
    def lookup_profile(self, *, phone=None, email=None):
        self._maybe_fault("lookup_profile")
        with self._session() as s:
            hit = repo.find_profile(s, phone=phone, email=email)
            if hit is None:
                raise TerminalError("not-found: profile")
            used = "phone" if phone and hit.phone == phone else "email"
            return {"exists": True, "profile_id": hit.profile_id,
                    "phone": hit.phone, "email": hit.email,
                    "username_type": used, "name": hit.full_name}

    def verify_nin(self, *, nin):
        self._maybe_fault("verify_nin")
        if self.faults.get("nimc") == "down":
            raise TransientError("NIMC gateway unreachable")
        if nin == "99999999999":
            return {"verdict": "suspended"}
        with self._session() as s:
            table_hit = repo.find_profile(s, nin=nin) is not None
        if table_hit or nin == "12345678901":
            return {"verdict": "match"}
        return {"verdict": "mismatch"}

    def nimc_health(self):
        if self.faults.get("nimc") == "down":
            return {"state": "down"}
        return {"state": "up"}

    def lookup_vehicle(self, *, plate=None, chassis=None):
        self._maybe_fault("lookup_vehicle")
        with self._session() as s:
            v = repo.find_vehicle(s, plate=plate, chassis=chassis)
            if v is None:
                raise TerminalError("not-found: vehicle")
            return {"vehicle_id": v.vehicle_id, "plate": v.plate,
                    "chassis": v.chassis, "owner": repo.owner_name(s, v),
                    "cert_state": _CERT_STATE_OUT.get(v.cert_state, v.cert_state),
                    "owner_history": repo.history_count(s, v.vehicle_id)}

    def lookup_owner(self, *, vehicle_id=None, plate=None):
        with self._session() as s:
            v = repo.find_vehicle(s, vehicle_id=vehicle_id, plate=plate)
            if v is None:
                raise TerminalError("not-found: vehicle")
            return {"owner": repo.owner_name(s, v),
                    "history_count": repo.history_count(s, v.vehicle_id)}

    def search_buyer(self, *, phone=None, email=None, nin=None, tin=None):
        self._maybe_fault("search_buyer")
        key = phone or email or nin or tin or ""
        with self._session() as s:
            hit = repo.find_profile(s, phone=key, email=key, nin=key)
            if hit is None:
                raise TerminalError("not-found: buyer profile")
            return {"match": True, "profile_id": hit.profile_id,
                    "name": hit.full_name}

    def lookup_receipt(self, *, rrr):
        self._maybe_fault("lookup_receipt")
        with self._session() as s:
            r = repo.find_receipt(s, rrr)
            if r is None:
                raise TerminalError("not-found: receipt")
            return {"rrr": r.rrr, "status": r.status,
                    "amount": (r.amount_kobo or 0) // _NAIRA,
                    "date": r.paid_at.date().isoformat() if r.paid_at else None,
                    "linked_account": r.linked_account}

    def lookup_certificate(self, *, plate):
        self._maybe_fault("lookup_certificate")
        with self._session() as s:
            v = repo.find_vehicle(s, plate=plate)
            if v is None:
                raise TerminalError("not-found: certificate")
            c = repo.active_certificate(s, v.vehicle_id)
            if c is None:
                raise TerminalError("not-found: certificate")
            return {"plate": plate,
                    "status": _CERT_STATUS_OUT.get(c.status, c.status),
                    "request_age_h": c.request_age_h,
                    "expiry": c.expires_at.date().isoformat() if c.expires_at else None,
                    "cert_no": c.cert_no}

    # ── WRITEs (fire once per idempotency key; same cache semantics) ──────
    def _once(self, key, fn):
        if key in self._once_cache:
            out = dict(self._once_cache[key])
            out["duplicate"] = True
            return out
        out = fn()
        out["duplicate"] = False
        self._once_cache[key] = dict(out)
        return out

    def resend_token(self, *, profile_id, medium, idempotency_key):
        def _fire():
            with self._session() as s:
                repo.log_token(s, profile_id=profile_id,
                               channel=_channel_in(medium))
                s.commit()
            return {"status": "sent", "medium": _CHANNEL_OUT.get(medium, medium)}
        return self._once(idempotency_key, _fire)

    def initiate_transfer(self, *, vehicle_id, buyer_profile_id, doc_ref,
                          idempotency_key):
        def _fire():
            with self._session() as s:
                row = repo.execute_transfer(s, vehicle_id=vehicle_id,
                                            buyer_profile_id=buyer_profile_id,
                                            doc_ref=doc_ref)
                s.commit()
                return {"status": "initiated", "transfer_ref": row.transfer_ref}
        return self._once(idempotency_key, _fire)

    def confirm_payment(self, *, request_ref, rrr, idempotency_key):
        def _fire():
            with self._session() as s:
                repo.confirm_receipt(s, rrr)
                s.commit()
            return {"status": "confirmed", "rrr": rrr}
        return self._once(idempotency_key, _fire)

    def link_payment(self, *, rrr, account, idempotency_key):
        def _fire():
            with self._session() as s:
                repo.link_receipt(s, rrr, account)
                s.commit()
            return {"status": "linked", "rrr": rrr, "account": account,
                    "link_ref": f"L-{rrr[-4:]}"}
        return self._once(idempotency_key, _fire)

    def resend_certificate(self, *, plate, email, idempotency_key):
        def _fire():
            with self._session() as s:
                v = repo.find_vehicle(s, plate=plate)
                if v is None or repo.active_certificate(s, v.vehicle_id) is None:
                    raise TerminalError("not-found: certificate")
                s.commit()
            return {"status": "resent", "plate": plate, "email": email}
        return self._once(idempotency_key, _fire)

    def renew_certificate(self, *, plate, state, rrr, idempotency_key):
        def _fire():
            with self._session() as s:
                v = repo.find_vehicle(s, plate=plate)
                if v is None:
                    raise TerminalError("not-found: vehicle")
                r = repo.find_receipt(s, rrr)
                if r is None or r.status != "paid":
                    raise TerminalError("renewal requires a paid RRR")
                # History kept: the old active row expires, a new active row
                # is issued. (The literal number below preserves the legacy
                # seed-data quirk so result shapes never drift.)
                row = repo.renew_certificate(
                    s, vehicle_id=v.vehicle_id, cert_no="CMR- renewed",
                    expires_at=datetime(2028, 1, 1))
                s.commit()
                return {"status": "renewed", "cert_no": row.cert_no,
                        "expiry": "2028-01-01"}
        return self._once(idempotency_key, _fire)

    def correct_certificate(self, *, plate, field, old_value, new_value, reason,
                            request_age_days, idempotency_key):
        def _fire():
            if request_age_days is not None and request_age_days > 30:
                raise TerminalError("outside 30-day correction window; refer to HQ")
            if field == "color" and str(new_value).lower() == "custom":
                raise TerminalError("Custom colour not allowed on the portal")
            with self._session() as s:
                n = repo.next_counter(s, "CORR")
                s.commit()
            return {"status": "corrected", "plate": plate, "field": field,
                    "ticket": f"CORR-{n:04d}"}
        return self._once(idempotency_key, _fire)
