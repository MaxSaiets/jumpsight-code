"""Real concurrent transactions of the local DB; PostgreSQL is a separate launch gate."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from jumpsight_coach.auth_store import AuthStoreUnavailable, DatabaseAuthStore


@pytest.fixture
def store(tmp_path):
    db = DatabaseAuthStore("sqlite:///" + (tmp_path / "auth.sqlite3").as_posix())
    db.initialize()
    yield db
    db.engine.dispose()


def test_atomic_limit_and_window(store):
    with ThreadPoolExecutor(max_workers=16) as pool:
        accepted = list(pool.map(lambda _: store.atomic_increment("attempt:key", 1000, 12, 600), range(64)))
    assert sum(accepted) == 12
    assert not store.atomic_increment("attempt:key", 1599, 12, 600)
    assert store.atomic_increment("attempt:key", 1600, 12, 600)
    assert store.atomic_increment("attempt:other", 1000, 12, 600)


def test_transfer_consumed_once(store):
    store.put("transfer:key", ("guest_transfer_123", 2000))
    with ThreadPoolExecutor(max_workers=12) as pool:
        rows = list(pool.map(lambda _: store.pop("transfer:key", None), range(32)))
    assert sum(row is not None for row in rows) == 1
    assert store.get("transfer:key") is None


def test_sessions_use_database_contract(store, monkeypatch):
    from jumpsight_coach import sessions

    monkeypatch.setattr(sessions, "_REMOTE", store)
    token = sessions.create("guest_database_123")
    assert sessions.resolve(token) == "guest_database_123"
    sessions.revoke(token)
    assert sessions.resolve(token) is None
    store.put("expired", ("guest_database_123", 1))
    store.purge_expired(2)
    assert store.get("expired") is None


def test_missing_schema_fails_without_leaking_database_url(tmp_path):
    db = DatabaseAuthStore("sqlite:///" + (tmp_path / "private-name.sqlite3").as_posix())
    try:
        with pytest.raises(AuthStoreUnavailable, match="^authentication storage unavailable$"):
            db.get("session:key")
    finally:
        db.engine.dispose()


def test_unavailable_store_returns_retryable_503(monkeypatch):
    from fastapi.testclient import TestClient

    from jumpsight_coach import sessions
    from jumpsight_coach.api import app

    monkeypatch.setattr(sessions, "_REMOTE", {})
    client = TestClient(app, base_url="http://localhost")
    response = client.post("/auth/login", json={"email": "user@example.test", "password": "secret-password"})
    assert response.status_code == 503
    assert response.json() == {"detail": "authentication temporarily unavailable"}
    assert response.headers["retry-after"] == "30"


def test_postgresql_attempt_is_one_upsert(store):
    from unittest.mock import patch

    from sqlalchemy.dialects import postgresql

    with patch.object(store.engine.dialect, "name", "postgresql"):
        statement = store.attempt_statement("attempt:key", 1000, 12, 600)
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT" in sql and "RETURNING" in sql and "WHERE" in sql


def test_mounted_app_handles_database_outage(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from jumpsight_app import webapp
    from jumpsight_coach import sessions

    db = DatabaseAuthStore("sqlite:///" + (tmp_path / "missing-schema.sqlite3").as_posix())
    monkeypatch.setattr(sessions, "_REMOTE", db)
    monkeypatch.setattr(webapp, "WORK", tmp_path / "web")
    try:
        client = TestClient(webapp.build_app(), base_url="http://localhost")
        client.cookies.set("js_session", "valid_token_format")
        response = client.get("/coach/me")
        assert response.status_code == 503
        assert "missing-schema" not in response.text
    finally:
        db.engine.dispose()
