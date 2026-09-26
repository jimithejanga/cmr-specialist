"""Intent router -> small enum + confidence + reason (spec 06).

Deterministic rule router is the default (works offline, testable).
An LLM adapter may PROPOSE an intent; this module ENFORCES the enum + fallback.
"""
from __future__ import annotations

import re

from harness.agent.schemas import Intent, IntentResult

_QUESTION_WORDS = {"how", "what", "when", "where", "which", "why", "steps", "process",
                   "procedure", "fee", "fees", "requirement", "requirements", "renew", "renewal"}
_TASK_VERBS = {"register", "reconcile", "verify", "check", "change", "renew", "update",
               "draft", "execute", "process", "confirm", "resolve", "investigate", "do"}
_ENTITY_SIGNALS = [r"\b\d{11}\b", r"\b\d{12}\b", r"@[a-z]", r"plate", r"chassis|vin",
                   r"rrr", r"080|081|070|090|\+234"]
_UNSUPPORTED_SIGNALS = [r"\bhack\b", r"\bbribe\b", r"delete (the )?database",
                        r"transfer money", r"bypass (approval|policy|verification)"]

_INTENT_PROMPT = (
    "You classify citizen messages for the Nigeria Police CMR support desk. "
    "Reply with ONLY one JSON object: {\"intent\": ..., \"confidence\": 0.0-1.0, \"reason\": \"...\"}. "
    "Allowed intents: KNOWLEDGE_QUERY (how-to/process/fee questions), AUTOMATION_TASK "
    "(requests to do something: reconcile, verify, change, renew, confirm), CASE_UPDATE "
    "(supplies facts like NIN/phone/RRR/plate with no question), NEEDS_CLARIFICATION "
    "(too vague to act on), UNSUPPORTED (hacking, bribes, deleting data, bypassing checks)."
)


def _llm_propose(text: str) -> IntentResult | None:
    """Model proposes; this module enforces enum + ranges. None = fall back."""
    from harness.agent import llm as llm_mod

    obj = llm_mod.propose_json(_INTENT_PROMPT, text, max_new_tokens=600)
    if not obj:
        return None
    name = str(obj.get("intent", "")).upper().strip()
    try:
        intent = Intent[name]
    except KeyError:
        return None
    try:
        conf = max(0.0, min(1.0, float(obj.get("confidence", 0.6))))
    except (TypeError, ValueError):
        return None
    reason = str(obj.get("reason", "llm proposal"))[:300]
    return IntentResult(intent=intent, confidence=conf, reason=f"llm: {reason}")


def classify(text: str) -> IntentResult:
    """Model decides. Safety veto first (enforcement, not decision-making);
    rule router last, as emergency fallback only when the model is silent."""
    t = (text or "").strip()
    lowered = t.lower()
    for pat in _UNSUPPORTED_SIGNALS:
        if re.search(pat, lowered):
            return IntentResult(intent=Intent.UNSUPPORTED, confidence=0.95,
                                reason="safety veto: disallowed request pattern")
    proposed = _llm_propose(text)
    if proposed is not None:
        return proposed
    if not t or len(t.split()) < 3:
        return IntentResult(intent=Intent.NEEDS_CLARIFICATION, confidence=0.6,
                            reason="emergency fallback: input too short")
    fallback = _rule_classify(text)
    fallback.reason = f"emergency fallback (model silent): {fallback.reason}"
    return fallback


def _rule_classify(text: str) -> IntentResult:
    t = (text or "").strip()
    lowered = t.lower()

    if not t or len(t.split()) < 3:
        return IntentResult(intent=Intent.NEEDS_CLARIFICATION, confidence=0.6,
                            reason="input too short to classify")

    for pat in _UNSUPPORTED_SIGNALS:
        if re.search(pat, lowered):
            return IntentResult(intent=Intent.UNSUPPORTED, confidence=0.9,
                                reason=f"unsupported request pattern: {pat}")

    has_entity = any(re.search(p, lowered) for p in _ENTITY_SIGNALS)
    has_question = "?" in t or any(w in lowered for w in _QUESTION_WORDS)
    has_task_verb = any(w in lowered for w in _TASK_VERBS)

    # Task takes precedence when an action verb + entity/instruction is present
    if has_task_verb and (has_entity or any(k in lowered for k in
            ["for me", "my ", "please ", "need to", "want to", "help me"])):
        # pure "how do I ..." without entities is knowledge, not a task
        if has_question and not has_entity and lowered.startswith(("how", "what", "which")):
            return IntentResult(intent=Intent.KNOWLEDGE_QUERY, confidence=0.75,
                                reason="how/what question without case entities")
        return IntentResult(intent=Intent.AUTOMATION_TASK, confidence=0.8,
                            reason="action verb with case context")

    if has_question:
        return IntentResult(intent=Intent.KNOWLEDGE_QUERY, confidence=0.8,
                            reason="question about process/steps/fees")
    if has_entity and not has_task_verb:
        return IntentResult(intent=Intent.CASE_UPDATE, confidence=0.7,
                            reason="entities supplied without explicit question or task")
    if has_task_verb:
        return IntentResult(intent=Intent.AUTOMATION_TASK, confidence=0.65,
                            reason="action verb present")
    return IntentResult(intent=Intent.NEEDS_CLARIFICATION, confidence=0.55,
                        reason="no clear question, task, or entities")
