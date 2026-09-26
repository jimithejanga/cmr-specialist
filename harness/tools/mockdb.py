"""Mock CMR database (Phase 2 v3 §9).

Deterministic seed data behind a repository interface, with error injection
(timeouts, 404s, downtime flags) so retry, fallback, and escalation paths are
testable. The REAL backend later must satisfy the same interface + conformance
suite — only this file (and its real twin) ever touches data.
"""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field


class TransientError(Exception):
    """Retryable: timeout, 5xx, rate-limit."""


class TerminalError(Exception):
    """Not retryable: not-found, validation, forbidden."""


@dataclass
class MockDB:
    """In-memory stand-in for the CMR main database."""

    profiles: dict = field(default_factory=dict)
    vehicles: dict = field(default_factory=dict)
    receipts: dict = field(default_factory=dict)
    certificates: dict = field(default_factory=dict)
    transfers: dict = field(default_factory=dict)
    tokens_sent: list = field(default_factory=list)
    # error injection switches (tests / chaos drills)
    faults: dict = field(default_factory=dict)
    # idempotency store: key -> result (writes fire once)
    fired: dict = field(default_factory=dict)

    # ── seeding ──────────────────────────────────────────────────────────
    @classmethod
    def seeded(cls) -> "MockDB":
        db = cls()
        db.profiles = {
            "08012345678": {"profile_id": "prof-001", "phone": "08012345678",
                            "email": "ada@example.com", "username_type": "phone",
                            "name": "Ada Obi"},
            "ada@example.com": {"profile_id": "prof-001", "phone": "08012345678",
                                "email": "ada@example.com", "username_type": "email",
                                "name": "Ada Obi"},
        }
        db.vehicles = {
            "ABC123XY": {"vehicle_id": "veh-001", "plate": "ABC123XY",
                         "chassis": "CHS987654321", "owner": "Ada Obi",
                         "cert_state": "valid", "owner_history": 1},
        }
        db.receipts = {
            "123456789012": {"rrr": "123456789012", "status": "paid",
                             "amount": 5000, "date": "2026-09-10",
                             "linked_account": "acct-X"},
        }
        db.certificates = {
            "ABC123XY": {"plate": "ABC123XY", "status": "approved",
                         "request_age_h": 30, "expiry": "2027-01-01",
                         "cert_no": "CMR-0001"},
        }
        return db

    # ── fault helper ─────────────────────────────────────────────────────
    def _maybe_fault(self, op: str):
        spec = self.faults.get(op)
        if spec == "timeout":
            time.sleep(0.01)
            raise TransientError(f"{op}: injected timeout")
        if spec == "down":
            raise TransientError(f"{op}: injected outage")
        if spec == "notfound":
            raise TerminalError(f"{op}: injected not-found")

    # ── CHECKs (read-only) ───────────────────────────────────────────────
    def lookup_profile(self, *, phone=None, email=None):
        self._maybe_fault("lookup_profile")
        hit = self.profiles.get(phone or "") or self.profiles.get(email or "")
        if not hit:
            raise TerminalError("not-found: profile")
        return {"exists": True, **hit}

    def verify_nin(self, *, nin):
        self._maybe_fault("verify_nin")
        if self.faults.get("nimc") == "down":
            raise TransientError("NIMC gateway unreachable")
        if nin == "99999999999":
            return {"verdict": "suspended"}
        if nin == "12345678901":
            return {"verdict": "match"}
        return {"verdict": "mismatch"}

    def nimc_health(self):
        if self.faults.get("nimc") == "down":
            return {"state": "down"}
        return {"state": "up"}

    def lookup_vehicle(self, *, plate=None, chassis=None):
        self._maybe_fault("lookup_vehicle")
        for v in self.vehicles.values():
            if (plate and v["plate"] == plate) or (chassis and v["chassis"] == chassis):
                return dict(v)
        raise TerminalError("not-found: vehicle")

    def lookup_owner(self, *, vehicle_id=None, plate=None):
        v = self.lookup_vehicle(plate=plate) if plate else None
        if vehicle_id:
            v = next((x for x in self.vehicles.values() if x["vehicle_id"] == vehicle_id), None)
        if not v:
            raise TerminalError("not-found: vehicle")
        return {"owner": v["owner"], "history_count": v["owner_history"]}

    def search_buyer(self, *, phone=None, email=None, nin=None, tin=None):
        self._maybe_fault("search_buyer")
        key = phone or email or nin or tin or ""
        hit = self.profiles.get(key)
        if not hit:
            raise TerminalError("not-found: buyer profile")
        return {"match": True, "profile_id": hit["profile_id"], "name": hit["name"]}

    def lookup_receipt(self, *, rrr):
        self._maybe_fault("lookup_receipt")
        r = self.receipts.get(rrr)
        if not r:
            raise TerminalError("not-found: receipt")
        return dict(r)

    def lookup_certificate(self, *, plate):
        self._maybe_fault("lookup_certificate")
        c = self.certificates.get(plate)
        if not c:
            raise TerminalError("not-found: certificate")
        return dict(c)

    # ── WRITEs (fire once per idempotency key) ────────────────────────────
    def _once(self, key, fn):
        if key in self.fired:
            out = dict(self.fired[key])
            out["duplicate"] = True
            return out
        out = fn()
        out["duplicate"] = False
        self.fired[key] = dict(out)
        return out

    def resend_token(self, *, profile_id, medium, idempotency_key):
        def _fire():
            self.tokens_sent.append({"profile_id": profile_id, "medium": medium})
            return {"status": "sent", "medium": medium}
        return self._once(idempotency_key, _fire)

    def initiate_transfer(self, *, vehicle_id, buyer_profile_id, doc_ref, idempotency_key):
        def _fire():
            ref = f"TRF-{len(self.transfers) + 1:04d}"
            self.transfers[ref] = {"vehicle_id": vehicle_id, "buyer": buyer_profile_id,
                                   "doc_ref": doc_ref}
            return {"status": "initiated", "transfer_ref": ref}
        return self._once(idempotency_key, _fire)

    def confirm_payment(self, *, request_ref, rrr, idempotency_key):
        def _fire():
            r = self.receipts.get(rrr)
            if not r or r["status"] != "paid":
                raise TerminalError("no paid receipt to confirm")
            return {"status": "confirmed", "rrr": rrr}
        return self._once(idempotency_key, _fire)

    def link_payment(self, *, rrr, account, idempotency_key):
        def _fire():
            r = self.receipts.get(rrr)
            if not r:
                raise TerminalError("not-found: receipt")
            if r["status"] != "paid":
                raise TerminalError("receipt not paid; cannot link")
            r["linked_account"] = account
            return {"status": "linked", "rrr": rrr, "account": account,
                    "link_ref": f"L-{rrr[-4:]}"}
        return self._once(idempotency_key, _fire)

    def resend_certificate(self, *, plate, email, idempotency_key):
        def _fire():
            if plate not in self.certificates:
                raise TerminalError("not-found: certificate")
            return {"status": "resent", "plate": plate, "email": email}
        return self._once(idempotency_key, _fire)

    def renew_certificate(self, *, plate, state, rrr, idempotency_key):
        def _fire():
            r = self.receipts.get(rrr)
            if not r or r["status"] != "paid":
                raise TerminalError("renewal requires a paid RRR")
            c = self.certificates.setdefault(plate, {"plate": plate})
            c.update({"status": "approved", "cert_no": "CMR- renewed",
                      "expiry": "2028-01-01"})
            return {"status": "renewed", "cert_no": c["cert_no"], "expiry": c["expiry"]}
        return self._once(idempotency_key, _fire)

    def correct_certificate(self, *, plate, field, old_value, new_value, reason,
                            request_age_days, idempotency_key):
        def _fire():
            if request_age_days is not None and request_age_days > 30:
                raise TerminalError("outside 30-day correction window; refer to HQ")
            if field == "color" and str(new_value).lower() == "custom":
                raise TerminalError("Custom colour not allowed on the portal")
            return {"status": "corrected", "plate": plate, "field": field,
                    "ticket": f"CORR-{len(self.fired) + 1:04d}"}
        return self._once(idempotency_key, _fire)


# deep-copy helper for test isolation
def fresh_mock(**faults) -> MockDB:
    db = MockDB.seeded()
    db.faults = dict(faults)
    return db
