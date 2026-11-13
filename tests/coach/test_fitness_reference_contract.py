"""The absence of a normative band is not a measured weakness."""

import json

import pytest

from jumpsight_coach.fitness import TESTS


@pytest.fixture
def fitness(monkeypatch, tmp_path):
    from jumpsight_coach import fitness
    from jumpsight_coach.userctx import reset_uid, set_uid

    monkeypatch.setattr(fitness, "PROFILE", tmp_path / "fitness.json")
    token = set_uid(None)
    try:
        yield fitness
    finally:
        reset_uid(token)


CASES = [(t, v) for t in TESTS for v in (min(b[0] for b in t["bands"]) - 1, max(b[1] for b in t["bands"]))]


@pytest.mark.parametrize("test,value", CASES, ids=[f"{t['id']}-{v}" for t, v in CASES])
def test_unmapped_raw_is_saved_without_weakness(fitness, test, value):
    result = fitness.save({test["id"]: str(value)})
    assert result["raw"][test["id"]] == str(value)
    assert test["group"] not in result["groups"]
    assert result["assessments"][test["id"]] == {"status": "unrated", "reason": "outside_reference"}
    assert result["bands"][test["id"]]
    gates = fitness.gates()
    assert not gates["has_data"]
    assert not any(gates[k] for k in ("limit_power", "limit_flex", "limit_balance", "limit_volume"))


@pytest.mark.parametrize("test", TESTS, ids=[t["id"] for t in TESTS])
def test_each_valid_lower_boundary_keeps_its_score(fitness, test):
    for score, (lo, _, label) in enumerate(test["bands"]):
        result = fitness._build({test["id"]: lo})
        assert result["bands"][test["id"]] == label
        assert result["groups"][test["group"]]["score"] == score


def test_mixed_group_ignores_unrated_sample_and_balance_gate(fitness):
    result = fitness.save({"plank": "120", "squats_60s": "-1", "balance_s": "-1"})
    assert result["groups"]["endurance"]["score"] == 2
    assert "balance" not in result["groups"]
    assert not fitness.gates()["limit_balance"]
    assert not fitness.gates()["limit_volume"]


def test_legacy_false_grade_is_reprojected_without_file_write(fitness):
    legacy = {
        "ts": 123,
        "raw": {"plank": "-1"},
        "bands": {"plank": ""},
        "groups": {"endurance": {"score": 0, "grade": "C", "label": "weak"}},
    }
    original = json.dumps(legacy, ensure_ascii=False).encode("utf-8")
    fitness.PROFILE.write_bytes(original)
    result = fitness.load()
    assert result["ts"] == 123
    assert result["groups"] == {}
    assert not fitness.gates()["limit_volume"]
    assert fitness.PROFILE.read_bytes() == original


def test_unrated_reason_keeps_the_raw_value(fitness):
    result = fitness.save({"plank": "999"})
    assert result["raw"]["plank"] == "999"
    assert result["bands"]["plank"] == "Unrated: result is outside the available reference bands."
    assert result["assessments"]["plank"]["status"] == "unrated"
