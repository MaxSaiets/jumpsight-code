"""A skill assessment does not raise the level through unsuitable or selected attempts."""

from jumpsight_coach import jobs, skills


def test_best_three_attempts_do_not_hide_typical_performance(monkeypatch):
    rows = [
        {"revolutions": rev, "rev_usable": True, "confidence": "high", "clean": False}
        for rev in [3.0, 3.0, 3.0, 0.8, 0.8, 0.8, 0.8]
    ]
    monkeypatch.setattr(jobs, "history", lambda: rows)
    result = skills.assess_from_history()
    assert result["measured_level"] == 1
    assert result["consistent_revolutions"] == 0.8
    assert result["best_revolutions"] == 3.0


def test_refused_measurements_never_promote_level(monkeypatch):
    rows = [
        {"revolutions": 3.0, "rev_usable": False, "confidence": "high"},
        {"revolutions": float("nan"), "rev_usable": True, "confidence": "high"},
        {"revolutions": float("inf"), "rev_usable": True, "confidence": "high"},
        {"revolutions": -1, "rev_usable": True, "confidence": "high"},
    ]
    monkeypatch.setattr(jobs, "history", lambda: rows)
    result = skills.assess_from_history()
    assert result["measured_level"] is None
    assert result["n_videos"] == 0
