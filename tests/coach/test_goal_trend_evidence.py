"""A session between unmeasured videos does not prove improvement of the goal."""

import time

import pytest

from jumpsight_coach import jobs


@pytest.mark.parametrize(
    "record,codes,all_codes,expected",
    [
        ({"errors_checked_clean": ["touch_down"]}, {"touch_down", "hand_down"}, True, None),
        ({"errors_checked_clean": ["touch_down", "hand_down"]}, {"touch_down", "hand_down"}, True, False),
        ({"errors": ["touch_down"]}, {"touch_down", "hand_down"}, True, True),
        ({"errors_checked_clean": ["tilted_axis"]}, {"tilted_axis", "axis_lean_in_air"}, False, False),
        ({"clean": True}, {"fall"}, False, None),
    ],
)
def test_goal_channel_evidence(record, codes, all_codes, expected):
    assert jobs.goal_check_state(record, codes, require_all=all_codes) is expected


@pytest.mark.parametrize(
    "scenario,trend,reason,n_recent",
    [
        ("unknown", "n/a", "too_few", 0),
        ("one", "n/a", "too_few", 1),
        ("checked", "better", None, 3),
        ("no_session", "n/a", "no_session_between", 3),
        ("other_session", "n/a", "no_session_between", 3),
        ("mixed", "n/a", "mixed_engines", 3),
    ],
)
def test_goal_trend_uses_its_own_assessed_windows(monkeypatch, scenario, trend, reason, n_recent):
    from jumpsight_coach import api, core, session

    now = time.time()
    old = [{"ts": now - 10 * 86400 + i, "errors": ["touch_down"], "engine": "jumpsight"} for i in range(3)]
    recent = [
        {
            "ts": now - 86400 + i,
            "errors": [],
            "engine": "jumpsight",
            "errors_checked_clean": ["touch_down", "hand_down"]
            if scenario not in ("unknown", "one") or scenario == "one" and i == 0
            else [],
        }
        for i in range(3)
    ]
    if scenario == "mixed":
        old[0]["engine"] = "full"
    sessions = [] if scenario == "no_session" else [{"ts": now - 7 * 86400, "focus": "landing_stability"}]
    if scenario == "other_session":
        sessions[0]["focus"] = "axis_tilt"
    monkeypatch.setattr(jobs, "_load_hist", lambda: old + recent)
    monkeypatch.setattr(session, "_log", lambda: sessions)
    monkeypatch.setattr(core, "load_kb", lambda: ({}, []))
    monkeypatch.setattr(session, "goal_label", lambda goal, lang="en": goal)
    result = api.get_progress_goals()
    row = next(g for g in result["goals"] if g["goal"] == "landing_stability")
    assert row["n_recent"] == n_recent
    assert row["n_earlier"] == 3
    assert row["trend"] == trend
    assert row["trend_reason"] == reason
    assert row["err_rate_recent"] == (None if n_recent == 0 else 0)
