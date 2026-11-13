"""Contract of the server-side bootstrap for the guest cookie session."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


def _app(monkeypatch, tmp_path):
    from jumpsight_coach import accounts, sessions
    from jumpsight_coach.api import app

    monkeypatch.setattr(accounts, "STORE", tmp_path / "accounts.json")
    monkeypatch.setattr(accounts, "USERS", tmp_path / "users")
    monkeypatch.setattr(sessions, "DB", tmp_path / "sessions.sqlite3")
    monkeypatch.setattr(sessions, "_REMOTE", None)
    return app


def test_header_cannot_restore_guest_and_bootstrap_is_stable(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)
    replay = TestClient(app, base_url="http://localhost", headers={"X-App-User": "stolen_guest_123"})
    assert replay.get("/me").status_code == 403
    assert "js_session" not in replay.cookies

    created = replay.post("/auth/guest")
    assert created.status_code == 200
    uid = created.json()["uid"]
    assert created.json()["created"] is True
    assert "httponly" in created.headers["set-cookie"].lower()
    assert replay.get("/me").json()["uid"] == uid

    repeated = replay.post("/auth/guest")
    assert repeated.json() == {"uid": uid, "created": False}


def test_unknown_id_header_becomes_fresh_guest(monkeypatch, tmp_path):
    """A client-generated id for every new visitor must not hit a login wall on the first visit. With no data behind the id nothing is lost, so a new guest is issued; the header itself does not make a person."""
    app = _app(monkeypatch, tmp_path)
    client = TestClient(app, base_url="http://localhost", headers={"X-App-User": "fresh_random_id_1234"})
    response = client.post("/auth/guest")
    assert response.status_code == 200
    uid = response.json()["uid"]
    assert uid != "fresh_random_id_1234" and response.json()["created"] is True
    assert client.get("/me").json()["uid"] == uid


def test_independent_bootstraps_are_isolated(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)
    first = TestClient(app, base_url="http://localhost")
    second = TestClient(app, base_url="http://localhost")
    first_uid = first.post("/auth/guest").json()["uid"]
    second_uid = second.post("/auth/guest").json()["uid"]
    assert first_uid != second_uid

    replay = TestClient(app, base_url="http://localhost", headers={"X-App-User": first_uid})
    assert replay.get("/me").status_code == 403
    stored = json.loads((tmp_path / "accounts.json").read_text(encoding="utf-8"))
    assert set(stored["profiles"]) == {first_uid, second_uid}


def test_logout_replaces_session_with_new_guest(monkeypatch, tmp_path):
    app = _app(monkeypatch, tmp_path)
    client = TestClient(app, base_url="http://localhost")
    old_uid = client.post("/auth/guest").json()["uid"]
    logged_out = client.post("/auth/logout")
    assert logged_out.status_code == 200
    assert logged_out.json()["uid"] != old_uid
    assert client.get("/me").json()["uid"] == logged_out.json()["uid"]


def test_remote_session_cache_resolves_once_and_revoke_invalidates(monkeypatch):
    """The session cache lives in the process: the Dict is queried once, and revoke applies at once."""
    from jumpsight_coach import sessions as S

    class _Store:
        def __init__(self):
            self.d, self.gets = {}, 0

        def put(self, k, v):
            self.d[k] = v

        def get(self, k, default=None):
            self.gets += 1
            return self.d.get(k, default)

        def pop(self, k, default=None):
            return self.d.pop(k, default)

    st = _Store()
    monkeypatch.setattr(S, "_REMOTE", st)
    monkeypatch.setattr(S, "_CACHE", {})
    tok = S.create("guest_cache_test1")
    assert S.resolve(tok) == "guest_cache_test1"
    assert S.resolve(tok) == "guest_cache_test1" and st.gets == 1
    S.revoke(tok)
    assert S.resolve(tok) is None
