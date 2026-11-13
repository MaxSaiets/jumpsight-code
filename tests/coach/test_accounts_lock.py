"""Locking of the Coach JSON store between processes."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from jumpsight_core.paths import REPO_ROOT


def _isolated_lock(monkeypatch, tmp_path):
    from jumpsight_coach import accounts

    monkeypatch.setattr(accounts, "STORE", tmp_path / "accounts.json")
    monkeypatch.setattr(accounts, "USERS", tmp_path / "users")
    return accounts


def test_lock_lives_next_to_current_store(monkeypatch, tmp_path):
    """A test or a future separate store must not lock the production file."""
    accounts = _isolated_lock(monkeypatch, tmp_path)
    expected = tmp_path / "accounts.lock"

    with accounts._LOCK:
        assert expected.exists()

    assert not expected.exists()


def test_two_processes_preserve_both_json_updates(monkeypatch, tmp_path):
    """Two independent processes do not lose one read-modify-write record."""
    _isolated_lock(monkeypatch, tmp_path)
    store = tmp_path / "accounts.json"
    worker = """
import json
import sys
import time
from pathlib import Path
from jumpsight_coach import accounts

accounts.STORE = Path(sys.argv[1])
accounts.USERS = accounts.STORE.parent / "users"
with accounts._LOCK:
    data = accounts._load()
    data.setdefault("markers", []).append(sys.argv[2])
    time.sleep(0.15)
    accounts._save(data)
"""
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    first = subprocess.Popen([sys.executable, "-c", worker, str(store), "first"], env=env)
    second = subprocess.Popen([sys.executable, "-c", worker, str(store), "second"], env=env)
    assert first.wait(timeout=10) == 0
    assert second.wait(timeout=10) == 0

    assert sorted(json.loads(store.read_text(encoding="utf-8"))["markers"]) == ["first", "second"]
    assert not store.with_suffix(".lock").exists()


def test_only_linked_coach_can_write_student_focus(monkeypatch, tmp_path):
    """A detached coach does not leave the pupil with a hidden session target."""
    accounts = _isolated_lock(monkeypatch, tmp_path)
    from jumpsight_coach.userctx import reset_uid, set_uid

    coach, student = "coach_focus_123", "student_focus_123"
    token = set_uid(coach)
    try:
        with accounts._LOCK:
            data = accounts._load()
            data["teams"][coach] = {"students": [student]}
            accounts._save(data)
        assert accounts.set_coach_focus(student, "under_rotation")["goal"] == "under_rotation"
        accounts.unlink(student)
        with pytest.raises(PermissionError):
            accounts.set_coach_focus(student, "under_rotation")
    finally:
        reset_uid(token)
