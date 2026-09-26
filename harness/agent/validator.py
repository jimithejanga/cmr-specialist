"""Output validator: evidence, result schema, case updates, user-safe response.

Software MUST enforce (spec 03 table):
- citation presence + active-source check for knowledge answers
- verified tool outcomes + stored final state for task completion
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ValidationResult:
    valid: bool
    reason: str = ""
    fallback: bool = False


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
    return ValidationResult(valid=True, reason="cited answer")


def validate_task_result(result: dict) -> ValidationResult:
    if not isinstance(result, dict) or "summary" not in result:
        return ValidationResult(valid=False, reason="result missing summary")
    if result.get("status") not in {"completed", "waiting_for_input", "waiting_approval", "failed"}:
        return ValidationResult(valid=False, reason="unknown result status")
    return ValidationResult(valid=True, reason="result schema ok")
