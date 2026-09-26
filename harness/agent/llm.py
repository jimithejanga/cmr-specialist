"""LLM proposal helper (PDF v3: model proposes, software enforces).

All functions return None when no model is configured or any failure occurs,
so callers always fall back to deterministic behavior. Never raises.
Transient upstream errors (e.g. Gemini 503s) get one retry after a pause.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Any

log = logging.getLogger("cmr.llm")

_RETRIES = 1
_RETRY_PAUSE_S = 4.0

# Usage ledger (visibility into the limiter). est_tokens uses ~4 chars/token.
_stats = {"calls": 0, "cache_hits": 0, "est_tokens_in": 0, "est_tokens_out": 0}
_cache: dict[str, tuple[float, Any]] = {}
_last_call_ts = 0.0


def stats() -> dict[str, int]:
    return dict(_stats)


def _throttle() -> None:
    """Pace outbound calls so per-minute quotas survive bursts."""
    global _last_call_ts
    from configs.settings import settings

    gap = time.monotonic() - _last_call_ts
    wait = settings.LLM_MIN_INTERVAL_S - gap
    if wait > 0:
        time.sleep(min(wait, 10.0))
    _last_call_ts = time.monotonic()


def _cache_get(key: str):
    from configs.settings import settings

    hit = _cache.get(key)
    if hit and (time.monotonic() - hit[0]) < settings.LLM_CACHE_TTL_S:
        _stats["cache_hits"] += 1
        return hit[1]
    return None


def _cache_put(key: str, value: Any) -> None:
    _cache[key] = (time.monotonic(), value)


def _key(kind: str, system: str, user_text: str, max_new_tokens: int) -> str:
    h = hashlib.sha256(f"{system}\n{user_text[:2000]}\n{max_new_tokens}".encode()).hexdigest()[:16]
    return f"{kind}:{h}"


def propose_json(system: str, user_text: str, *, max_new_tokens: int = 600) -> dict[str, Any] | None:
    """Ask the configured model for one JSON object. Cached + paced. None on failure."""
    from harness.inference.gateway import InferenceGateway

    if not InferenceGateway.llm_enabled():
        return None
    key = _key("json", system, user_text, max_new_tokens)
    hit = _cache_get(key)
    if hit is not None:
        return hit
    for attempt in range(_RETRIES + 1):
        try:
            _throttle()
            raw = InferenceGateway().generate_response(
                [{"role": "system", "content": system},
                 {"role": "user", "content": user_text[:2000]}],
                temperature=0, max_new_tokens=max_new_tokens)
            _stats["calls"] += 1
            _stats["est_tokens_in"] += (len(system) + len(user_text)) // 4
            _stats["est_tokens_out"] += len(raw or "") // 4
            parsed = _parse_json(raw)
            if parsed is not None:
                _cache_put(key, parsed)
                return parsed
            return None  # well-formed reply, unparseable content: don't retry
        except Exception as exc:
            if attempt < _RETRIES:
                time.sleep(_RETRY_PAUSE_S)
                continue
            log.warning("LLM proposal failed, using deterministic fallback: %s", exc)
            return None


def propose_text(system: str, user_text: str, *, max_new_tokens: int = 800) -> str | None:
    from harness.inference.gateway import InferenceGateway

    if not InferenceGateway.llm_enabled():
        return None
    key = _key("text", system, user_text, max_new_tokens)
    hit = _cache_get(key)
    if hit is not None:
        return hit
    for attempt in range(_RETRIES + 1):
        try:
            _throttle()
            out = InferenceGateway().generate_response(
                [{"role": "system", "content": system},
                 {"role": "user", "content": user_text[:3000]}],
                temperature=0.2, max_new_tokens=max_new_tokens)
            _stats["calls"] += 1
            _stats["est_tokens_in"] += (len(system) + len(user_text)) // 4
            _stats["est_tokens_out"] += len(out or "") // 4
            if out and out.strip():
                _cache_put(key, out)
            return out
        except Exception as exc:
            if attempt < _RETRIES:
                time.sleep(_RETRY_PAUSE_S)
                continue
            log.warning("LLM draft failed, using deterministic fallback: %s", exc)
            return None


def _parse_json(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except (json.JSONDecodeError, ValueError):
            return None
    return None
