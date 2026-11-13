"""The FastAPI application factory: job-ownership and error middleware plus the
route groups of the analyzer.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.middleware.gzip import GZipMiddleware

from . import jobs, status, summary, uploads

_JOB_ROUTES = {
    "status",
    "events",
    "summary",
    "fulldata",
    "full",
    "media",
    "data",
    "result",
    "cancel",
    "upload_part",
    "upload_finish",
    "train_consent",
}


def _guard_jobs(request: Request):
    """Synchronous part of the job-ownership middleware: (uid, refusal or None)."""
    from jumpsight_coach.accounts import can_view_job
    from jumpsight_coach.sessions import SHARE_COOKIE, effective_uid, same_origin

    if not same_origin(request):
        return None, JSONResponse({"detail": "cross-origin request"}, status_code=403)
    uid = effective_uid(request)
    request.state.app_uid = uid
    parts = request.url.path.strip("/").split("/")
    if parts[0] in ("upload", "upload_start") and not uid:
        return uid, JSONResponse({"detail": "user required"}, status_code=401)
    if len(parts) > 1 and parts[0] in _JOB_ROUTES:
        job_id = parts[1]
        if not job_id.isascii() or not all(c.isalnum() or c in "-_" for c in job_id):
            return uid, JSONResponse({"detail": "unknown job"}, status_code=404)
        j = jobs._job(job_id)
        owner = j.get("uid") if j else None
        if j is None:
            mp = jobs.WORK / job_id / "parts.json"
            if mp.is_file():
                with contextlib.suppress(OSError, ValueError):
                    owner = json.loads(mp.read_text(encoding="utf-8")).get("uid")
        # The demo analysis example is open to everyone for READING only: changes
        # to the job state (cancel, recording parts) remain with the owner.
        public_demo = bool(j and j.get("demo") and j.get("state") == "done" and request.method in ("GET", "HEAD"))
        if not public_demo and not can_view_job(owner, uid, job_id, request.cookies.get(SHARE_COOKIE)):
            return uid, JSONResponse({"detail": "unknown job"}, status_code=404)
    return uid, None


async def _protect_jobs(request: Request, call_next):
    """One owner for fetch, SSE, video, and live-recording parts.

    All checks run in a thread pool: with the session and job state in a remote
    shared dict (a miss meaning a volume reload) the event loop would otherwise
    serve requests one at a time, and parts and /status hung for up to 25 s on the
    single web container. The decision logic is in `_guard_jobs`.
    """
    from jumpsight_coach.sessions import COOKIE, resolve, set_cookie

    uid, deny = await run_in_threadpool(_guard_jobs, request)
    if deny is not None:
        return deny
    response = await call_next(request)
    if uid:

        def _cookie():
            if not resolve(request.cookies.get(COOKIE)) and f"{COOKIE}=" not in response.headers.get("set-cookie", ""):
                set_cookie(response, request, uid, guest=True)

        await run_in_threadpool(_cookie)
    return response


def build_app():
    app = FastAPI(title="Figure skating jump analysis")
    jobs.WORK.mkdir(parents=True, exist_ok=True)
    jobs._recover()

    app.middleware("http")(_protect_jobs)

    # Static assets are ~450 KB of uncompressed JS/CSS/HTML; gzip cuts that
    # roughly fourfold on mobile networks. Starlette skips text/event-stream,
    # so the /events SSE stream is not buffered.
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    api_errors_log: list = []

    @app.get("/api_errors")
    def api_errors(request: Request):
        tok = os.environ.get("JS_COACH_TOKEN", "")
        if not tok or request.headers.get("x-coach-token", "") != tok:
            return JSONResponse({"error": "token"}, status_code=403)
        return JSONResponse(jobs._jsonable(list(api_errors_log)))

    @app.middleware("http")
    async def _log_unhandled(request, call_next):
        from jumpsight_coach.auth_store import AuthStoreUnavailable

        # A 500 without a traceback in the container logs is undiagnosable (three
        # simultaneous uploads once failed with the cause printed nowhere). The
        # marker [api-error] is searched for in the logs.
        try:
            return await call_next(request)
        except AuthStoreUnavailable:
            return JSONResponse(
                {"detail": "authentication temporarily unavailable"},
                status_code=503,
                headers={"Retry-After": "30", "Cache-Control": "no-store"},
            )
        except Exception as _ex:
            try:  # the last errors are kept in process memory; read /api_errors
                api_errors_log.append(
                    {
                        "t": time.time(),
                        "path": request.url.path,
                        "err": f"{type(_ex).__name__}: {_ex}"[:300],
                        "tb": traceback.format_exc()[-1500:],
                    }
                )
                del api_errors_log[:-20]
            except Exception:
                pass
            print("[api-error]", request.method, request.url.path, file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr, flush=True)
            raise

    uploads.register(app)
    status.register(app)
    summary.register(app)
    return app
