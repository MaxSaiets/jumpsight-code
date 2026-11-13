"""A forecast does not change the history of a parallel request or the external context."""

import threading

import pytest


def test_forecast_is_invisible_to_parallel_history_reader(monkeypatch, tmp_path):
    from jumpsight_coach import session, skills

    monkeypatch.setattr(session, "_lp", lambda: tmp_path / "absent.json")
    monkeypatch.setattr(skills, "load", lambda: {"survey": {"freq": 3}})
    entered, release = threading.Event(), threading.Event()
    calls, errors = [], []

    def build(*args, **kwargs):
        calls.append(session._log())
        if len(calls) == 2:
            entered.set()
            assert release.wait(5)
        return {"focus": "rotation", "blocks": [{"drill_id": "forecast_drill"}]}

    def forecast():
        try:
            session.plan(object(), days=2)
        except BaseException as exc:
            errors.append(exc)

    monkeypatch.setattr(session, "build", build)
    worker = threading.Thread(target=forecast)
    worker.start()
    try:
        assert entered.wait(5)
        assert session._log() == []
        assert session.history() == []
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()
    assert not errors
    assert calls[0] == []
    assert calls[1][0]["simulated"] is True
    assert session._log() == []


def test_forecast_cleans_up_after_build_failure(monkeypatch, tmp_path):
    from jumpsight_coach import session, skills

    monkeypatch.setattr(session, "_lp", lambda: tmp_path / "absent.json")
    monkeypatch.setattr(skills, "load", lambda: {"survey": {"freq": 3}})
    calls = []

    def build(*args, **kwargs):
        calls.append(session._log())
        if len(calls) == 2:
            raise ValueError("test failure")
        return {"blocks": [{"drill_id": "forecast_drill"}]}

    monkeypatch.setattr(session, "build", build)
    with pytest.raises(ValueError, match="test failure"):
        session.plan(object(), days=2)
    assert session._log() == []
