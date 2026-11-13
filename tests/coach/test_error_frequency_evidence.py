"""An unperformed check of an error is not its absence."""

import pytest

from jumpsight_coach import jobs, skills


def rows_for(states):
    return [
        {
            "stem": str(i),
            "jump": "Salchow",
            "ts": i,
            "errors": ["step_out"] if state == "found" else [],
            "errors_checked_clean": ["step_out"] if state == "clean" else [],
            "errors_uncertain": [{"code": "step_out"}] if state == "unknown" else [],
        }
        for i, state in enumerate(states)
    ]


def test_gap_uses_checked_attempts_not_all_videos(monkeypatch):
    monkeypatch.setattr(jobs, "history", lambda: rows_for(["found"] * 2 + ["clean"] + ["unknown"] * 7))
    row = skills.skill_map()["jumps"][0]
    assert row["attempts"] == 10
    assert row["gaps"][0] == {"code": "step_out", "in_attempts": 2, "of": 3, "rate": 0.67, "verdict": "not_owned"}
    assert skills.persistent_gaps() == ["step_out"]
    assert skills.persistent_gaps(min_attempts=4) == []


def test_unknowns_cannot_supply_minimum_sample(monkeypatch):
    monkeypatch.setattr(jobs, "history", lambda: rows_for(["found"] * 2 + ["unknown"] * 8))
    assert skills.skill_map()["jumps"][0]["gaps"][0]["verdict"] == "too_few"
    assert skills.persistent_gaps() == []


@pytest.mark.parametrize(
    "record,expected",
    [
        (
            {"errors": ["step_out"], "errors_checked_clean": ["step_out"], "errors_uncertain": [{"code": "step_out"}]},
            True,
        ),
        ({"errors_checked_clean": ["step_out"], "errors_uncertain": [{"code": "step_out"}]}, None),
        ({"errors_checked_clean": ["fall"]}, None),
        ({"clean": True, "checks_run": 4}, None),
        ({"errors": ["step_out"]}, True),
        ({"errors_checked_clean": ["step_out"]}, False),
        ({"errors": ["step_out"], "outcome": "not_measured"}, None),
    ],
)
def test_per_code_evidence_precedence_and_legacy(record, expected):
    assert jobs.error_check_state(record, "step_out") is expected


def test_writer_preserves_negative_codes(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "_hp", lambda: tmp_path / "history.json")
    result = {
        "jump": {"name": "Salchow", "confidence": "medium"},
        "rotation": {"revolutions": 1.53, "usable": True, "rotation_count_call": {"count": 2}},
        "errors": {"found": [], "checked_and_clean": ["fall", "step_out"], "uncertain": [{"code": "hand_down"}]},
    }
    row = jobs.add_history_jumpsight("checks", result)
    assert row.get("errors_checked_clean") == ["fall", "step_out"]
    assert jobs.error_check_state(jobs.history()[0], "step_out") is False
