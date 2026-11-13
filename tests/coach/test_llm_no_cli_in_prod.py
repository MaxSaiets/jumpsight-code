"""The LLM layer is OpenAI only: no CLI path, no key files, no network in tests.

Without an API key the layer refuses honestly with an explanation, and the chat
shows a source excerpt with a note instead of staying silent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jumpsight_coach import llm


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in ("OPENAI_API_KEY", "JS_PROD", "MODAL_TASK_ID", "MODAL_ENVIRONMENT"):
        monkeypatch.delenv(k, raising=False)


def test_no_key_means_no_provider_and_a_clear_refusal():
    assert llm.provider() == "none"
    assert llm.key_source() is None
    with pytest.raises(llm.LLMUnavailable) as exc:
        llm.complete("hi")
    assert "OPENAI_API_KEY" in str(exc.value)


def test_key_comes_from_the_environment_only(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert llm.provider() == "openai"
    assert llm.key_source() == "env"


def test_no_cli_or_key_file_code_remains():
    src = Path(llm.__file__).read_text(encoding="utf-8")
    assert "claude" not in src.lower()
    assert ".openai.key" not in src and "KEY_FILE" not in src
    from jumpsight_coach import core

    assert not hasattr(core, "call_llm") and not hasattr(core, "claude_exe")


def test_health_without_key_is_reported_not_raised():
    llm._HEALTH_CACHE["value"] = None
    res = llm.health(force=True)
    assert res["ok"] is False and res["provider"] == "none"


def test_chat_without_model_shows_excerpt_with_note(monkeypatch):
    from jumpsight_coach import knowledge as k

    rows = [{"text": "The Axel takes off forwards.", "source": "S", "url": "", "lang": "en"}]
    monkeypatch.setattr(k, "CORPUS", __import__("pathlib").Path(__file__))  # corpus "exists"
    monkeypatch.setattr(k, "_load", lambda: (rows, __import__("numpy").ones((1, 3))))
    monkeypatch.setattr(k, "_lexical_hits", lambda q, kk=5: None)

    class _M:
        def encode(self, *a, **kw):
            return __import__("numpy").ones((1, 3))

    monkeypatch.setattr(k, "_m", lambda: _M())
    k._FALLBACK_READY.set()
    monkeypatch.setattr(k.embed, "_model", object())
    r = k.ask("zzzz qqqq")
    assert r["answer"] and r.get("note")
    assert r["failure_kind"] == "LLMUnavailable"
