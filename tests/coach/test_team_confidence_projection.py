"""The coach receives the confidence of the conclusion, not the inherited confidence of the revolutions."""

from jumpsight_coach import accounts, jobs


def test_history_writer_separates_name_count_and_error_confidence(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "_hp", lambda: tmp_path / "history.json")
    result = {
        "jump": {"name": "Axel", "confidence": "low"},
        "rotation": {
            "revolutions": 2.1,
            "confidence": "medium",
            "usable": True,
            "rotation_count_call": {"count": 2, "confidence": "low", "estimated": True},
        },
        "errors": {"found": [{"code": "step_out", "confidence": "low"}]},
    }
    row = jobs.add_history_jumpsight("controlled", result)
    assert row["name_confidence"] == "low"
    assert row["count_confidence"] == "low"
    assert row["confidence"] == "medium"
    assert row["errors_conf"] == {"step_out": "low"}


def test_team_keeps_each_conclusions_confidence(monkeypatch):
    monkeypatch.setattr(accounts, "_uid", lambda: "coach_fixture")
    monkeypatch.setattr(
        accounts,
        "_load",
        lambda: {"teams": {"coach_fixture": {"students": ["student_fixture"]}}, "profiles": {}, "codes": {}},
    )
    row = {
        "job": "fixture_job",
        "ts": 1790700000,
        "jump": "Axel",
        "name_confidence": "low",
        "count_named": "double",
        "count_estimated": True,
        "count_confidence": "low",
        "errors": ["step_out"],
        "errors_conf": {"step_out": "low"},
    }
    monkeypatch.setattr(accounts, "_history_of", lambda _: [row])
    monkeypatch.setattr(accounts, "coach_focus_of", lambda _: None)
    last = accounts.team()[0]["last"]
    for key in ("name_confidence", "count_confidence", "errors_conf"):
        assert last[key] == row[key]
