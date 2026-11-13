"""Who computes: queueing a job for analysis (`_dispatch`, `_enqueue`).
Locally a thread of the bounded queue; the cloud entry point replaces `_dispatch` with a GPU worker launch.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from fastapi.responses import JSONResponse

from jumpsight_core.job_queue import QueueFull

from . import jobs, pipeline

# In the cloud the API container stays light and multi-instance, and the number of
# workers grows with the queue. Both readers of job state read WORK/<job>/job.json on
# the shared volume.


def _dispatch_thread(job_id: str, video: Path) -> None:
    def work():
        try:
            jobs.JOBS[job_id]["queue_wait_s"] = round(time.time() - jobs.JOBS[job_id]["started"], 3)
            pipeline._prescan_job(job_id, video)
        except Exception as exc:
            print(f"[analysis {job_id}] {type(exc).__name__}: {exc}", file=sys.stderr)
            jobs.JOBS[job_id].update(
                state="error", error_code="ANALYSIS_FAILED", error="Analysis did not finish. Try again."
            )
            jobs._persist(job_id)

    jobs._ANALYSIS_QUEUE.submit(job_id, work)


_dispatch = _dispatch_thread


def _enqueue(job_id: str, video: Path):
    """Single overload response for a whole file and for chunked writes."""
    try:
        _dispatch(job_id, video)
    except QueueFull as exc:
        jobs.JOBS[job_id].update(state="error", error_code="QUEUE_FULL", error=str(exc))
        jobs._persist(job_id)
        return JSONResponse(
            {"job": job_id, "error_code": "QUEUE_FULL", "error": str(exc)},
            status_code=503,
            headers={"Retry-After": "10"},
        )
    return None
