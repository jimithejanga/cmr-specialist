"""Formulation catalog (PDF v3 §3–§5).

Every template carries: id, verb, endpoint, typed inputs, permission,
approval, idempotency, evidence requirement, timeout, retries, result shape.
The formulation IS the policy — policy.py only enforces two rules:
  1. CHECKs pass freely (allowlisted + schema-valid).
  2. WRITEs need approval + idempotency key + named evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Formulation:
    id: str                      # e.g. CHECK.receipt.lookup
    verb: str                    # CHECK | WRITE
    endpoint: str                # module API path (not the DB)
    inputs: dict                 # name -> spec {type, required, pattern?}
    permission: str              # standard | sensitive
    approval: str                # none | single
    idempotency: str             # not-required | required
    evidence: str | None         # required check verdict, e.g. "receipt=paid"
    timeout_s: int
    retries: int                 # reads only; writes always 0
    returns: tuple               # result keys


def _check(fid, endpoint, inputs, returns):
    return Formulation(fid, "CHECK", endpoint, inputs, "standard", "none",
                       "not-required", None, 15, 2, returns)


def _write(fid, endpoint, inputs, returns, evidence=None):
    return Formulation(fid, "WRITE", endpoint, inputs, "sensitive", "single",
                       "required", evidence, 60, 0, returns)


CATALOG: dict[str, Formulation] = {}

for _f in [
    # ── CHECKs (8) ──────────────────────────────────────────────────────
    _check("CHECK.profile.lookup", "GET /tool/check/profile",
           {"phone": {"type": "string", "required": False},
            "email": {"type": "string", "required": False}},
           ("exists", "profile_id", "username_type")),
    _check("CHECK.nin.verify", "GET /tool/check/nin",
           {"nin": {"type": "string", "required": True, "pattern": r"^\d{11}$"}},
           ("verdict",)),
    _check("CHECK.nimc.health", "GET /tool/check/nimc-health", {},
           ("state",)),
    _check("CHECK.vehicle.lookup", "GET /tool/check/vehicle",
           {"plate": {"type": "string", "required": False},
            "chassis": {"type": "string", "required": False}},
           ("vehicle_id", "plate", "owner", "cert_state")),
    _check("CHECK.owner.lookup", "GET /tool/check/owner",
           {"vehicle_id": {"type": "string", "required": False},
            "plate": {"type": "string", "required": False}},
           ("owner", "history_count")),
    _check("CHECK.buyer.search", "GET /tool/check/buyer",
           {"phone": {"type": "string", "required": False},
            "email": {"type": "string", "required": False},
            "nin": {"type": "string", "required": False},
            "tin": {"type": "string", "required": False}},
           ("match", "profile_id")),
    _check("CHECK.receipt.lookup", "GET /tool/check/receipt",
           {"rrr": {"type": "string", "required": True, "pattern": r"^\d{12}$"}},
           ("status", "amount", "date", "linked_account")),
    _check("CHECK.certificate.lookup", "GET /tool/check/certificate",
           {"plate": {"type": "string", "required": True}},
           ("status", "request_age_h", "expiry")),
    # ── WRITEs (7) ──────────────────────────────────────────────────────
    _write("WRITE.token.resend", "POST /tool/write/token-resend",
           {"profile_id": {"type": "string", "required": True},
            "medium": {"type": "string", "required": True}},
           ("status", "medium")),
    _write("WRITE.transfer.initiate", "POST /tool/write/transfer",
           {"vehicle_id": {"type": "string", "required": True},
            "buyer_profile_id": {"type": "string", "required": True},
            "doc_ref": {"type": "string", "required": True}},
           ("status", "transfer_ref")),
    _write("WRITE.payment.confirm", "POST /tool/write/payment-confirm",
           {"request_ref": {"type": "string", "required": True},
            "rrr": {"type": "string", "required": True, "pattern": r"^\d{12}$"}},
           ("status", "rrr"), evidence="receipt=paid"),
    _write("WRITE.payment.link", "POST /tool/write/payment-link",
           {"rrr": {"type": "string", "required": True, "pattern": r"^\d{12}$"},
            "account": {"type": "string", "required": True}},
           ("status", "link_ref"), evidence="receipt=paid"),
    _write("WRITE.certificate.resend", "POST /tool/write/certificate-resend",
           {"plate": {"type": "string", "required": True},
            "email": {"type": "string", "required": True}},
           ("status",)),
    _write("WRITE.certificate.renew", "POST /tool/write/certificate-renew",
           {"plate": {"type": "string", "required": True},
            "state": {"type": "string", "required": True},
            "rrr": {"type": "string", "required": True, "pattern": r"^\d{12}$"}},
           ("status", "cert_no", "expiry"), evidence="receipt=paid"),
    _write("WRITE.certificate.correct", "POST /tool/write/certificate-correct",
           {"plate": {"type": "string", "required": True},
            "field": {"type": "string", "required": True},
            "old_value": {"type": "string", "required": False},
            "new_value": {"type": "string", "required": True},
            "reason": {"type": "string", "required": True},
            "request_age_days": {"type": "number", "required": False}},
           ("status", "ticket")),
]:
    CATALOG[_f.id] = _f


# family plan templates: complaint → formulation sequence (PDF v3 §8)
FAMILY_PLANS: dict[str, list[str]] = {
    "password_reset_otp": ["CHECK.profile.lookup", "WRITE.token.resend"],
    "validation_nin": ["CHECK.nin.verify", "CHECK.nimc.health"],
    "change_of_ownership": ["CHECK.vehicle.lookup", "CHECK.owner.lookup",
                            "CHECK.buyer.search", "WRITE.transfer.initiate"],
    "payment_issue": ["CHECK.receipt.lookup", "CHECK.vehicle.lookup",
                      "WRITE.payment.confirm", "WRITE.payment.link"],
    "certificate_issue": ["CHECK.certificate.lookup", "CHECK.receipt.lookup",
                          "WRITE.certificate.renew", "WRITE.certificate.resend",
                          "WRITE.certificate.correct"],
}

# Phase-4 viability: a formulation step is only plannable when its inputs
# resolve. Case-field names map to argument names; doc_ref/reason are always
# defaulted by the service; prior steps' declared returns chain forward.
FIELD_ARG_NAMES = {
    "remita_rrr": "rrr", "rrr": "rrr",
    "plate_number": "plate", "plate": "plate",
    "chassis_number": "chassis", "chassis": "chassis",
    "nin": "nin", "phone": "phone", "email": "email",
    "account_identifier": "account", "account": "account", "tin": "tin",
}
ALWAYS_PROVIDED = {"doc_ref", "reason"}
# The searched buyer IS the transfer buyer: profile_id satisfies it.
SATISFIED_BY = {"buyer_profile_id": "profile_id"}


def _resolves(name: str, provided: set[str]) -> bool:
    if name in provided:
        return True
    alt = SATISFIED_BY.get(name)
    return bool(alt and alt in provided)


def viable_family_plan(family: str, fields: dict) -> list[str]:
    """Prune a family template to steps whose inputs resolve.

    A step survives when every required input resolves (from case fields,
    always-defaulted args, or an earlier surviving step's returns) AND at
    least one input resolves at all (a CHECK with zero identifiers is not a
    check, it is a guess). Returns the surviving formulation IDs in order.
    """
    tools = FAMILY_PLANS.get(family, [])
    provided: set[str] = set()
    for fname, arg in FIELD_ARG_NAMES.items():
        if (fields or {}).get(fname):
            provided.add(arg)
    provided |= set(ALWAYS_PROVIDED)
    viable: list[str] = []
    for fid in tools:
        form = CATALOG.get(fid)
        if form is None:
            continue
        inputs = form.inputs or {}
        required = [n for n, s in inputs.items() if s.get("required")]
        if any(not _resolves(n, provided) for n in required):
            continue
        if inputs and not any(_resolves(n, provided) for n in inputs):
            continue
        viable.append(fid)
        provided |= set(form.returns or ())
    return viable


# Human questions for unresolvable WRITE inputs (used when a family plan
# loses all its WRITEs: the task must ask, not silently complete read-only).
WRITE_INPUT_PROMPTS = {
    "phone": "buyer phone number",
    "email": "buyer email address",
    "nin": "buyer NIN",
    "account": "payment account",
    "rrr": "12-digit Remita RRR",
    "plate": "vehicle plate number",
    "request_ref": "payment request reference",
    "state": "certificate state",
}


def blocking_inputs(family: str, fields: dict) -> list[str]:
    """Field-level inputs blocking the family's WRITEs, in plan order.

    Used when viability pruning would silently drop every WRITE: instead of
    completing read-only, the task waits and asks for exactly these. The
    walk follows the chain backward (WRITE needs buyer_profile_id <- the
    buyer search needs a phone), so the user is asked for real facts, never
    internal wiring names. Returns [] when at least one WRITE is executable.
    """
    viable = viable_family_plan(family, fields)
    template = FAMILY_PLANS.get(family, [])
    writes = [f for f in template
              if CATALOG.get(f) is not None and CATALOG[f].verb == "WRITE"]
    if not writes or any(f in viable for f in writes):
        return []
    provided: set[str] = set()
    for fname, arg in FIELD_ARG_NAMES.items():
        if (fields or {}).get(fname):
            provided.add(arg)
    provided |= set(ALWAYS_PROVIDED)
    for fid in template:
        if fid in viable:
            form = CATALOG.get(fid)
            if form:
                provided |= set(form.returns or ())
    wanted: list[str] = []
    # Ask only for facts a user can supply in a follow-up; chain-only names
    # (request_ref, internal ids) are the system's problem, not the user's.
    suppliable = set(FIELD_ARG_NAMES.values())

    def provides(n: str) -> bool:
        for fid in template:
            form = CATALOG.get(fid)
            if form is None:
                continue
            returns = set(form.returns or ())
            if n in returns or SATISFIED_BY.get(n) in returns:
                return True
        return False

    def need(name: str, depth: int = 0) -> None:
        if _resolves(name, provided) or depth > 3:
            return
        progressed = False
        for fid in template:
            form = CATALOG.get(fid)
            if form is None:
                continue
            returns = set(form.returns or ())
            alias = SATISFIED_BY.get(name)
            if name in returns or (alias and alias in returns):
                progressed = True
                for n in (form.inputs or {}):
                    if not _resolves(n, provided):
                        if provides(n):
                            need(n, depth + 1)
                        elif n in suppliable and n not in wanted:
                            wanted.append(n)
        if not progressed and name in suppliable and name not in wanted:
            wanted.append(name)

    for fid in template:
        form = CATALOG.get(fid)
        if form is None or form.verb != "WRITE":
            continue
        for n, s in (form.inputs or {}).items():
            if s.get("required"):
                need(n)
                # Root facts are asked directly even when a (blocked) provider
                # exists downstream - e.g. the RRR itself, not just the account.
                if (not _resolves(n, provided) and n in suppliable
                        and n not in wanted):
                    wanted.append(n)
    return wanted



def prompt_for_input(name: str) -> str:
    label = WRITE_INPUT_PROMPTS.get(name, name.replace("_", " "))
    return f"Please provide the {label} so the write step can run."
