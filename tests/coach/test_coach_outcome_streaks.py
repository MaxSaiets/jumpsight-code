"""Quality streaks: a contradictory legacy record does not become mastery."""

import pytest


def entry(*outcomes):
    return {"blocks": [{"drill_id": "a", "outcome": outcome} for outcome in outcomes]}


@pytest.mark.parametrize(
    "outcomes,expected",
    [
        (("ok", "fail"), (0, 1)),
        (("fail", "ok"), (0, 1)),
        (("ok", "partial"), (0, 0)),
        (("partial", "ok"), (0, 0)),
        (("ok", "done"), (0, 0)),
        (("done", "ok"), (0, 0)),
        (("ok", "ok", "ok"), (1, 0)),
        (("fail", "fail"), (0, 1)),
    ],
)
def test_legacy_duplicates_are_conservative_and_order_independent(outcomes, expected):
    from jumpsight_coach.session import _outcome_streaks

    success, failure = _outcome_streaks([entry(*outcomes)])
    assert (success.get("a", 0), failure.get("a", 0)) == expected


@pytest.mark.parametrize(
    "rows,expected",
    [
        ([entry("ok"), entry("done"), entry("ok"), entry("ok")], (2, 0)),
        ([entry("fail"), entry("done"), entry("fail")], (0, 1)),
        ([entry("ok"), {"blocks": [{"drill_id": "other", "outcome": "fail"}]}, entry("ok")], (2, 0)),
        ([entry("ok"), entry("unknown"), entry("ok")], (1, 0)),
        ([entry("ok"), {"blocks": [{"drill_id": "a"}]}, entry("ok")], (1, 0)),
    ],
)
def test_unknown_results_break_evidence_but_other_drills_do_not(rows, expected):
    from jumpsight_coach.session import _outcome_streaks

    success, failure = _outcome_streaks(rows)
    assert (success.get("a", 0), failure.get("a", 0)) == expected


def test_repeated_session_id_is_one_workout():
    from jumpsight_coach.session import _outcome_streaks

    row = {**entry("ok"), "session_id": "same_workout"}
    success, failure = _outcome_streaks([row, row, row])
    assert success["a"] == 1 and failure["a"] == 0


@pytest.mark.parametrize("outcomes", [("ok", "fail"), ("fail", "ok")])
def test_conflicting_session_retries_are_aggregated(outcomes):
    from jumpsight_coach.session import _outcome_streaks

    success, failure = _outcome_streaks([{**entry(outcome), "session_id": "same"} for outcome in outcomes])
    assert success["a"] == 0 and failure["a"] == 1


def test_conflicting_history_does_not_unlock_harder_plan(monkeypatch, tmp_path):
    import json

    from jumpsight_coach import fitness, goal, session, skills

    monkeypatch.setattr(session, "LOG", tmp_path / "sessions.json")
    monkeypatch.setattr(skills, "PROFILE", tmp_path / "skills.json")
    monkeypatch.setattr(fitness, "PROFILE", tmp_path / "fitness.json")
    monkeypatch.setattr(goal, "STORE", tmp_path / "goal.json")
    monkeypatch.setattr(skills, "persistent_gaps", list)
    rows = [entry("ok", "fail") for _ in range(3)]
    for row in rows:
        for block in row["blocks"]:
            block["drill_id"] = "hv_consec_half_rotations"
    session.LOG.write_text(json.dumps(rows), encoding="utf-8")
    plan = session.build_for_goal("basics_rotation")
    assert not any("self-reported" in note for note in plan["personalisation"])
