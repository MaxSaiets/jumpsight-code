"""One file with several attempts is not independent evidence of the focus."""

from types import SimpleNamespace

import pytest

from jumpsight_coach import jobs, session, skills


def row(i, source, confidence="medium", code="fall"):
    record = {
        "stem": f"clip_att{i}",
        "jump": "Salchow",
        "outcome": "measured",
        "errors": [code],
        "errors_conf": {code: confidence},
    }
    if source is not None:
        record["file_key"] = f"{source}#a{i}"
    return record


def guard(monkeypatch, rows, code="fall", confidence="medium", persistent=False):
    monkeypatch.setattr(jobs, "history", lambda: rows)
    profile = SimpleNamespace(rotation_confidence="high", errors_found=[{"code": code, "confidence": confidence}])
    goal = session._goal_of(code)
    gaps = skills.persistent_gaps() if persistent else []
    return session.guard_focus(goal, gaps, profile)


def test_one_file_two_medium_attempts_cannot_supply_two_sources(monkeypatch):
    focus, reason = guard(monkeypatch, [row(i, "a" * 32) for i in range(2)])
    assert focus == "basics_rotation"
    assert reason["analyses_with_code"] == 1
    assert reason["evidence_unit"] == "video_source"


@pytest.mark.parametrize("sources", [["a" * 32] * 3, ["a" * 32, "b" * 32, "c" * 32]])
def test_persistent_low_does_not_supply_confident_focus(monkeypatch, sources):
    rows = [row(i, source, "low", "step_out") for i, source in enumerate(sources)]
    focus, reason = guard(monkeypatch, rows, "step_out", "low", persistent=True)
    assert skills.persistent_gaps() == ["step_out"]
    assert skills.skill_map()["jumps"][0]["gaps"][0]["of"] == 3
    assert focus == "basics_rotation" and reason["analyses_with_code"] == 0


def test_two_confident_sources_support_focus(monkeypatch):
    focus, reason = guard(monkeypatch, [row(0, "a" * 32), row(1, "b" * 32)])
    assert focus == "fall" and reason is None


def test_persistent_history_does_not_lose_two_prior_confident_sources(monkeypatch):
    rows = [
        row(0, "a" * 32, "medium", "step_out"),
        row(1, "b" * 32, "high", "step_out"),
        row(2, "a" * 32, "low", "step_out"),
    ]
    focus, reason = guard(monkeypatch, rows, "step_out", "low", persistent=True)
    assert focus == session._goal_of("step_out") and reason is None


@pytest.mark.parametrize("missing", ["source", "confidence", "invalid_confidence"])
def test_unknown_provenance_is_visible_but_not_confirmed(monkeypatch, missing):
    rows = [row(0, "a" * 32), row(1, "b" * 32)]
    for record in rows:
        if missing == "source":
            record.pop("file_key")
        if missing == "confidence":
            record.pop("errors_conf")
        if missing == "invalid_confidence":
            record["errors_conf"]["fall"] = "unvalidated"
    focus, reason = guard(monkeypatch, rows)
    assert focus == "basics_rotation" and reason["analyses_with_code"] == 0


@pytest.mark.parametrize(
    "record,expected",
    [
        ({"file_key": "a" * 32 + "#a2"}, "a" * 32),
        ({"file_key": "a" * 32}, "a" * 32),
        ({"video_source_key": "b" * 32, "file_key": "b" * 32 + "#a3"}, "b" * 32),
        ({"stem": "a" * 32}, None),
        ({"file_key": "one_content_hash#a2"}, None),
        ({"file_key": "a" * 32 + "#aunknown"}, None),
        ({"video_source_key": "garbage"}, None),
        ({"video_source_key": "b" * 32, "file_key": "a" * 32 + "#a1"}, None),
    ],
)
def test_source_identity_only_uses_supported_writer_metadata(record, expected):
    assert jobs.video_source_key(record) == expected


def test_writer_keeps_attempt_key_and_explicit_source(monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "_hp", lambda: tmp_path / "history.json")
    video = tmp_path / "video.mp4"
    video.write_bytes(b"controlled-video-bytes")
    for i in range(2):
        jobs.add_history_unmeasured(f"stem{i}", "controlled", video_path=video, attempt_id=i)
    rows = jobs.history()
    assert len(rows) == 2
    assert len({record["video_source_key"] for record in rows}) == 1
    assert len({record["file_key"] for record in rows}) == 2


def test_latest_unknown_error_confidence_cannot_borrow_rotation_confidence(monkeypatch):
    rows = [row(0, "a" * 32), row(1, "b" * 32)]
    focus, reason = guard(monkeypatch, rows, confidence="unvalidated")
    assert focus == "basics_rotation" and reason["rotation_confidence"] == "unknown"
