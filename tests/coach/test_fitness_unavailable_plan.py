"""An honest plan shows the missing personalization channel."""

import pytest


@pytest.fixture
def setup_plan(monkeypatch, tmp_path):
    from jumpsight_coach import fitness, goal, jobs, session, skills
    from jumpsight_coach.userctx import reset_uid, set_uid

    monkeypatch.setattr(fitness, "PROFILE", tmp_path / "fitness.json")
    monkeypatch.setattr(session, "LOG", tmp_path / "log.json")
    monkeypatch.setattr(goal, "STORE", tmp_path / "goal.json")
    monkeypatch.setattr(jobs, "HISTORY", tmp_path / "history.json")
    monkeypatch.setattr(skills, "profile", lambda *a, **k: {"level": 1})
    monkeypatch.setattr(skills, "load", lambda: {"survey": {"balance": 2, "coach": 2}})
    monkeypatch.setattr(skills, "persistent_gaps", list)
    token = set_uid(None)
    try:
        yield fitness, session
    finally:
        reset_uid(token)


@pytest.mark.parametrize("lang,phrase", [("en", "Fitness test results are unavailable")])
@pytest.mark.parametrize("content", [b"{broken", b'{"raw":{"plank":"oops"}}'])
def test_unavailable_profile_is_visible_without_corrupt_write(setup_plan, lang, phrase, content):
    fitness, session = setup_plan
    baseline = session.build_for_goal("landing_stability", lang=lang)
    fitness.PROFILE.write_bytes(content)
    result = session.build_for_goal("landing_stability", lang=lang)
    notes = " ".join(result["personalisation"])
    assert phrase in notes
    assert result["fitness_state"] == "unavailable"
    assert "flexibility measured fine" not in notes
    assert result["focus"] == baseline["focus"]
    assert [b.get("drill_id") for b in result["blocks"]] == [b.get("drill_id") for b in baseline["blocks"]]
    assert fitness.PROFILE.read_bytes() == content


@pytest.mark.parametrize("lang", ["en"])
def test_missing_profile_is_not_reported_as_outage(setup_plan, lang):
    _, session = setup_plan
    result = session.build_for_goal("landing_stability", lang=lang)
    assert result["fitness_state"] == "available"
    notes = " ".join(result["personalisation"])
    assert "Fitness test results are unavailable" not in notes


def test_unexpected_fitness_failure_is_not_reported_as_available_plan(setup_plan, monkeypatch):
    fitness, session = setup_plan

    def broken(*args, **kwargs):
        raise RuntimeError("unexpected fitness bug")

    monkeypatch.setattr(fitness, "gates", broken)
    with pytest.raises(RuntimeError, match="unexpected fitness bug"):
        session.build_for_goal("landing_stability", lang="en")


def test_invalid_flex_drill_level_cannot_skip_safety_filter(setup_plan, monkeypatch):
    fitness, session = setup_plan
    fitness.save({"sit_reach": "-12"})
    drills, causes = session.load_kb()
    # the shipped KB has no flexibility drill, so the test supplies a synthetic one
    selected = {**drills[0], "id": "synthetic_flex", "targets": ["spin_flexibility"], "kind": "off_ice"}
    monkeypatch.setattr(session, "load_kb", lambda: ([{**selected, "level": "invalid"}], causes))
    with pytest.raises(ValueError):
        session.build_for_goal("landing_stability", lang="en")
