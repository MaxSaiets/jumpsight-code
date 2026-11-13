"""Upload routes: a whole file (`/upload`) and a recording sent in parts
(`/upload_start`, `/upload_part`, `/upload_finish`).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
import weakref
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from . import dispatch, hooks, jobs, live_local, preview

# The recorder in the app (MediaRecorder, timeslice 4 s) sends each part at once; when
# the recording stops almost all of the video is already on the server, and analysis
# starts without a separate wait for the upload (30-90 s on a phone).

_DECLARABLE = ("Axel", "Salchow", "Toe loop", "Loop", "Flip", "Lutz")


def _json_dumps(o) -> str:
    return json.dumps(o, ensure_ascii=False)


def register(app: FastAPI) -> None:
    """Add the upload routes to `app`. Environment limits are read at build time."""
    parts_max_mb = int(os.environ.get("JS_MAX_UPLOAD_MB", "1024"))
    live_preview = os.environ.get("JS_LIVE_PREVIEW", "1") == "1"
    preview_gap_s = float(os.environ.get("JS_PREVIEW_GAP_S", "8"))

    @app.post("/upload")
    async def upload(
        request: Request,
        file: Annotated[UploadFile, File()],
        declared: Annotated[str, Form()] = "",
        train_consent: Annotated[str, Form()] = "",
        declared_turns: Annotated[str, Form()] = "",
    ):
        # Validation: one large or non-video file must not occupy a worker for the
        # whole processing time. The limits are environment variables, so the image
        # need not be rebuilt.
        name = Path(file.filename or "clip.mp4").name
        if Path(name).suffix.lower() not in jobs._ALLOWED_EXT:
            return JSONResponse(
                {"error": "unsupported file type", "allowed": sorted(jobs._ALLOWED_EXT)}, status_code=415
            )
        job_id = uuid.uuid4().hex[:12]
        d = jobs.WORK / job_id
        d.mkdir(parents=True, exist_ok=True)
        dst = d / name

        # The file is written outside the event loop: a synchronous copy in a
        # coroutine blocks the /status polls of all other users for the whole upload.
        def _save():
            total = 0
            with open(dst, "wb") as f:
                while True:
                    chunk = file.file.read(1 << 20)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > jobs._MAX_UPLOAD_MB * (1 << 20):
                        return False
                    f.write(chunk)
            return True

        if not await run_in_threadpool(_save):
            shutil.rmtree(d, ignore_errors=True)
            return JSONResponse({"error": f"file larger than {jobs._MAX_UPLOAD_MB} MB"}, status_code=413)
        dur = await run_in_threadpool(jobs._probe_duration, dst)
        if dur is None or dur > jobs._MAX_DURATION_S:
            shutil.rmtree(d, ignore_errors=True)
            return JSONResponse(
                {"error": f"not a readable video or longer than {jobs._MAX_DURATION_S:.0f} s"}, status_code=422
            )
        jobs._sweep_old_jobs()
        jobs.JOBS[job_id] = {
            "state": "queued",
            "video": str(dst),
            "name": name,
            "started": time.time(),
            "duration": float(dur),
            "uid": getattr(request.state, "app_uid", None),
        }
        # Declared jump: the person states what they attempted; the system verifies
        # the claim (engine_bridge.verify_declared), and the claim itself is the
        # person's label for future training.
        if declared in _DECLARABLE:
            jobs.JOBS[job_id]["declared"] = declared
        if declared_turns in ("1", "2", "3", "4"):
            jobs.JOBS[job_id]["declared_turns"] = int(declared_turns)
        # Explicit consent to use the video for training (default: no). Only with it
        # does the video live longer than the TTL and enter the training set.
        if train_consent == "1":
            jobs.JOBS[job_id]["train_consent"] = True
        # cloud: persist and enqueue commit the volume and spawn the worker (network);
        # in the event loop they would block all requests, so they go to the thread pool
        await run_in_threadpool(jobs._persist, job_id)
        busy = await run_in_threadpool(dispatch._enqueue, job_id, dst)
        if busy is not None:
            return busy
        return JSONResponse({"job": job_id})

    @app.post("/upload_start")
    async def upload_start(request: Request):
        job_id = uuid.uuid4().hex[:12]
        d = jobs.WORK / job_id
        d.mkdir(parents=True, exist_ok=True)
        ext = ((request.headers.get("x-app-ext")) or "webm").lower().strip(".")
        if ext not in ("webm", "mp4", "mkv"):
            ext = "webm"
        meta = {
            "ext": ext,
            "parts": 0,
            "bytes": 0,
            "started": time.time(),
            "uid": getattr(request.state, "app_uid", None),
        }
        (d / "parts.json").write_text(_json_dumps(meta), encoding="utf-8")
        if hooks._warm_hook is not None:
            # the cloud hook commits the volume and starts the live worker: network
            # calls, so not in the event loop
            def _call_warm():
                try:
                    hooks._warm_hook(job_id)
                except TypeError:
                    hooks._warm_hook()

            try:
                await run_in_threadpool(_call_warm)
            except Exception as _we:
                print(f"[warm] {_we}", file=sys.stderr)
        elif os.environ.get("JS_LIVE_LOCAL", "1") == "1":
            # local server (no cloud warm hook): start the same tail live worker as
            # in the cloud instead of the preview-run fallback; /status sees it via
            # hooks._live_status.
            if hooks._live_status is None:
                hooks._live_status = live_local._live_local_status
            try:
                live_local._start_live_local(job_id, d)
            except Exception as _le:
                print(f"[live-local] start {job_id}: {_le}", file=sys.stderr)
        return JSONResponse({"job": job_id})

    @app.post("/upload_part/{job_id}")
    async def upload_part(job_id: str, request: Request, seq: int = 0):
        from ..upload_parts import LOCK as parts_lock
        from ..upload_parts import append_part, save_meta

        d = jobs.WORK / job_id
        mp = d / "parts.json"
        if seq < 0:
            return JSONResponse({"error": "negative sequence"}, status_code=422)
        body = await request.body()
        status, result = await run_in_threadpool(append_part, d, seq, body, parts_max_mb * (1 << 20))
        if status != 200 or result.get("duplicate"):
            return JSONResponse(result, status_code=status)
        meta = json.loads(mp.read_text(encoding="utf-8"))
        before_preview = json.loads(_json_dumps(meta))
        try:
            await run_in_threadpool(
                lambda: preview._maybe_preview(job_id, meta, enabled=live_preview, gap_s=preview_gap_s)
            )
        except Exception as _pe:
            print(f"[preview] {job_id}: {_pe}", file=sys.stderr)

        def _save_preview():
            with parts_lock:
                latest = json.loads(mp.read_text(encoding="utf-8"))
                latest.update(
                    {
                        k: v
                        for k, v in meta.items()
                        if before_preview.get(k) != v and k not in ("parts", "bytes", "part_hashes", "finished")
                    }
                )
                save_meta(mp, latest)

        await run_in_threadpool(_save_preview)
        if hooks._part_hook is not None:
            try:
                # does not block: the bytes of the part with its offset go to the live
                # worker's queue (append_part writes strictly sequentially:
                # offset = bytes - len(body))
                hooks._part_hook(job_id, int(result["bytes"]) - len(body), body)
            except Exception as _he:
                print(f"[part_hook] {job_id}: {_he}", file=sys.stderr)
        ps = preview._preview_status(meta)
        return JSONResponse({**result, "found": ps["found"], "preview_state": ps["preview_state"]})

    finish_locks = weakref.WeakValueDictionary()

    @app.post("/upload_finish/{job_id}")
    async def upload_finish(job_id: str, request: Request, duration_s: float = 0.0):
        # Parallel finish retries of one job neither remux nor enqueue twice.
        lock = finish_locks.get(job_id)
        if lock is None:
            lock = asyncio.Lock()
            finish_locks[job_id] = lock
        async with lock:
            return await _finish_upload(job_id, request)

    async def _finish_upload(job_id: str, request: Request):
        existing = await run_in_threadpool(
            jobs._job, job_id
        )  # cloud: shared dict / volume reload, not in the event loop
        if existing and existing.get("state") in ("queued", "scanning", "running", "done"):
            # A retry of /finish after losing the HTTP response does not remux the file
            # and does not order the same paid analysis a second time.
            return JSONResponse({"job": job_id, "duration_s": existing.get("duration"), "state": existing["state"]})
        d = jobs.WORK / job_id
        mp = d / "parts.json"
        if not mp.is_file():
            return JSONResponse({"error": "unknown upload"}, status_code=404)
        from ..upload_parts import LOCK as parts_lock
        from ..upload_parts import save_meta

        def _seal():
            with parts_lock:
                meta = json.loads(mp.read_text(encoding="utf-8"))
                if meta.get("bytes", 0):
                    meta["finished"] = True
                    save_meta(mp, meta)
                return meta

        meta = await run_in_threadpool(_seal)
        if hooks._live_end_hook is not None and meta.get("finished"):
            try:
                hooks._live_end_hook(job_id)
            except Exception as _le:
                print(f"[live_end] {job_id}: {_le}", file=sys.stderr)
        src = d / f"input.{meta['ext']}"
        if not src.is_file() or meta["bytes"] == 0:
            return JSONResponse({"error": "empty upload"}, status_code=422)
        # A readable MP4/MOV is kept without remux: moving it into MKV can change the
        # edit list and add a final frame to the analysis (223 -> 224).
        source_duration = await run_in_threadpool(jobs._probe_duration, src)
        # A MediaRecorder WebM without duration needs a remux for the index.
        dst = d / "clip.mkv"

        def _remux():
            r = subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-c", "copy", str(dst)],
                capture_output=True,
                text=True,
                timeout=300,
            )
            return r.returncode == 0 and dst.is_file() and dst.stat().st_size > 0

        ok = await run_in_threadpool(_remux) if source_duration is None else False
        video = dst if ok else src
        dur = await run_in_threadpool(jobs._probe_duration, video) if ok else source_duration
        if dur is None or dur > jobs._MAX_DURATION_S:
            return JSONResponse(
                {"error": f"not a readable video or longer than {jobs._MAX_DURATION_S:.0f} s"}, status_code=422
            )
        jobs._sweep_old_jobs()
        jobs.JOBS[job_id] = {
            "state": "queued",
            "video": str(video),
            "name": video.name,
            "started": time.time(),
            "duration": float(dur),
            "uid": getattr(request.state, "app_uid", None),
        }
        await run_in_threadpool(jobs._persist, job_id)
        busy = await run_in_threadpool(dispatch._enqueue, job_id, video)
        if busy is not None:
            return busy
        return JSONResponse({"job": job_id, "duration_s": dur, "remuxed": ok})
