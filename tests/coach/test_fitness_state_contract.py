"""Damage to the profile does not allow silently erasing old evidence."""

import json

import pytest


@pytest.fixture
def profile(monkeypatch, tmp_path):
    from jumpsight_coach import fitness
    from jumpsight_coach.userctx import reset_uid, set_uid

    monkeypatch.setattr(fitness, "PROFILE", tmp_path / "fitness.json")
    token = set_uid(None)
    try:
        yield fitness
    finally:
        reset_uid(token)


@pytest.mark.parametrize(
    "content",
    [
        b"{broken",
        b"null",
        b"[]",
        b"\xff",
        b'{"raw": []}',
        b'{"raw":{"plank":"NaN"}}',
        b'{"raw":{"plank":"oops"}}',
        b'{"groups": []}',
        b'{"groups":{"endurance":{"score":"NaN"}}}',
        json.dumps({"groups": {"endurance": {"score": 10**400}}}).encode(),
    ],
)
def test_broken_profile_is_not_overwritten_or_returned_as_valid(profile, content):
    profile.PROFILE.write_bytes(content)
    with pytest.raises(profile.FitnessStateUnavailable):
        profile.load()
    with pytest.raises(profile.FitnessStateUnavailable):
        profile.save({"cmj_reach": "32"})
    assert profile.PROFILE.read_bytes() == content


def test_missing_profile_and_grade_less_legacy_remain_usable(profile):
    assert profile.load() == {}
    profile.save({"plank": "60"})
    data = json.loads(profile.PROFILE.read_text(encoding="utf-8"))
    del data["groups"]["endurance"]["grade"]
    profile.PROFILE.write_text(json.dumps(data), encoding="utf-8")
    assert profile.load()["groups"]["endurance"]["grade"] == "B"
    assert profile.save({"cmj_reach": "32"})["raw"] == {"plank": "60", "cmj_reach": "32"}


def test_http_get_and_post_report503_without_destroying_profile(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from jumpsight_coach import accounts, fitness, sessions
    from jumpsight_coach.api import app

    monkeypatch.setattr(accounts, "STORE", tmp_path / "accounts.json")
    monkeypatch.setattr(accounts, "USERS", tmp_path / "users")
    monkeypatch.setattr(fitness, "PROFILE", tmp_path / "fitness.json")
    monkeypatch.setattr(sessions, "DB", tmp_path / "sessions.sqlite3")
    client = TestClient(app, base_url="http://localhost", raise_server_exceptions=False)
    client.cookies.set("js_session", sessions.create("fitness_state_123"))
    path = tmp_path / "users" / "fitness_state_123" / "fitness.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{broken")
    for response in [
        client.get("/fitness"),
        client.post("/fitness", json={"owner_uid": "fitness_state_123", "results": {"plank": "60"}}),
    ]:
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "30"
        assert path.read_bytes() == b"{broken"
