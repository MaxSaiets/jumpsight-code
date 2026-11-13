"""An invalid physical result is not grade C and is not written partially."""

import math

import pytest


@pytest.fixture
def fitness_profile(monkeypatch, tmp_path):
    from jumpsight_coach import fitness
    from jumpsight_coach.userctx import reset_uid, set_uid

    monkeypatch.setattr(fitness, "PROFILE", tmp_path / "fitness.json")
    token = set_uid(None)
    try:
        yield fitness
    finally:
        reset_uid(token)


@pytest.mark.parametrize(
    "invalid",
    ["oops", "NaN", "Infinity", "-Infinity", float("nan"), float("inf"), -float("inf"), True, False, [], {}, " "],
)
def test_invalid_measurement_refused_before_write(fitness_profile, invalid):
    fitness_profile.save({"cmj_reach": "32", "plank": "60"})
    before = fitness_profile.PROFILE.read_bytes()
    with pytest.raises(ValueError):
        fitness_profile.save({"cmj_reach": "48", "plank": invalid})
    assert fitness_profile.PROFILE.read_bytes() == before


def test_unknown_id_cannot_commit_other_valid_fields(fitness_profile):
    with pytest.raises(ValueError):
        fitness_profile.save({"cmj_reach": "32", "invented_test": "10"})
    assert not fitness_profile.PROFILE.exists()


def test_valid_numeric_values_partial_merge_and_blank_compatibility(fitness_profile):
    fitness_profile.save({"cmj_reach": "32", "sit_reach": "-3.5", "split_gap": 0})
    result = fitness_profile.save({"plank": 60.5, "cmj_reach": None, "sit_reach": ""})
    assert result["raw"] == {"cmj_reach": "32", "sit_reach": "-3.5", "split_gap": 0, "plank": 60.5}
    assert result["groups"]["endurance"]["grade"] == "B"
    assert all(math.isfinite(group["score"]) for group in result["groups"].values())


def test_http422_keeps_profile_and_owner_guard_precedes_validation(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from jumpsight_coach import accounts, fitness, sessions
    from jumpsight_coach.api import app

    monkeypatch.setattr(accounts, "STORE", tmp_path / "accounts.json")
    monkeypatch.setattr(accounts, "USERS", tmp_path / "users")
    monkeypatch.setattr(fitness, "PROFILE", tmp_path / "fitness.json")
    monkeypatch.setattr(sessions, "DB", tmp_path / "sessions.sqlite3")
    client = TestClient(app, base_url="http://localhost")
    client.cookies.set("js_session", sessions.create("fitness_input_123"))
    good = {"owner_uid": "fitness_input_123", "results": {"cmj_reach": "32"}}
    assert client.post("/fitness", json=good).status_code == 200
    path = tmp_path / "users" / "fitness_input_123" / "fitness.json"
    before = path.read_bytes()
    for values in [{"cmj_reach": "48", "plank": "NaN"}, {"cmj_reach": "48", "invented_test": "3"}]:
        assert client.post("/fitness", json={**good, "results": values}).status_code == 422
        assert path.read_bytes() == before
    assert client.post("/fitness", json={"owner_uid": "other_uid_123", "results": {"plank": "NaN"}}).status_code == 409

    # Do not confuse a state error with a wrong input by the person.
    def broken_save(_values):
        raise ValueError("invalid stored state")

    monkeypatch.setattr(fitness, "save", broken_save)
    broken_client = TestClient(app, base_url="http://localhost", raise_server_exceptions=False)
    broken_client.cookies.update(client.cookies)
    assert broken_client.post("/fitness", json=good).status_code == 500
    broken_client.close()
