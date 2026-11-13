"""Case comparison works on what is MEASURED.

`p5_case` (which feeds /recommend) must not require the reference's revolution confidence above 'low' or decimal revolutions in both attempts. The honesty rules withhold this number on most clips (in the corpus 103 of 105 analyses have confidence low), so requiring it would collect no references and always answer 'not enough measurements for a case comparison', although flight time is measured in 74 analyses.
"""

from __future__ import annotations

import json
from pathlib import Path


def _result(air: float, *, rev=None, usable=False, count=2, errors=()) -> dict:
    return {
        "engine": "jumpsight",
        "jump": {"name": "Axel", "confidence": "medium"},
        "phases": {"air_time_s": air, "jump_height_m": 0.45, "takeoff": 10, "landing": 30},
        "rotation": {
            "revolutions": rev,
            "usable": usable,
            "confidence": "low",
            "reason": "REV_BAND_WIDER_THAN_HALF_TURN",
            "rotation_count_call": {"count": count},
        },
        "errors": {
            "found": [{"code": c, "measured": ""} for c in errors],
            "checked_and_clean": ["fall"],
            "uncertain": [],
        },
    }


def _corpus(tmp_path: Path, airs) -> Path:
    d = tmp_path / "corpus"
    d.mkdir()
    for i, a in enumerate(airs):
        (d / f"ref{i}_result.json").write_text(json.dumps(_result(a)), encoding="utf-8")
    return d


def test_low_confidence_no_longer_kills_the_reference_pool(tmp_path):
    from jumpsight_coach.core import load_profile
    from jumpsight_coach.pipelines import p5_case

    corpus = _corpus(tmp_path, [0.60, 0.62, 0.61, 0.59])
    mine = tmp_path / "mine_result.json"
    mine.write_text(json.dumps(_result(0.44)), encoding="utf-8")
    rec = p5_case(load_profile(mine), corpus_dir=corpus)
    text = " | ".join(rec.diagnosis)
    assert "not enough measurements" not in text, text
    # the comparison happened by FLIGHT TIME, which is measured
    assert "flight time" in text, text
    assert "low_height" in {g for d in rec.drills for g in (d.get("targets") or [])} or rec.drills, text


def test_rotation_is_compared_only_where_it_is_measured(tmp_path):
    """Revolutions that the engine refused do not become the basis for advice."""
    from jumpsight_coach.core import load_profile
    from jumpsight_coach.pipelines import p5_case

    corpus = _corpus(tmp_path, [0.60, 0.62, 0.61])
    for f in sorted(corpus.glob("*_result.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        d["rotation"]["revolutions"] = 2.4  # the number exists but is unsuitable
        f.write_text(json.dumps(d), encoding="utf-8")
    mine = tmp_path / "mine_result.json"
    mine.write_text(json.dumps(_result(0.60, rev=1.2, usable=False)), encoding="utf-8")
    rec = p5_case(load_profile(mine), corpus_dir=corpus)
    assert not any("revolutions" in d for d in rec.diagnosis), rec.diagnosis


def test_profile_carries_the_integer_count(tmp_path):
    from jumpsight_coach.core import load_profile

    f = tmp_path / "x_result.json"
    f.write_text(json.dumps(_result(0.5, count=3)), encoding="utf-8")
    p = load_profile(f)
    assert p.nominal_count == 3
    assert p.revolutions is None  # the decimal is honestly absent
    # the reason there are no revolutions reaches the advice
    assert any(n.get("code") == "revolutions" for n in p.not_measured), p.not_measured
