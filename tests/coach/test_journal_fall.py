"""Coach journal: an aborted attempt with measured errors is an attempt, not a 'window without a count'.

A real clip: a Lutz, a fall plus a hand on the ice, flight 0.67 s; the width channel gave no revolutions in flight. The entry must not go to not_measured, because the fall would vanish from the journal, from the clean share and from the skills profile."""

import tempfile
from pathlib import Path

import jumpsight_coach.jobs as J


def _with_tmp_history(fn):
    real = J.HISTORY
    tmp = Path(tempfile.mkdtemp(prefix="jf_"))
    J.HISTORY = tmp / "hist.json"
    try:
        return fn()
    finally:
        J.HISTORY = real


def _result(found, revolutions, count):
    return {
        "rotation": {
            "revolutions": revolutions,
            "confidence": "low",
            "measured": revolutions is not None,
            "usable": False,
            "rotation_count_call": {"count": count, "name": None},
        },
        "phases": {"air_time_s": 0.67, "jump_height_m": 0.55},
        "jump": {"name": "Lutz", "name_display": "Lutz", "confidence": "medium", "alternatives": []},
        # The fall/interval fixture for the clean share contains no unconfirmed
        # blade check. The 2D proxy is covered separately by cache tests.
        "errors": {"found": found, "checked_and_clean": ["step_out"]},
    }


def test_fall_without_revolutions_is_a_measured_attempt():
    def run():
        rec = J.add_history_jumpsight(
            "clip_att2", _result([{"code": "fall"}, {"code": "hand_down"}], None, None), job_id="j1"
        )
        assert rec["outcome"] == "measured"
        assert rec["jump"] == "Lutz"
        assert rec["errors"] == ["fall", "hand_down"]
        assert rec["clean"] is False
        assert rec["revolutions"] is None
        assert rec["air_time_s"] == 0.67
        pr = J.progress()
        assert pr["total"] == 1 and pr["clean_pct"] == 0
        assert pr["trend"] == {}  # without revolutions does not enter the trend

    _with_tmp_history(run)


def test_fragment_without_errors_stays_not_measured():
    def run():
        rec = J.add_history_jumpsight("clip_att9", _result([], 0.07, None), job_id="j2")
        assert rec["outcome"] == "not_measured"
        assert J.progress()["total"] == 0

    _with_tmp_history(run)


def test_clean_share_error_is_not_zero_on_three_of_three():
    def run():
        for i in range(3):
            J.add_history_jumpsight(f"c_att{i}", _result([], 1.5, 2), job_id=f"j{i}")
        pr = J.progress()
        assert pr["clean_pct"] == 100
        assert pr["clean_pct_se"] > 10  # Agresti–Coull: 3/3 → ≈17 pp.

    _with_tmp_history(run)


def test_entry_fragment_with_fall_is_not_a_jump_in_the_journal():
    """A spin without a jump, a flight < 0.2 s, does not pass the check. The screen says 'entry fragment', so the journal must not write 'Fall'."""

    def run():
        res = _result([{"code": "fall"}], None, None)
        res["phases"] = {"air_time_s": None, "air_time_s_raw": 0.17, "jump_height_m": None}
        rec = J.add_history_jumpsight("spin_att1", res, job_id="j3")
        assert rec["outcome"] == "not_measured"
        assert J.progress()["total"] == 0

    _with_tmp_history(run)
