"""One-time transfer of a guest profile between two sessions."""

from fastapi.testclient import TestClient


def test_transfer_is_one_time_and_does_not_use_profile_code(monkeypatch, tmp_path):
    from jumpsight_coach import accounts, sessions
    from jumpsight_coach.api import app

    monkeypatch.setattr(accounts, "STORE", tmp_path / "accounts.json")
    monkeypatch.setattr(accounts, "USERS", tmp_path / "users")
    monkeypatch.setattr(sessions, "DB", tmp_path / "sessions.sqlite3")
    monkeypatch.setattr(sessions, "_REMOTE", None)
    source = TestClient(app, base_url="http://localhost")
    uid = source.post("/auth/guest").json()["uid"]
    token = source.post("/auth/transfer").json()["token"]
    target = TestClient(app, base_url="http://localhost")
    assert target.post("/claim", json={"token": token}).json()["uid"] == uid
    assert target.get("/me").json()["uid"] == uid
    assert target.post("/claim", json={"token": token}).status_code == 404
