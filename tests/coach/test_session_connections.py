"""Local sessions do not leave an open SQLite after each request."""

import sqlite3

import pytest


def test_session_operations_close_connections(monkeypatch, tmp_path):
    from jumpsight_coach import sessions

    monkeypatch.setattr(sessions, "DB", tmp_path / "sessions.sqlite3")
    real_connect = sqlite3.connect
    connections = []

    def connect(*args, **kwargs):
        con = real_connect(*args, **kwargs)
        connections.append(con)
        return con

    monkeypatch.setattr(sqlite3, "connect", connect)
    token = sessions.create("guest_close_123")
    assert sessions.resolve(token) == "guest_close_123"
    assert sessions.allow_attempt("close", "local", limit=1)
    assert not sessions.allow_attempt("close", "local", limit=1)
    transfer = sessions.issue_transfer("guest_close_123")
    assert sessions.consume_transfer(transfer) == "guest_close_123"
    assert sessions.consume_transfer(transfer) is None
    sessions.revoke(token)
    assert sessions.resolve(token) is None
    for con in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            con.execute("SELECT 1")
