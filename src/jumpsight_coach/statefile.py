"""User state is read-modified-written under a lock and atomically.

Places that change JSON state in memory and write it back:

  goal.save / goal.clear      — goal for a jump
  skills.save_survey          — skills profile (load -> update -> write)
  fitness.save                — physical test results
  session._save              — completed session (append semantics)
  api./verdict_feedback       — 'the system said correct/wrong' labels

A plain `write_text` has two different failures:
  1. LOST UPDATE. Two simultaneous saves read the same base and the second overwrites the first. Not visible for one
     user; with several it is the first thing that breaks.
  2. NON-ATOMIC WRITE. `write_text` first truncates the file: an interruption at this point leaves an empty or
     half-written page, and the next read returns `None` (and `skills.load` raises JSONDecodeError altogether).

The atomic pattern is mkstemp + os.replace, combined here with the lock.

LIMIT OF THE PROTECTION: the lock is SINGLE-PROCESS. `uvicorn --workers>1` needs a file lock (`msvcrt.locking` on
Windows); it is deliberately absent, so as not to pretend to a guarantee that does not exist.
"""

from __future__ import annotations

import contextlib
import json
import os
import random
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    """One lock per file. The key is the path itself, so different users do not wait for each other (each has its own directory, see userctx.py)."""
    key = str(path.resolve()) if path.parent.exists() else str(path)
    with _LOCKS_GUARD:
        lk = _LOCKS.get(key)
        if lk is None:
            lk = _LOCKS[key] = threading.Lock()
        return lk


def read_json(path: Path, default: Any = None) -> Any:
    """Reading that does not fail on a broken file, but does not stay silent about it."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        print(
            f"[statefile] corrupt state {path.name}: {type(e).__name__} — using the default value",
            file=sys.stderr,
            flush=True,
        )
        return default


def write_json(path: Path, data: Any) -> None:
    """Atomic write: first alongside, then a single rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        # Windows: os.replace runs into a file that is being read at that moment (WinError 5). Python's open() on
        # Windows does not grant FILE_SHARE_DELETE, so while a reader holds the handle it cannot be renamed over.
        # Measured on a bench with a reader in a tight loop: 3 attempts of 50 ms were never enough and 8 attempts
        # (~0.7 s) were not enough in 1 run out of 6, so there are 15 attempts with a random component (~2.5 s in
        # total), and if it still fails, the exception
        # goes outward: silently losing a record is worse than failing loudly.
        for attempt in range(15):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 14:
                    raise
                time.sleep(0.02 * (attempt + 1) + random.uniform(0, 0.01))
    finally:
        with contextlib.suppress(OSError):
            Path(tmp).unlink(missing_ok=True)


def update_json(path: Path, mutate: Callable[[Any], Any], default: Any = None, *, preserve_broken: bool = False) -> Any:
    """Read, change, write: under a lock and atomically.

    `mutate` receives the value read and returns what must be written. The written value is returned.

    `preserve_broken=True`: for files whose contents cannot be reproduced (human testimony, training labels). If the existing file cannot be read, it is RENAMED alongside instead of being overwritten by new content. Silently starting from an empty list would mean erasing all earlier labels because of one temporary read error.
    """
    with _lock_for(path):
        cur = read_json(path, None)
        if cur is None and path.exists() and preserve_broken:
            spoiled = path.with_suffix(path.suffix + f".corrupt-{int(time.time())}")
            try:
                os.replace(path, spoiled)
                print(
                    f"[statefile] {path.name} is unreadable — kept as {spoiled.name}, writing a new one",
                    file=sys.stderr,
                    flush=True,
                )
            except OSError:
                pass
        if cur is None:
            cur = default
        new = mutate(cur)
        write_json(path, new)
        return new
