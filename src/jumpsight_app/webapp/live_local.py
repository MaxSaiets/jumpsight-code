"""Live worker running inside the web process (the cloud runs `live_worker.run_live_loop` on its own machine).
State lives in process memory; active only without a cloud warm hook and with JS_LIVE_LOCAL on.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

from . import hooks, jobs

_LIVE_LOCAL: dict = {}  # job_id -> last state projection (found/live/state/...)
_LIVE_ACTIVE: set = set()  # job_ids of the live worker right now: do not start _maybe_preview for them
_LIVE_SLOTS = threading.BoundedSemaphore(max(1, int(os.environ.get("JS_LIVE_WORKERS", "1"))))


def _live_local_status(job_id: str) -> dict | None:
    return _LIVE_LOCAL.get(job_id)


def _live_scan_for_final(job_id: str, wait_s: float = 12.0) -> str | None:
    """Path to live_scan.pkl of the live worker for the final run, or None.

    After recording finishes the live worker scans the last tail and writes the
    file; the final run starts right after /upload_finish, so it waits up to wait_s
    for the worker to end or for the file to appear. With no live worker (regular
    upload) the result is None and the full scan runs as usual.

    The reuse is on by default: the live scan works on file snapshots (exactly
    meta.bytes bytes) and was proven equal to the full scan byte for byte (25
    random splits, and 5 splits with the real detector). On the simulator, twice:
    the same 5 rows, final after "stop" 15 -> 9-12 s (engine 14.5 -> 8.5-11.3 s).
    Scanning a file that was still growing gave 7 rows instead of 5.
    JS_LIVE_REUSE_SCAN=0 disables it.
    """
    if os.environ.get("JS_LIVE_REUSE_SCAN", "1") != "1":
        return None
    if hooks._live_scan_hook is not None:
        # cloud: the live worker runs on another machine; the scan arrives via the
        # volume, with a flag in the shared dict
        try:
            return hooks._live_scan_hook(job_id, wait_s)
        except Exception as _he:
            print(f"[live-scan] {job_id}: {_he}", file=sys.stderr, flush=True)
            return None
    d = (jobs.WORK / job_id).resolve()
    f = d / "live_scan.pkl"
    if job_id not in _LIVE_ACTIVE and not f.is_file():
        return None
    t0 = time.time()
    st = None
    while time.time() - t0 < wait_s:
        st = (_LIVE_LOCAL.get(job_id) or {}).get("state")
        if f.is_file() and st == "ended":
            break
        if st == "ended" and not f.is_file():
            print(
                f"[live-local {job_id}] final WITHOUT scan: the worker finished, no file", file=sys.stderr, flush=True
            )
            return None
        time.sleep(0.2)
    else:
        print(
            f"[live-local {job_id}] final WITHOUT scan: did not wait for {wait_s:.0f} s "
            f"(state={st}, file={f.is_file()})",
            file=sys.stderr,
            flush=True,
        )
    if f.is_file():
        print(
            f"[live-local {job_id}] final with the live worker's scan ({time.time() - t0:.1f} s wait)",
            file=sys.stderr,
            flush=True,
        )
        return str(f)
    return None


def _start_live_local(job_id: str, job_dir: Path) -> None:
    """Start a daemon thread running run_live_loop for one recording."""
    from ..live_worker import run_live_loop

    mp = job_dir / "parts.json"
    if not _LIVE_SLOTS.acquire(blocking=False):
        _LIVE_LOCAL[job_id] = {
            "state": "deferred",
            "found": None,
            "live": [],
            "live_warning": "Live cues are busy with another recording. Your full analysis starts when you stop.",
        }
        return

    def _is_finished() -> bool:
        try:
            return bool(json.loads(mp.read_text(encoding="utf-8")).get("finished"))
        except Exception:
            return False

    def _publish(proj: dict) -> None:
        _LIVE_LOCAL[job_id] = proj

    def _log(m: str) -> None:
        print(f"[live-local {job_id}] {m}", file=sys.stderr, flush=True)

    def _run() -> None:
        try:
            run_live_loop(job_dir, _is_finished, _publish, _log, reload=None, max_s=1150)
        except Exception as e:
            _log(f"crash: {type(e).__name__}: {e}")
            _LIVE_LOCAL[job_id] = {
                **_LIVE_LOCAL.get(job_id, {}),
                "state": "error",
                "live_warning": "Live preview is unavailable. The recording will be checked after you stop.",
            }
        finally:
            _LIVE_ACTIVE.discard(job_id)
            _LIVE_SLOTS.release()

    _LIVE_ACTIVE.add(job_id)
    threading.Thread(target=_run, daemon=True, name=f"live-local-{job_id}").start()
