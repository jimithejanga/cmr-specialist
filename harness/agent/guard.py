"""Input guard: size limits, file types, injection indicators (spec 06)."""
from __future__ import annotations

import re
from dataclasses import dataclass

from configs.settings import settings

_ALLOWED_ATTACHMENT_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".txt"}

_INJECTION_PATTERNS = [
    r"ignore (all |any |previous |prior )?(instructions|prompts|rules)",
    r"reveal (your |the )?(system|secret|internal) (prompt|instructions|key)",
    r"\bjailbreak\b",
    r"\bDAN\b.{0,20}do anything",
    r"override (safety|policy|guardrail)",
]


@dataclass
class GuardResult:
    allowed: bool
    reason: str = ""
    warnings: list[str] | None = None


def check_text(raw_text: str) -> GuardResult:
    if not raw_text or not raw_text.strip():
        return GuardResult(allowed=False, reason="empty_input")
    if len(raw_text) > settings.MAX_INPUT_CHARS:
        return GuardResult(allowed=False, reason=f"input exceeds {settings.MAX_INPUT_CHARS} chars")
    warnings = []
    lowered = raw_text.lower()
    for pat in _INJECTION_PATTERNS:
        if re.search(pat, lowered):
            warnings.append(f"prompt-injection indicator matched: {pat[:40]}")
    return GuardResult(allowed=True, warnings=warnings or None)


def check_attachment(filename: str, size_bytes: int | None) -> GuardResult:
    suffix = "." + (filename.rsplit(".", 1)[-1].lower() if "." in filename else "")
    if suffix not in _ALLOWED_ATTACHMENT_SUFFIXES:
        return GuardResult(allowed=False, reason=f"file type {suffix or '?'} not accepted")
    if size_bytes is not None and size_bytes > settings.MAX_ATTACHMENT_BYTES:
        return GuardResult(allowed=False, reason="attachment too large")
    return GuardResult(allowed=True)
