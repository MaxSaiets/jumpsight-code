"""Live counter during recording without a live worker (preview runs of the growing file).
`found` of a recording job is how many jumps the last completed preview run found.
"""

from __future__ import annotations

import subprocess
import time

from . import dispatch, jobs, live_local

# Every >= 8 s of recording, and not more often than the previous run ends, the
# growing file is remuxed into preview_k.mkv and goes through the regular analysis
# path as a separate job <job>-p<k>. The cost is O(n^2) in the recording length (each
# run starts from zero), acceptable up to ~1-2 min.


def _preview_status(meta: dict) -> dict:
    """State of runs: whether a live one exists, and how many jumps the last completed run found."""
    out = {"found": None, "preview_state": None, "preview_id": None, "previews": len(meta.get("previews") or [])}
    for pid in reversed(meta.get("previews") or []):
        pj = jobs._job(pid)
        if not pj:
            continue
        st = pj.get("state")
        if out["preview_state"] is None:
            out["preview_state"] = st
            out["preview_id"] = pid
        if st == "done" and out["found"] is None:
            ev = pj.get("events") or []
            out["found"] = sum(1 for e in ev if e.get("state") in ("done", "running"))
            out["found_id"] = pid
            break
    return out


def _maybe_preview(job_id: str, meta: dict, *, enabled: bool, gap_s: float) -> None:
    if not enabled or meta.get("finished"):
        return
    if job_id in live_local._LIVE_ACTIVE or job_id in live_local._LIVE_LOCAL:
        # the tail live worker already watches this job: two runs would fight for
        # the same --serve worker simultaneously
        return
    now = time.time()
    if now - float(meta.get("last_preview", 0)) < gap_s:
        return
    if meta.get("parts", 0) < 2:
        return
    # do not start a new one while the previous one is still computing
    prev = meta.get("previews") or []
    if prev:
        pj = jobs._job(prev[-1])
        if pj and pj.get("state") not in ("done", "error"):
            return
    d = jobs.WORK / job_id
    k = len(prev)
    src = d / f"input.{meta['ext']}"
    dst = d / f"preview_{k}.mkv"
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-c", "copy", str(dst)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode != 0 or not dst.is_file() or dst.stat().st_size == 0:
        meta["last_preview"] = now
        return
    dur = jobs._probe_duration(dst) or 0.0
    pid = f"{job_id}-p{k}"
    jobs.JOBS[pid] = {
        "state": "queued",
        "video": str(dst),
        "name": dst.name,
        "started": now,
        "duration": float(dur),
        "uid": meta.get("uid"),
        "preview_of": job_id,
    }
    jobs._persist(pid)
    dispatch._dispatch(pid, dst)
    meta.setdefault("previews", []).append(pid)
    meta["last_preview"] = now
