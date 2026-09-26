"""Case extractor -> task-specific structured JSON validated by Pydantic.

Persists raw response + accepted fields (caller stores via repository).
One real task type ships first: payment_reconciliation.
Generic CMR entities are extracted for every input.
"""
from __future__ import annotations

import re
from typing import Any

from harness.agent.schemas import ExtractedValue

# task_type -> required field names + human prompt when missing
TASK_SCHEMAS: dict[str, dict[str, Any]] = {
    "payment_reconciliation": {
        "required": ["remita_rrr", "payment_date", "account_identifier"],
        "optional": ["nin", "phone", "email", "plate_number"],
        "missing_prompt": {
            "remita_rrr": "Please provide your 12-digit Remita RRR receipt number.",
            "payment_date": "On which date did you make the payment?",
            "account_identifier": "Which account / plate number / email is the payment for?",
        },
    },
    "change_of_ownership": {
        "required": ["plate_number", "buyer_name", "seller_name"],
        "optional": ["nin", "phone", "chassis_number"],
        "missing_prompt": {
            "plate_number": "What is the vehicle plate number?",
            "buyer_name": "Who is the buyer (full name)?",
            "seller_name": "Who is the seller (full name)?",
        },
    },
    "general_support": {
        "required": [],
        "optional": ["nin", "phone", "email", "plate_number", "remita_rrr"],
        "missing_prompt": {},
    },
}


_FILLER = re.compile(r"^(?:is|are|was|no\.?|number|num|of)\b[\s:#-]*", re.I)


def _clean(captured: str | None) -> str | None:
    """Strip filler words ("is", "number", ...) between a label and its value."""
    if not captured:
        return None
    v = captured.strip()
    while True:
        nv = _FILLER.sub("", v).strip()
        if nv == v:
            return v or None
        v = nv


def extract(text: str) -> list[ExtractedValue]:
    t = text or ""
    out: list[ExtractedValue] = []

    def _add(name, raw, norm, conf, dtype="string"):
        if raw:
            out.append(ExtractedValue(name=name, data_type=dtype, raw_value=str(raw),
                                      normalized_value=norm, confidence=conf, validation="valid"))

    m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", t)
    _add("email", m.group(0) if m else None, m.group(0).lower() if m else None, 0.95)

    m = re.search(r"\b(\d{12})\b", t)
    _add("remita_rrr", m.group(1) if m else None, m.group(1) if m else None, 0.9)

    # Phone first (11-digit 070/080/081/090/091 or +234...); NIN must not be phone-like.
    mp = re.search(r"(?:\+?234|0)?[789][01]\d{8}\b", t)
    phone_val = mp.group(0) if mp else None
    _add("phone", phone_val, phone_val, 0.85)

    # NIN: 11 digits, excluding phone-like prefixes
    mn = re.search(r"(?<!\d)(\d{11})(?!\d)", t)
    nin_val = mn.group(1) if mn else None
    if nin_val and (nin_val == phone_val or re.match(r"^(0?[789][01]|234[789][01])", nin_val)):
        nin_val = None
    _add("nin", nin_val, nin_val, 0.9)

    m = re.search(r"(?:plate(?: number)?|registration number|reg no)[:#\s-]*([A-Z0-9][A-Z0-9 -]{4,14})", t, re.I)
    _plate = _clean(m.group(1)) if m else None
    _add("plate_number", _plate,
         re.sub(r"\s+", "", _plate.upper()) if _plate else None, 0.8)

    m = re.search(r"(?:chassis|vin)[:#\s-]*([A-Z0-9][A-Z0-9 -]{7,24})", t, re.I)
    _add("chassis_number", m.group(1).strip() if m else None,
         re.sub(r"\s+", "", m.group(1).strip().upper()) if m else None, 0.8)

    m = re.search(r"\b(today|yesterday|\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{1,2}-\d{1,2})\b", t.lower())
    _add("payment_date", m.group(0) if m else None, m.group(0) if m else None, 0.7)

    # account identifier: explicit "account ..." or fallback to email/plate/phone
    m = re.search(r"account[:#\s-]*([A-Za-z0-9@._ -]{3,40})", t, re.I)
    if m:
        _acct = _clean(m.group(1))
        _add("account_identifier", _acct, _acct, 0.6)
    else:
        for cand in ("email", "plate_number", "phone"):
            hit = next((e for e in out if e.name == cand), None)
            if hit:
                _add("account_identifier", hit.raw_value, hit.normalized_value, 0.5)
                break

    m = re.search(r"(?:buyer|seller)[:#\s-]+([A-Za-z ]{3,40})", t, re.I)
    if m:
        role = "buyer_name" if "buyer" in m.group(0).lower() else "seller_name"
        _who = _clean(m.group(1))
        _add(role, _who, _who.title() if _who else None, 0.6)
    m = re.search(r"(?:my name is|full name)[:\s]+([A-Za-z ]{3,40})", t, re.I)
    if m:
        _add("requester_name", m.group(1).strip(), m.group(1).strip().title(), 0.6)

    _llm_primary_merge(t, out, _add)
    return out


