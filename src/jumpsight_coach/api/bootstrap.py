"""Application object, per-request user context middleware and chat warm-up."""

from __future__ import annotations

import os
import threading

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="coach API", version="1.1")


@app.middleware("http")
async def _user_ctx(request, call_next):
    # The session wins over the header; a registered UID without a session is rejected.
    # The production session store is a network call: keep it off the event loop.
    from starlette.concurrency import run_in_threadpool

    from ..auth_store import AuthStoreUnavailable
    from ..sessions import effective_uid, resolve, same_origin
    from ..userctx import reset_uid, set_uid

    if not same_origin(request):
        return JSONResponse({"detail": "cross-origin request"}, status_code=403)
    try:
        uid = await run_in_threadpool(effective_uid, request)
    except AuthStoreUnavailable:
        return JSONResponse(
            {"detail": "authentication temporarily unavailable"},
            status_code=503,
            headers={"Retry-After": "30", "Cache-Control": "no-store"},
        )
    tok = set_uid(uid)
    from ..userctx import begin_anonymous_request, end_anonymous_request

    anon_tok = None if uid else begin_anonymous_request()
    try:
        response = await call_next(request)
        from ..sessions import COOKIE as _SC

        if uid:

            def _cookie():
                if not resolve(request.cookies.get(_SC)) and f"{_SC}=" not in response.headers.get("set-cookie", ""):
                    from ..sessions import set_cookie

                    set_cookie(response, request, uid, guest=True)

            await run_in_threadpool(_cookie)
        return response
    except AuthStoreUnavailable:
        return JSONResponse(
            {"detail": "authentication temporarily unavailable"},
            status_code=503,
            headers={"Retry-After": "30", "Cache-Control": "no-store"},
        )
    finally:
        reset_uid(tok)
        if anon_tok is not None:
            end_anonymous_request(anon_tok)


@app.on_event("startup")
def _warmup() -> None:
    """Background warm-up of the chat: embedding model and indexes, so the
    first question does not wait. A missing corpus is reported, not fatal."""
    if os.environ.get("JS_SKIP_WARMUP") == "1":
        return

    def go():
        try:
            from ..embed import build_index
            from ..knowledge import CorpusMissing, _load, _m

            try:
                _load()
            except CorpusMissing as ex:
                print(f"[warmup] {ex}", flush=True)
                return
            build_index()
            # _load() and build_index() read cached embeddings and do not
            # create the model; load it and run a dummy encode explicitly.
            _m().encode(["query: warmup"], show_progress_bar=False)
            print("[warmup] knowledge indexes and embedding model are warm", flush=True)
        except Exception as ex:
            print(f"[warmup] {ex}", flush=True)

    threading.Thread(target=go, daemon=True).start()
