"""Status routes of a job: `/status`, `/events` (SSE), `/cancel` and `/prewarm`."""

from __future__ import annotations

import asyncio
import json
import sys
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse

from . import hooks, jobs, preview


def register(app: FastAPI) -> None:
    """Add the status routes to `app`."""

    @app.get("/status/{job_id}")
    def status(job_id: str):
        j = jobs._job(job_id)
        if not j:
            mp = jobs.WORK / job_id / "parts.json"
            if mp.is_file():
                try:
                    meta = json.loads(mp.read_text(encoding="utf-8"))
                    ps = preview._preview_status(meta)
                    lv = hooks._live_status(job_id) if hooks._live_status is not None else None
                    if lv:
                        # the live worker is more accurate and faster than the preview runs
                        ps["found"] = lv.get("found")
                        ps["live"] = lv.get("live") or []
                        ps["live_state"] = lv.get("state")
                        ps["scanned_s"] = lv.get("scanned_s")
                        for key in ("live_errors", "live_warning", "live_degraded", "pending_analyzes", "open_seen"):
                            if key in lv:
                                ps[key] = lv[key]
                    return JSONResponse(
                        jobs._jsonable(
                            {
                                "state": "recording",
                                "parts": meta.get("parts", 0),
                                "bytes": meta.get("bytes", 0),
                                "elapsed": round(time.time() - float(meta.get("started", time.time()))),
                                **ps,
                            }
                        )
                    )
                except Exception:
                    pass
            return JSONResponse({"state": "unknown"}, status_code=404)
        ev = j.get("events") or []
        out = {
            "state": j["state"],
            "elapsed": round(time.time() - j["started"]),
            "total": len(ev),
            "done": sum(1 for e in ev if e["state"] == "done"),
            "running": next((e["peak_frame"] for e in ev if e["state"] == "running"), None),
        }
        if j.get("timing"):
            out["timing"] = j["timing"]
        # Expected time comes from the server, not from client constants. Measured on
        # a CPU worker with remote models: a 12 s clip -> response 11-19 s, an 87 s
        # clip -> 40-90 s (with cold starts).
        if j.get("duration"):
            _d = float(j["duration"])
            out["eta_lo"] = int(round(4 + 0.6 * _d))
            out["eta_hi"] = int(round(12 + 1.3 * _d))
        if j.get("stage"):
            out["stage"] = j["stage"]
        if isinstance(j.get("early"), dict):
            out["early"] = j["early"]
        out["queue_position"] = jobs._ANALYSIS_QUEUE.position(job_id)
        out["queue_wait_s"] = j.get("queue_wait_s")
        if j["state"] == "error":
            out["error"] = j.get("error", "")
        # silent failures are returned in the response
        warn = {k: j[k] for k in jobs._WARN_KEYS if j.get(k)}
        if warn:
            out["warnings"] = warn
        return JSONResponse(jobs._jsonable(out))

    @app.post("/prewarm")
    def prewarm(live: int = 0):
        """Wakes the compute worker in advance (cloud); locally, nothing.
        live=1 also wakes the live worker (live-recording buttons)."""
        if hooks._prewarm_hook is None:
            return {"ok": True, "warming": False}
        try:
            try:
                hooks._prewarm_hook(live=bool(live))
            except TypeError:
                hooks._prewarm_hook()
        except Exception as _pe:
            print(f"[prewarm] {_pe}", file=sys.stderr)
            return {"ok": False, "warming": False}
        return {"ok": True, "warming": True}

    @app.post("/cancel/{job_id}")
    def cancel(job_id: str):
        """Cancellation from the waiting screen. A job in the queue is removed
        before it starts; what is already computing finishes (the thread is not interrupted),
        but the client no longer waits for it, and the response says so honestly."""
        j = jobs._job(job_id)
        if not j:
            return JSONResponse({"error": "unknown job"}, status_code=404)
        if j.get("state") in ("done", "error"):
            return JSONResponse({"state": j["state"], "cancelled": False})
        how = jobs._ANALYSIS_QUEUE.cancel(job_id)
        if how == "queued":
            jobs.JOBS[job_id].update(
                state="error", error_code="CANCELLED", error="cancelled by the user before analysis started"
            )
            jobs._persist(job_id)
            return JSONResponse({"state": "cancelled", "cancelled": True})
        return JSONResponse(
            {"state": j.get("state"), "cancelled": False, "note": "already running; it will finish on the server"}
        )

    @app.get("/events/{job_id}")
    async def events(job_id: str):
        """SSE instead of polling every 400 ms.

        The server rereads the state (shared dict/disk) every 300 ms and sends an event
        ONLY when something changed; a heartbeat every 15 s keeps the connection alive.
        After done/error: the last event, then close. The client falls back to polling
        if EventSource is unavailable or dropped.
        """

        def _snap():
            j = jobs._job(job_id)
            if not j:
                return None
            ev = j.get("events") or []
            out = {
                "state": j["state"],
                "elapsed": round(time.time() - j["started"]),
                "total": len(ev),
                "done": sum(1 for e in ev if e["state"] == "done"),
                "running": next((e["peak_frame"] for e in ev if e["state"] == "running"), None),
                "stage": j.get("stage"),
                "timing": j.get("timing"),
            }
            if isinstance(j.get("early"), dict):
                out["early"] = j["early"]
            out["queue_position"] = jobs._ANALYSIS_QUEUE.position(job_id)
            out["queue_wait_s"] = j.get("queue_wait_s")
            if j.get("duration"):
                _d = float(j["duration"])
                out["eta_lo"] = int(round(4 + 0.6 * _d))
                out["eta_hi"] = int(round(12 + 1.3 * _d))
            if j["state"] == "error":
                out["error"] = j.get("error", "")
            warn = {k: j[k] for k in jobs._WARN_KEYS if j.get(k)}
            if warn:
                out["warnings"] = warn
            return out

        async def _gen():
            last = None
            t_hb = time.time()
            t0 = time.time()
            while True:
                snap = await run_in_threadpool(_snap)
                if snap is None:
                    yield "event: gone\ndata: {}\n\n"
                    return
                key = json.dumps({k: v for k, v in snap.items() if k != "elapsed"}, sort_keys=True, default=str)
                if key != last or time.time() - t_hb > 15:
                    last = key
                    t_hb = time.time()
                    yield "data: " + json.dumps(jobs._jsonable(snap), default=str) + "\n\n"
                if snap.get("state") in ("done", "error") or time.time() - t0 > 900:
                    return
                await asyncio.sleep(0.3)

        return StreamingResponse(
            _gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        )