# Model-primary extraction: the model proposes the full field map; regex acts
# as validator (patterned IDs) and safety net (whatever the model missed).
# Principle: model decides, patterns enforce. Model silent → regex-only floor.
_FULLMAP_PROMPT = (
    "Extract every field present in this CMR support message. Reply with ONLY one JSON "
    "object mapping keys to string values, using only these keys: remita_rrr (12 digits), "
    "nin (11 digits), phone, email, plate_number, chassis_number, payment_date, "
    "account_identifier, buyer_name, seller_name, requester_name. Omit absent keys. "
    "buyer_name/seller_name/requester_name hold ONLY the person's name — no titles, "
    "no surrounding words (e.g. \"Adaeze Okafor\", never \"the buyer is Adaeze\"). "
    "Copy ID numbers exactly as written; never invent digits."
)

_ID_PATTERNS = {
    "remita_rrr": re.compile(r"^\d{12}$"),
    "nin": re.compile(r"^\d{11}$"),
    "phone": re.compile(r"^(?:\+?234|0)?[789][01]\d{8}$"),
    "email": re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"),
}

_NAME_FIELDS = {"buyer_name", "seller_name", "requester_name", "account_identifier"}


def _id_ok(name: str, value: str) -> bool:
    v = value.strip()
    if name == "nin":
        # 11 digits AND not phone-like
        return bool(re.match(r"^\d{11}$", v)) and not bool(
            re.match(r"^(0?[789][01]|234[789][01])", v))
    pat = _ID_PATTERNS.get(name)
    if pat is not None:
        return bool(pat.match(v))
    return len(v) >= 3  # plate/chassis/date: loose sanity


def _llm_primary_merge(t: str, out: list[ExtractedValue], _add) -> None:
    from harness.agent import llm as llm_mod

    obj = llm_mod.propose_json(_FULLMAP_PROMPT, t, max_new_tokens=600)
    if not obj:
        print("[extractor] model silent, regex floor stands", flush=True)
        return  # emergency floor: regex findings stand as-is
    have = {e.name: e for e in out}
    for name, raw in obj.items():
        if not isinstance(raw, str) or not raw.strip():
            continue
        val = raw.strip()[:120]
        if name in _NAME_FIELDS:
            if name not in have:
                try:
                    out.append(ExtractedValue(
                        name=name, data_type="string", raw_value=val,
                        normalized_value=val.title(), confidence=0.7,
                        validation="pending"))
                except Exception:
                    continue
        elif name in _ID_PATTERNS or name in ("plate_number", "chassis_number",
                                              "payment_date", "nin"):
            if not _id_ok(name, val):
                continue  # model hallucinated the pattern: reject, keep regex
            if name not in have:
                norm = val.lower() if name == "email" else val.upper() if name in (
                    "plate_number", "chassis_number") else val
                _add(name, val, norm, 0.85)


def validate_for_task(task_type: str, fields: dict[str, Any]) -> tuple[bool, list[str]]:
    schema = TASK_SCHEMAS.get(task_type, TASK_SCHEMAS["general_support"])
    missing = [r for r in schema["required"] if not fields.get(r)]
    return (len(missing) == 0, missing)


def missing_prompt(task_type: str, field: str) -> str:
    return TASK_SCHEMAS.get(task_type, {}).get("missing_prompt", {}).get(
        field, f"Please provide: {field}.")
