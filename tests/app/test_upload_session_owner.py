"""The task owner comes from the server-side session, not from the client header."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


def _app(monkeypatch, tmp_path):
    from jumpsight_app import webapp
    from jumpsight_coach import accounts, sessions

    monkeypatch.setattr(accounts, "STORE", tmp_path / "accounts.json")
    monkeypatch.setattr(accounts, "USERS", tmp_path / "users")
    monkeypatch.setattr(sessions, "DB", tmp_path / "sessions.sqlite3")
    monkeypatch.setattr(sessions, "_REMOTE", None)
    monkeypatch.setattr(webapp, "WORK", tmp_path / "jobs")
    monkeypatch.setattr(webapp, "JOBS", {})
    monkeypatch.setattr(webapp, "_probe_duration", lambda _path: 0.5)
    monkeypatch.setattr(webapp, "_enqueue", lambda *_args: None)
    monkeypatch.setattr(webapp, "_start_live_local", lambda *_args: None)
    return webapp.build_app()


def _client(app, uid: str, forged: str | None = None) -> TestClient:
    from jumpsight_coach import sessions

    headers = {"X-App-User": forged} if forged else None
    client = TestClient(app, base_url="http://localhost", headers=headers)
    client.cookies.set("js_session", sessions.create(uid))
    return client


def test_regular_upload_owner_uses_session_not_forged_header(monkeypatch, tmp_path):
    from jumpsight_app import webapp

    app = _app(monkeypatch, tmp_path)
    owner = _client(app, "session_owner_123", "forged_owner_123")

    response = owner.post("/upload", files={"file": ("clip.mp4", b"synthetic video", "video/mp4")})

    assert response.status_code == 200
    job_id = response.json()["job"]
    assert webapp.JOBS[job_id]["uid"] == "session_owner_123"
    assert owner.get(f"/status/{job_id}").status_code == 200

    other = _client(app, "other_owner_123", "session_owner_123")
    assert other.get(f"/status/{job_id}").status_code == 404

    plain_session = _client(app, "session_owner_123")
    plain = plain_session.post("/upload", files={"file": ("second.mp4", b"synthetic video", "video/mp4")})
    assert plain.status_code == 200
    assert webapp.JOBS[plain.json()["job"]]["uid"] == "session_owner_123"


def test_live_upload_owner_survives_start_part_and_finish(monkeypatch, tmp_path):
    from jumpsight_app import webapp

    app = _app(monkeypatch, tmp_path)
    owner = _client(app, "live_owner_123", "forged_owner_123")

    started = owner.post("/upload_start", headers={"X-App-Ext": "webm"})
    assert started.status_code == 200
    job_id = started.json()["job"]
    parts = json.loads((tmp_path / "jobs" / job_id / "parts.json").read_text())
    assert parts["uid"] == "live_owner_123"
    assert owner.post(f"/upload_part/{job_id}?seq=0", content=b"chunk").status_code == 200

    finished = owner.post(f"/upload_finish/{job_id}", params={"duration_s": 0.5})
    assert finished.status_code == 200
    assert webapp.JOBS[job_id]["uid"] == "live_owner_123"
