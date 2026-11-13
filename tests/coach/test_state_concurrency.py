"""User state under load: nothing is lost and nothing collides.

Five places in coach/ read JSON, changed it and wrote it back with plain `write_text`. Two simultaneous saves lost one of two, and an interruption on the write left an empty page (`skills.load` on it raised JSONDecodeError outward). While there is one user this is not visible; this is prevention before a multi-user mode.

ISOLATION (without it the test would write into the real coach/out): the store paths are moved into tmp_path, and the uid is set INSIDE each thread, because a contextvar is not inherited by a new threading.Thread.
"""

from __future__ import annotations

import json
import threading

from jumpsight_core import paths  # noqa: E402


def _isolate(monkeypatch, tmp_path):
    from jumpsight_coach import fitness, goal, session, skills

    monkeypatch.setattr(goal, "STORE", tmp_path / "goal.json")
    monkeypatch.setattr(skills, "PROFILE", tmp_path / "skill_profile.json")
    monkeypatch.setattr(fitness, "PROFILE", tmp_path / "fitness.json")
    monkeypatch.setattr(session, "LOG", tmp_path / "session_log.json")
    return goal, skills, fitness, session


def _run(n, fn):
    errors = []

    def _worker(i):
        from jumpsight_coach import userctx

        userctx.set_uid(None)  # contextvar in a new thread
        try:
            fn(i)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{type(e).__name__}: {e}")

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return errors


def test_twenty_sessions_are_all_written(monkeypatch, tmp_path):
    _goal, _skills, _fitness, session = _isolate(monkeypatch, tmp_path)
    errors = _run(20, lambda i: session._save({"n": i}))
    assert not errors, errors
    data = json.loads((tmp_path / "session_log.json").read_text(encoding="utf-8"))
    assert len(data) == 20, f"wrote {len(data)} of 20"
    assert sorted(r["n"] for r in data) == list(range(20))


def test_fitness_results_do_not_erase_each_other(monkeypatch, tmp_path):
    from jumpsight_coach import fitness

    _isolate(monkeypatch, tmp_path)
    ids = [t["id"] for t in fitness.TESTS][:6]
    errors = _run(len(ids), lambda i: fitness.save({ids[i]: 10 + i}))
    assert not errors, errors
    raw = json.loads((tmp_path / "fitness.json").read_text(encoding="utf-8"))["raw"]
    assert set(raw) == set(ids), f"remained {sorted(raw)} of {sorted(ids)}"


def test_reader_never_sees_a_half_written_file(monkeypatch, tmp_path):
    goal, skills, _f, _s = _isolate(monkeypatch, tmp_path)
    stop = threading.Event()
    seen: list[str] = []

    def _reader():
        from jumpsight_coach import userctx

        userctx.set_uid(None)
        while not stop.is_set():
            try:
                goal.load()
                skills.load()
            except Exception as e:  # noqa: BLE001
                seen.append(f"{type(e).__name__}: {e}")

    r = threading.Thread(target=_reader)
    r.start()
    try:
        for i in range(200):
            goal.save("axel", 50 + (i % 40), "2026-12-01")
    finally:
        stop.set()
        r.join()
    assert not seen, seen[:3]


def test_real_user_files_are_untouched(monkeypatch, tmp_path):
    """The test itself must not write into the real coach/out."""
    from jumpsight_coach import goal

    real = paths.STATE_DIR / "goal.json"
    before = real.stat().st_mtime_ns if real.exists() else None
    _isolate(monkeypatch, tmp_path)
    goal.save("lutz", 60, "2026-12-01")
    after = real.stat().st_mtime_ns if real.exists() else None
    assert before == after
