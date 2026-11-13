"""Job state of the analyzer: in-memory table, atomic persistence to WORK/<job>/job.json,
recovery after a restart, TTL cleanup and upload limits.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from jumpsight_core import paths
from jumpsight_core.job_queue import AnalysisQueue

from . import hooks

# The source of truth is the file WORK/<job>/job.json: every state change is written
# atomically, /status and /summary read from memory and fall back to disk. A WORK
# directory on a shared volume makes the state visible to every container without
# Redis. Heavy fields (per-frame arrays) do not go into the file.

WORK = paths.WORK_DIR
JOBS: dict[str, dict] = {}
_ANALYSIS_QUEUE = AnalysisQueue(
    workers=int(os.environ.get("JS_ANALYSIS_WORKERS", "1")), pending=int(os.environ.get("JS_MAX_PENDING_JOBS", "8"))
)
_WARN_KEYS = ("jumpsight_error",)

_ALLOWED_EXT = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}
_MAX_UPLOAD_MB = int(os.environ.get("JS_MAX_UPLOAD_MB", "1024"))
_MAX_DURATION_S = float(os.environ.get("JS_MAX_DURATION_S", "900"))
_JOB_TTL_H = float(os.environ.get("JS_JOB_TTL_H", "72"))
_last_sweep = [0.0]

_PERSIST_LOCK = threading.Lock()


def _jsonable(o):
    """NaN and Infinity do not exist in JSON. Instead of a silent replacement with 0,
    None is used, which the report draws as a dash meaning "not measured"."""
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    return o


def _status_projection(j: dict) -> dict:
    ev = j.get("events") or []
    return {
        "state": j.get("state"),
        "uid": j.get("uid"),
        "stage": j.get("stage"),
        "early": j.get("early"),
        "started": j.get("started"),
        "timing": j.get("timing"),
        "metrics": j.get("metrics"),
        "total": len(ev),
        "done": sum(1 for e in ev if e.get("state") == "done"),
        "warnings": {k: j[k] for k in _WARN_KEYS if j.get(k)},
        "error": j.get("error"),
        "error_code": j.get("error_code"),
        "queue_wait_s": j.get("queue_wait_s"),
    }


def _probe_duration(path: Path) -> float | None:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True,
            text=True,
            timeout=60,
        ).stdout.strip()
        return float(out) if out else None
    except Exception:
        return None


def _sweep_old_jobs() -> None:
    """Cleanup by TTL: the work directory would otherwise grow without limit."""
    now = time.time()
    if now - _last_sweep[0] < 600 or _JOB_TTL_H <= 0:
        return
    _last_sweep[0] = now
    cutoff = now - _JOB_TTL_H * 3600
    for d in WORK.glob("*"):
        try:
            if d.is_dir() and d.stat().st_mtime < cutoff:
                jid = d.name
                if (JOBS.get(jid) or {}).get("state") in ("queued", "scanning", "running"):
                    continue
                # The example analysis for new visitors lives until it is
                # explicitly removed (tools/demo_job.py), not on the TTL.
                if (JOBS.get(jid) or {}).get("demo"):
                    continue
                # videos with consent to training: the scarcest data of the project
                if (JOBS.get(jid) or {}).get("train_consent"):
                    continue
                shutil.rmtree(d, ignore_errors=True)
                JOBS.pop(jid, None)
        except OSError:
            continue


def _persist(job_id: str) -> None:
    j = JOBS.get(job_id)
    if not j:
        return
    d = WORK / job_id
    try:
        d.mkdir(parents=True, exist_ok=True)
        data = dict(j)
        tmp = d / "job.json.tmp"
        with _PERSIST_LOCK:
            tmp.write_text(json.dumps(_jsonable(data), ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, d / "job.json")
    except Exception as _pe:
        print(f"[jobs] persist {job_id} failed: {_pe}", file=sys.stderr)
    if hooks._on_persist is not None:
        try:
            hooks._on_persist(job_id, _status_projection(j))
        except Exception as _he:
            print(f"[jobs] status hook {job_id}: {_he}", file=sys.stderr)


def _job(job_id: str) -> dict | None:
    """Job state: from memory, otherwise from disk (another container or a restart)."""
    j = JOBS.get(job_id)
    if j is not None:
        return j
    f = WORK / job_id / "job.json"
    if not f.is_file():
        return None
    try:
        j = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    JOBS[job_id] = j
    return j


@contextlib.contextmanager
def _stage(job_id: str, name: str):
    """Stage stopwatch, so "analysis is slow" is a number, not a guess.
    Writes both to the log and to the job itself, so stages are visible in /status."""
    t0 = time.time()
    j = JOBS.get(job_id) or {}
    j.setdefault("timing", {})
    j["stage"] = name
    try:
        yield
    finally:
        dt = round(time.time() - t0, 1)
        j["timing"][name] = dt
        print(f"[timing] {job_id} {name}: {dt}s", flush=True)


def attempt_stem(job_id: str, video: Path, attempt_id) -> str:
    """Unique key for an attempt analysis: <job>_<safe name>_att<N>.

    A bare stem (f"{video.stem}_att{N}") collides across users: identical file names
    (a live recording is always "clip", phone cameras too) overwrite each other's
    results in the shared directory, and the owner is looked up by stem, so one user
    could open another user's video. Safe characters only, so that the stem passes
    the access check ([A-Za-z0-9_.-], coach/api._require_stem_access)."""
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", video.stem).strip("_.")[:48] or "video"
    return f"{job_id}_{safe}_att{attempt_id}"


def _recover():
    """Restore already computed jobs from disk.

    A server restart must not destroy a result the user waited five minutes for:
    a saved link must keep opening. Unfinished jobs are not resumed.
    """
    for d in sorted(WORK.glob("*")):
        if not d.is_dir() or d.name in JOBS:
            continue
        jf = d / "job.json"
        if jf.is_file():
            try:
                job = json.loads(jf.read_text(encoding="utf-8"))
                if job.get("state") in ("done", "error"):
                    JOBS[d.name] = job
                    continue
            except (OSError, ValueError):
                pass
