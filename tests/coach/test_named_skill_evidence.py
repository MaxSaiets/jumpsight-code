"""A pair of names does not prove mastery of one specific jump."""

import pytest

from jumpsight_coach import jobs, skills


@pytest.mark.parametrize(
    "evidence",
    [
        {"name_is_family": True, "name_display": "Lutz / Flip"},
        {"name_display": "Lutz / Flip"},
        {"name_uncertain": True},
        {"name_is_family": "true"},
        {"jump": None},
    ],
)
def test_pair_does_not_create_named_skill_or_trend(monkeypatch, evidence):
    rows = [
        {
            "stem": f"clip{i}",
            "ts": 100000 + i * 86400,
            "jump": "Lutz",
            "engine": "jumpsight",
            "revolutions": 1.53,
            "rev_usable": True,
            "confidence": "high",
            "band": 0.1,
            "clean": True,
            "errors": [],
            **evidence,
        }
        for i in range(3)
    ]
    monkeypatch.setattr(jobs, "history", lambda: rows)
    monkeypatch.setattr(jobs, "_load_hist", lambda: rows)
    assert skills.skill_map()["jumps"] == []
    assert jobs.progress()["trend"] == {}
    # An honest physical measurement remains usable for the general assessment.
    assert skills.assess_from_history()["measured_level"] == 2


def test_single_name_keeps_skill_and_trend(monkeypatch):
    rows = [
        {
            "stem": f"clip{i}",
            "ts": 100000 + i * 86400,
            "jump": "Lutz",
            "engine": "jumpsight",
            "revolutions": 1.53,
            "rev_usable": True,
            "confidence": "high",
            "band": 0.1,
            "clean": True,
            "errors": [],
            "name_display": "Lutz",
            "name_is_family": False,
        }
        for i in range(3)
    ]
    monkeypatch.setattr(jobs, "history", lambda: rows)
    monkeypatch.setattr(jobs, "_load_hist", lambda: rows)
    assert skills.skill_map()["jumps"][0]["jump"] == "Lutz"
    assert "Lutz" in jobs.progress()["trend"]


def test_journal_preserves_pair(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "_hp", lambda: tmp_path / "history.json")
    result = {
        "jump": {
            "name": "Lutz",
            "name_display": "Lutz / Flip",
            "name_is_family": True,
            "confidence": "low",
            "alternatives": ["Lutz", "Flip"],
        },
        "rotation": {"revolutions": 1.53, "confidence": "medium", "usable": True, "rotation_count_call": {"count": 2}},
        "phases": {},
        "errors": {"found": [], "checked_and_clean": ["fall"]},
    }
    jobs.add_history_jumpsight("pair_clip", result)
    row = jobs.history()[0]
    assert row.get("name_display") == "Lutz / Flip"
    assert row.get("name_is_family") is True
