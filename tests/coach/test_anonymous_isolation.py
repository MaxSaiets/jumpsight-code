"""A request without a session does not read or write the shared 'old' state.

A new visitor on the very first load must not see someone else's 'Last answer': /coach/history without a cookie must not read the shared history file where ownerless tasks write.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def test_sessionless_history_is_empty_and_isolated(monkeypatch, tmp_path):
    from jumpsight_coach import accounts, jobs, sessions
    from jumpsight_coach.api import app

    monkeypatch.setattr(accounts, "STORE", tmp_path / "accounts.json")
    monkeypatch.setattr(accounts, "USERS", tmp_path / "users")
    monkeypatch.setattr(sessions, "DB", tmp_path / "sessions.sqlite3")

    legacy = Path(jobs.__file__).resolve().parent / "out" / "history.json"
    before = legacy.read_bytes() if legacy.exists() else None
    anon = TestClient(app, base_url="http://localhost")
    r = anon.get("/history?lang=uk")
    assert r.status_code == 200
    assert r.json() == []
    after = legacy.read_bytes() if legacy.exists() else None
    assert before == after


def test_user_path_outside_http_keeps_legacy_path():
    from jumpsight_coach.userctx import begin_anonymous_request, end_anonymous_request, user_path

    p = Path("coach/out/history.json")
    assert user_path(p) == p
    tok = begin_anonymous_request()
    try:
        anon = user_path(p)
        assert anon != p and anon.name == "history.json"
        anon.write_text(json.dumps([{"x": 1}]), encoding="utf-8")
    finally:
        end_anonymous_request(tok)
    assert not anon.exists()
    assert user_path(p) == p


def test_goal_only_session_does_not_mention_a_clip():
    """A session on a chosen target without a clip: the explanation does not mention 'this clip'."""
    from jumpsight_coach.session import build_for_goal

    out = build_for_goal("rotation_power", lang="en")
    text = " ".join(str(x) for x in (out.get("personalisation") or []))
    assert "clip" not in text, text
