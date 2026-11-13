"""LLM access: OpenAI chat completions only.

Configuration (environment only, nothing is read from disk):
    OPENAI_API_KEY         API key
    JS_OPENAI_MODEL        model name (default gpt-4o-mini)
    JS_LLM_HEALTH_TTL_S    how long a health probe is cached (default 300)

Prompts are English (prompts.py); the output language is a separate field.
The LLM is never a source of facts: callers validate its output against the
retrieved sources.
"""

from __future__ import annotations

import json
import os

_client = None
DEFAULT_MODEL = "gpt-4o-mini"


def api_key() -> str | None:
    k = os.environ.get("OPENAI_API_KEY", "").strip()
    return k or None


def key_source() -> str | None:
    """Where the key came from: "env" or None. The value is never exposed."""
    return "env" if api_key() else None


class LLMUnavailable(RuntimeError):
    """No API key is configured."""


def is_prod() -> bool:
    """Production: explicit JS_PROD=1 or a Modal container."""
    if os.environ.get("JS_PROD", "").strip().lower() in ("1", "true", "yes", "on"):
        return True
    return bool(os.environ.get("MODAL_TASK_ID") or os.environ.get("MODAL_ENVIRONMENT"))


def model_name() -> str:
    return os.environ.get("JS_OPENAI_MODEL", DEFAULT_MODEL)


def provider() -> str:
    """openai | none."""
    return "openai" if api_key() else "none"


def unavailable_reason() -> str:
    return "no LLM API key is configured (OPENAI_API_KEY)"


def _openai():
    global _client
    if _client is None:
        from openai import OpenAI

        _client = OpenAI(api_key=api_key())
    return _client


def complete(
    prompt: str, *, system: str | None = None, json_mode: bool = True, timeout: int = 90, model: str | None = None
) -> str:
    """One LLM call. Returns the raw text of the answer."""
    if provider() == "none":
        raise LLMUnavailable(unavailable_reason())
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    kw = {"model": model or model_name(), "messages": msgs, "timeout": timeout, "temperature": 0}
    if json_mode:
        kw["response_format"] = {"type": "json_object"}
    r = _openai().chat.completions.create(**kw)
    return (r.choices[0].message.content or "").strip()


def complete_json(prompt: str, *, system: str | None = None, timeout: int = 90, model: str | None = None) -> dict:
    """Call with JSON mode on, plus a tolerant parser for fenced answers."""
    from .core import extract_json

    txt = complete(prompt, system=system, json_mode=True, timeout=timeout, model=model)
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        return extract_json(txt)


_HEALTH_CACHE: dict = {"at": 0.0, "value": None}
# A health probe is a real paid call with the provider key, so it is cached.
HEALTH_TTL_S = float(os.environ.get("JS_LLM_HEALTH_TTL_S", "300"))


def health(force: bool = False) -> dict:
    """Quick check that the provider is alive and returns JSON (cached)."""
    import time as _t

    now = _t.time()
    cached = _HEALTH_CACHE.get("value")
    if not force and cached is not None and now - _HEALTH_CACHE["at"] < HEALTH_TTL_S:
        out = dict(cached)
        out["cached"] = True
        out["age_s"] = round(now - _HEALTH_CACHE["at"], 1)
        return out
    try:
        d = complete_json('Return exactly {"ok": true}', system="You output strict JSON only.", timeout=30)
        res = {"provider": provider(), "ok": bool(d.get("ok")), "model": model_name()}
    except LLMUnavailable as ex:
        res = {"provider": "none", "ok": False, "error": str(ex)[:200]}
    except Exception as ex:
        res = {"provider": provider(), "ok": False, "error": str(ex)[:200]}
    res["key_source"] = key_source()
    _HEALTH_CACHE["at"], _HEALTH_CACHE["value"] = now, dict(res)
    out = dict(res)
    out["cached"] = False
    out["age_s"] = 0.0
    return out
