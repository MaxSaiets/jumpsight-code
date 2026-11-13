"""Real HTTP distinguishes an unavailable profile from a programmatic failure."""

import pytest


@pytest.mark.parametrize("state,status", [("missing", 200), ("broken", 200), ("unexpected", 500)])
def test_authenticated_plan_fitness_boundary(monkeypatch, tmp_path, state, status):
    from fastapi.testclient import TestClient

    from jumpsight_coach import accounts, fitness, goal, jobs, session, sessions, skills
    from jumpsight_coach.api import app

    monkeypatch.setattr(accounts, "STORE", tmp_path / "accounts.json")
    monkeypatch.setattr(accounts, "USERS", tmp_path / "users")
    monkeypatch.setattr(sessions, "DB", tmp_path / "sessions.sqlite3")
    monkeypatch.setattr(fitness, "PROFILE", tmp_path / "fitness.json")
    monkeypatch.setattr(session, "LOG", tmp_path / "log.json")
    monkeypatch.setattr(goal, "STORE", tmp_path / "goal.json")
    monkeypatch.setattr(jobs, "HISTORY", tmp_path / "history.json")
    monkeypatch.setattr(skills, "profile", lambda *a, **k: {"level": 1})
    monkeypatch.setattr(skills, "load", lambda: {"survey": {"balance": 2, "coach": 2}})
    monkeypatch.setattr(skills, "persistent_gaps", list)
    uid = "fitness_http_123"
    path = accounts.USERS / uid / "fitness.json"
    if state == "broken":
        path.parent.mkdir(parents=True)
        path.write_bytes(b"{broken")
    if state == "unexpected":

        def fail(*args, **kwargs):
            raise RuntimeError("private internal failure at " + str(path))

        monkeypatch.setattr(fitness, "gates", fail)
    client = TestClient(app, base_url="http://localhost", raise_server_exceptions=False)
    client.cookies.set("js_session", sessions.create(uid))
    response = client.get("/today?goal=landing_stability&lang=en")
    assert response.status_code == status
    assert str(path) not in response.text
    assert "private internal failure" not in response.text
    if status == 200:
        assert response.json()["fitness_state"] == ("unavailable" if state == "broken" else "available")
    else:
        assert "fitness_state" not in response.text
    if state == "broken":
        assert path.read_bytes() == b"{broken"
