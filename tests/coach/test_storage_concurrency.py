"""Concurrent properties of the local transactional session storage."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor


def test_attempt_limit_is_atomic_across_connections(monkeypatch, tmp_path):
    from jumpsight_coach import sessions

    monkeypatch.setattr(sessions, "DB", tmp_path / "sessions.sqlite3")
    monkeypatch.setattr(sessions, "_REMOTE", None)
    limit = 12
    with ThreadPoolExecutor(max_workers=16) as pool:
        accepted = list(pool.map(lambda _: sessions.allow_attempt("login", "127.0.0.1", limit, 600), range(64)))
    assert sum(accepted) == limit


def test_transfer_token_is_consumed_once_across_connections(monkeypatch, tmp_path):
    from jumpsight_coach import sessions

    monkeypatch.setattr(sessions, "DB", tmp_path / "sessions.sqlite3")
    monkeypatch.setattr(sessions, "_REMOTE", None)
    token = sessions.issue_transfer("guest_transfer_123")
    with ThreadPoolExecutor(max_workers=12) as pool:
        consumed = list(pool.map(lambda _: sessions.consume_transfer(token), range(32)))
    assert consumed.count("guest_transfer_123") == 1
    assert consumed.count(None) == 31


def test_remote_attempt_store_fails_closed_without_atomic_increment(monkeypatch):
    from jumpsight_coach import sessions

    monkeypatch.setattr(sessions, "_REMOTE", {})
    try:
        sessions.allow_attempt("login", "127.0.0.1")
    except RuntimeError as exc:
        assert "atomic_increment" in str(exc)
    else:
        raise AssertionError("non-atomic remote store must not rate-limit silently")
