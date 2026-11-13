"""An assessed endurance does not confirm an unmeasured flexibility."""

import pytest


@pytest.fixture
def plan(monkeypatch, tmp_path):
    from jumpsight_coach import fitness, goal, jobs, session, skills
    from jumpsight_coach.userctx import reset_uid, set_uid

    monkeypatch.setattr(fitness, "PROFILE", tmp_path / "fitness.json")
    monkeypatch.setattr(session, "LOG", tmp_path / "log.json")
    monkeypatch.setattr(goal, "STORE", tmp_path / "goal.json")
    monkeypatch.setattr(jobs, "HISTORY", tmp_path / "history.json")
    monkeypatch.setattr(skills, "profile", lambda *a, **k: {"level": 1})
    monkeypatch.setattr(skills, "load", lambda: {"survey": {"balance": 2, "coach": 2}})
    monkeypatch.setattr(skills, "persistent_gaps", list)
    selected_goals = []
    original_pick = session.pick_drills

    def capture(goals, *args, **kwargs):
        selected_goals.extend(goals)
        return original_pick(goals, *args, **kwargs)

    monkeypatch.setattr(session, "pick_drills", capture)
    token = set_uid(None)

    def make(raw, lang):
        fitness.save(raw)
        selected_goals.clear()
        result = session.build_for_goal("landing_stability", lang=lang)
        return result, set(selected_goals), fitness.gates(lang)

    try:
        yield make
    finally:
        reset_uid(token)


@pytest.mark.parametrize("raw", [{}, {"plank": "120"}, {"cmj_reach": "40"}, {"plank": "120", "sit_reach": "99"}])
@pytest.mark.parametrize("lang", ["en"])
def test_unknown_flexibility_does_not_open_measured_flex_goals(plan, raw, lang):
    result, goals, gates = plan(raw, lang)
    notes = " ".join(result["personalisation"])
    assert not ({"spin_flexibility", "spin_position"} & goals), notes
    assert "flexibility measured fine" not in notes
    assert "flexibility" not in gates["measured_groups"]


@pytest.mark.parametrize("value,weak", [("-12", True), ("22", False)])
@pytest.mark.parametrize("lang", ["en"])
def test_rated_flexibility_keeps_existing_goal_and_limit(plan, value, weak, lang):
    result, goals, gates = plan({"sit_reach": value}, lang)
    assert "flexibility" in gates["measured_groups"]
    assert "spin_flexibility" in goals
    assert ("spin_position" in goals) is not weak
    assert gates["limit_flex"] is weak


def test_balance_only_keeps_its_support_goal_without_opening_flexibility(plan):
    result, goals, gates = plan({"balance_s": "6"}, "en")
    assert "balance_control" in goals
    assert not ({"spin_flexibility", "spin_position"} & goals)
    assert gates["measured_groups"] == ["balance"]
