"""Output validator: evidence, result schema, case updates, user-safe response.

Software MUST enforce (spec 03 table):
- citation presence + active-source check for knowledge answers
- verified tool outcomes + stored final state for task completion
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ValidationResult:
    valid: bool
    reason: str = ""
    fallback: bool = False


# Phase-4 evidence rule: high-risk tokens in the answer (figures, verdicts,
# identifiers) must occur verbatim in the cited spans. A citation list that
# does not contain the claim is decoration, not evidence.
_VERDICT_WORDS = {"verified", "paid", "approved", "confirmed", "transferred",
                  "renewed", "valid", "rejected", "suspended"}
_TOKEN_RE = re.compile(r"\d[\d,]*(?:\.\d+)?|[A-Za-z]{4,}")

_STOP = {"that", "this", "with", "from", "your", "have", "been", "will",
         "step", "click", "visit", "select", "enter", "based", "procedures",
         "following", "using", "question"}


def _high_risk_tokens(answer: str) -> list[str]:
    toks: list[str] = []
    for m in _TOKEN_RE.findall(answer):
        low = m.lower()
        if m[0].isdigit():
            if len(m) >= 4:  # figures, years, ID runs - never uncited
                toks.append(low)
        elif low in _VERDICT_WORDS:
            toks.append(low)
    # de-dupe, keep order
    seen: set[str] = set()
    return [t for t in toks if not (t in seen or seen.add(t))]


def validate_knowledge_answer(answer: str, citations: list) -> ValidationResult:
    if not answer or not answer.strip():
        return ValidationResult(valid=False, reason="empty answer", fallback=True)
    if not citations:
        return ValidationResult(valid=False, reason="no citations", fallback=True)
    lowered = answer.lower()
    # must not claim an external event occurred without verified tool result
    for claim in ["payment has been confirmed", "your account has been updated",
                  "ownership has been transferred", "refund has been issued"]:
        if claim in lowered:
            return ValidationResult(valid=False,
                                    reason=f"unverified external claim: '{claim}'", fallback=True)
    spans = " ".join(getattr(c, "text", "") or "" for c in citations).lower()
    for tok in _high_risk_tokens(answer):
        if tok not in spans:
            return ValidationResult(valid=False,
                                    reason=f"unsupported token not in citations: '{tok}'",
                                    fallback=True)
    return ValidationResult(valid=True, reason="cited answer")


def validate_task_result(result: dict) -> ValidationResult:
    if not isinstance(result, dict) or "summary" not in result:
        return ValidationResult(valid=False, reason="result missing summary")
    if result.get("status") not in {"completed", "waiting_for_input", "waiting_approval", "failed"}:
        return ValidationResult(valid=False, reason="unknown result status")
    if result.get("status") == "completed":
        # Phase-2 backstop: no completed stamp over failed tool results.
        for name, out in (result.get("tool_results") or {}).items():
            if isinstance(out, dict) and out.get("status") == "failed":
                return ValidationResult(valid=False,
                                        reason=f"completed over failed tool result: {name}")
    return ValidationResult(valid=True, reason="result schema ok")
