import pytest

from jumpsight_coach import jobs, skills


@pytest.mark.parametrize(
    "found,clean,uncertain,state,outcome",
    [
        ([], ["fall"], [{"code": "step_out"}], "partial", None),
        ([], [], [{"code": "fall"}], "unavailable", None),
        ([{"code": "fall"}], [], [{"code": "step_out"}], "assessed", False),
        ([], ["fall", "step_out"], [], "assessed", True),
    ],
)
def test_execution_history_states(monkeypatch, tmp_path, found, clean, uncertain, state, outcome):
    monkeypatch.setattr(jobs, "_hp", lambda: tmp_path / "history.json")
    result = {
        "jump": {"name": "Salchow", "name_display": "Salchow", "confidence": "medium"},
        "rotation": {"revolutions": 1.53, "confidence": "medium", "usable": True, "rotation_count_call": {"count": 2}},
        "phases": {},
        "errors": {"found": found, "checked_and_clean": clean, "uncertain": uncertain},
    }
    row = jobs.add_history_jumpsight("execution_clip", result)
    assert row.get("execution_state") == state
    assert row.get("errors_uncertain") == uncertain
    assert jobs.execution_clean_state(row) is outcome


def test_unknown_execution_is_not_clean_or_dirty(monkeypatch):
    rows = [
        {
            "stem": str(i),
            "ts": 100 + i,
            "jump": "Salchow",
            "engine": "jumpsight",
            "revolutions": 1.53,
            "rev_usable": True,
            "confidence": "high",
            "band": 0.1,
            "execution_state": state,
            "clean": clean,
            "errors": [],
        }
        for i, (state, clean) in enumerate(
            [("assessed", True), ("assessed", False), ("partial", True), ("unavailable", False)]
        )
    ]
    monkeypatch.setattr(jobs, "_load_hist", lambda: rows)
    monkeypatch.setattr(jobs, "history", lambda: list(reversed(rows)))
    pr = jobs.progress()
    assert pr["total"] == 4
    assert pr["clean_pct"] == 50
    assert pr["clean_assessed_total"] == 2
    assert pr["streak"] == 0
    assert skills.skill_map()["jumps"][0]["clean_pct"] == 50
    assert skills.assess_from_history()["clean_pct"] == 50


def test_no_execution_evidence_has_no_percentage(monkeypatch):
    rows = [
        {
            "stem": "a",
            "ts": 100,
            "jump": "Salchow",
            "engine": "jumpsight",
            "revolutions": 1.53,
            "rev_usable": True,
            "confidence": "high",
            "band": 0.1,
            "execution_state": "partial",
            "clean": True,
        }
    ]
    monkeypatch.setattr(jobs, "_load_hist", lambda: rows)
    monkeypatch.setattr(jobs, "history", lambda: rows)
    assert jobs.progress()["clean_pct"] is None
    assert skills.skill_map()["jumps"][0]["clean_pct"] is None


def test_goal_without_execution_evidence_is_unmeasured(monkeypatch):
    from jumpsight_coach import goal

    monkeypatch.setattr(goal, "load", lambda: {"jump": "Salchow", "target_pct": 80})
    monkeypatch.setattr(
        skills,
        "skill_map",
        lambda lang: {
            "jumps": [{"jump": "Salchow", "clean_pct": None, "attempts": 8, "clean_assessed_total": 0, "clean": 0}]
        },
    )
    result = goal.with_progress()
    assert result["current_pct"] is None
    assert result["progress_pct"] is None
    assert result["clean_assessed_total"] == 0
    assert result["attempts"] == 8
