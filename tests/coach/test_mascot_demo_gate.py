"""A mascot demo must be the clip its report describes.

The report's `ok` is not tied to a file, so the demo's duration must match the
source duration recorded at publication (`lesson_duration_s`), and a binding
hash, when present, must match the file that is about to be shown. Demos are
published under `<JS_CLIP_PREFIX><drill id>`.
"""

from __future__ import annotations

import hashlib
import json

DRILL = {"id": "d1", "name": "Drill", "targets": []}
OK = {"ok": True, "layout": "character-only", "lesson_footage": False}


def _stage(tmp_path, monkeypatch, *, report: dict, demo_s, source_s):
    from jumpsight_coach import api

    work = tmp_path / "mascot"
    folder = work / "out" / f"{api.CLIP_PREFIX}d1"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{api.CLIP_PREFIX}d1_mascot.mp4").write_bytes(b"")
    rep = dict(report)
    if source_s is not None:
        rep["lesson_duration_s"] = source_s
    (folder / "report.json").write_text(json.dumps(rep), encoding="utf-8")

    monkeypatch.setattr(api, "MASCOT_WORK", work)
    monkeypatch.setattr(api, "load_kb", lambda: ([DRILL], {}))
    monkeypatch.setattr(api, "_media_duration_s", lambda p: demo_s)
    # the contract is strict (character only, no source audio); these tests
    # check the duration and the binding, so the rest is declared as valid
    monkeypatch.setattr(api, "_media_has_audio", lambda p: False)
    return api, folder


def test_matching_demo_is_shown(tmp_path, monkeypatch):
    api, _ = _stage(tmp_path, monkeypatch, report=OK, demo_s=26.00, source_s=25.98)
    assert api._mascot_file("d1") is not None


def test_demo_of_another_length_is_not_shown(tmp_path, monkeypatch):
    api, _ = _stage(tmp_path, monkeypatch, report=OK, demo_s=31.70, source_s=26.20)
    assert api._mascot_file("d1") is None


def test_unverifiable_duration_is_not_shown(tmp_path, monkeypatch):
    api, _ = _stage(tmp_path, monkeypatch, report=OK, demo_s=None, source_s=26.20)
    assert api._mascot_file("d1") is None
    api, _ = _stage(tmp_path, monkeypatch, report=OK, demo_s=26.0, source_s=None)
    assert api._mascot_file("d1") is None


def test_failed_report_still_blocks(tmp_path, monkeypatch):
    api, _ = _stage(tmp_path, monkeypatch, report={"ok": False}, demo_s=26.00, source_s=26.00)
    assert api._mascot_file("d1") is None


def test_report_that_describes_another_file_blocks(tmp_path, monkeypatch):
    api, _ = _stage(
        tmp_path,
        monkeypatch,
        report={**OK, "binding": {"video": {"size": 999999, "sha256": "0" * 64}}},
        demo_s=26.00,
        source_s=26.00,
    )
    assert api._mascot_file("d1") is None


def test_matching_binding_passes(tmp_path, monkeypatch):
    api, folder = _stage(tmp_path, monkeypatch, report=OK, demo_s=26.00, source_s=26.00)
    demo = folder / f"{api.CLIP_PREFIX}d1_mascot.mp4"
    demo.write_bytes(b"demo")
    (folder / "report.json").write_text(
        json.dumps(
            {
                **OK,
                "lesson_duration_s": 26.00,
                "binding": {"video": {"size": demo.stat().st_size, "sha256": hashlib.sha256(b"demo").hexdigest()}},
            }
        ),
        encoding="utf-8",
    )
    assert api._mascot_file("d1") is not None
