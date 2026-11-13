"""A draft from an old tab does not write fitness after the owner cookie changes."""

from fastapi.testclient import TestClient


def client_for(monkeypatch, tmp_path, uid):
    from jumpsight_coach import accounts, fitness, sessions
    from jumpsight_coach.api import app

    monkeypatch.setattr(accounts, "STORE", tmp_path / "accounts.json")
    monkeypatch.setattr(accounts, "USERS", tmp_path / "users")
    monkeypatch.setattr(sessions, "DB", tmp_path / "sessions.sqlite3")
    monkeypatch.setattr(fitness, "PROFILE", tmp_path / "fitness.json")
    client = TestClient(app, base_url="http://localhost")
    client.cookies.set("js_session", sessions.create(uid))
    return client


def test_stale_draft_owner_is_rejected_before_any_write(monkeypatch, tmp_path):
    from jumpsight_coach import fitness

    client = client_for(monkeypatch, tmp_path, "fitness_other_123")
    calls = []
    monkeypatch.setattr(fitness, "save", lambda values: calls.append(values))
    response = client.post("/fitness", json={"owner_uid": "fitness_owner_123", "results": {"cmj_reach": "32"}})
    assert response.status_code == 409
    assert calls == []


def test_current_owner_receives_ack_and_only_own_profile_changes(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path, "fitness_owner_123")
    response = client.post("/fitness", json={"owner_uid": "fitness_owner_123", "results": {"cmj_reach": "32"}})
    assert response.status_code == 200
    assert response.json()["owner_uid"] == "fitness_owner_123"
    assert client.get("/fitness").json()["owner_uid"] == "fitness_owner_123"
    assert response.json()["profile"]["raw"]["cmj_reach"] == "32"
    assert (tmp_path / "users" / "fitness_owner_123" / "fitness.json").exists()
    assert not (tmp_path / "fitness.json").exists()


def test_legacy_payload_remains_compatible(monkeypatch, tmp_path):
    client = client_for(monkeypatch, tmp_path, "fitness_legacy_123")
    assert client.post("/fitness", json={"results": {"cmj_reach": "31"}}).status_code == 200
