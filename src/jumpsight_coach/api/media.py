"""Original clip serving and the 3D avatar (bounded generation queue, data, viewer)."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from jumpsight_core.job_queue import AnalysisQueue, QueueFull
from jumpsight_core.paths import OUTPUT_DIR, REPO_ROOT, WORK_DIR

from .common import _require_stem_access, _valid_stem

router = APIRouter()

# Building the 3D avatar re-runs the pose model. A separate small queue keeps
# this optional view from blocking the analysis of new videos.
_AVATAR_QUEUE = AnalysisQueue(workers=1, pending=2)
_AVATAR_STATE: dict[str, dict] = {}
_AVATAR_LOCK = threading.Lock()


@router.get("/video/{stem}")
def clip_video(stem: str, request: Request):
    """Serve the original jump video, without a drawn skeleton.

    Rendering an annotated copy cost 3.6 s on a 180-frame 576x1024 clip after the verdict was already
    computed, and grows with resolution and length. The render measures nothing: the numbers are shown as
    a card over the original, where they can be selected, translated and shown next to the confidence.
    Results that already have an `{stem}_annotated.mp4` on disk fall back to it.
    """
    from fastapi.responses import FileResponse, Response

    _require_stem_access(stem, request)
    if ".." in stem or "/" in stem or "\\" in stem:
        return Response(status_code=400)
    VID = (".mp4", ".mov", ".webm", ".m4v", ".avi")
    # only files that live inside the platform's own directories are served
    roots = [r.resolve() for r in (REPO_ROOT, WORK_DIR, OUTPUT_DIR)]

    # 1. The exact path from the result itself: the analysis records which
    #    video it actually watched (video.path), the only source without
    #    guessing. A name search would be wrong: the same file name can exist
    #    for several skaters.
    rj = OUTPUT_DIR / f"{stem}_result.json"
    if rj.exists():
        try:
            src = (json.loads(rj.read_text(encoding="utf-8")).get("video") or {}).get("path")
            if src:
                p = Path(src).resolve()
                # the field came from a file on disk: never serve an arbitrary path
                if p.is_file() and p.suffix.lower() in VID and any(p.is_relative_to(r) for r in roots):
                    return FileResponse(p, media_type="video/mp4")
        except Exception:
            pass

    # 2. Results without video.path: the upload folder, where names are unique by construction.
    for d in (WORK_DIR,):
        if not d.is_dir():
            continue
        for f in sorted(d.glob(f"{stem}.*")):
            if f.suffix.lower() in VID:
                return FileResponse(f, media_type="video/mp4")
    # Fallback: the annotated render, when one exists on disk.
    legacy = OUTPUT_DIR / f"{stem}_annotated.mp4"
    if legacy.exists():
        return FileResponse(legacy, media_type="video/mp4")
    return Response(status_code=404)


def _avatar_path(stem: str) -> Path:
    return OUTPUT_DIR / f"{stem}_avatar3d.json"


def _analysis_result_path(stem: str) -> Path:
    return OUTPUT_DIR / f"{stem}_result.json"


def _avatar_is_current(stem: str) -> bool:
    """One freshness predicate for the API and the generator.

    A video replaced under the same name must not show the old avatar.
    """
    from jumpsight_coach.integration import HOST

    avatar, result = _avatar_path(stem), _analysis_result_path(stem)
    if HOST.avatar_cache_is_current is None or not avatar.exists() or not result.exists():
        return False
    try:
        video = (json.loads(result.read_text(encoding="utf-8")).get("video") or {}).get("path") or ""
    except (OSError, ValueError, TypeError):
        video = ""
    return HOST.avatar_cache_is_current(avatar, result, Path(video or "missing"))


@router.post("/avatar3d/{stem}/generate", status_code=202)
def avatar3d_generate(stem: str, request: Request):
    """Put the derived 3D view into the bounded queue."""

    _require_stem_access(stem, request)
    if not _valid_stem(stem):
        raise HTTPException(status_code=400, detail="bad analysis id")
    if _avatar_is_current(stem):
        return {"state": "ready"}
    if not _analysis_result_path(stem).exists():
        raise HTTPException(status_code=404, detail="analysis result not found")

    def work():
        with _AVATAR_LOCK:
            _AVATAR_STATE[stem] = {"state": "running"}
        try:
            from jumpsight_coach.integration import HOST

            if HOST.avatar_generate is None:
                raise RuntimeError("no avatar generator is installed by the host")
            msg = HOST.avatar_generate(stem)
            state = "ready" if _avatar_is_current(stem) else "unavailable"
            with _AVATAR_LOCK:
                _AVATAR_STATE[stem] = {"state": state, "detail": msg}
        except Exception as exc:
            with _AVATAR_LOCK:
                _AVATAR_STATE[stem] = {"state": "failed", "detail": f"{type(exc).__name__}: {exc}"}

    try:
        accepted = _AVATAR_QUEUE.submit(stem, work)
    except QueueFull:
        return JSONResponse({"state": "busy"}, status_code=503, headers={"Retry-After": "10"})
    with _AVATAR_LOCK:
        if accepted:
            # A terminal mark (failed/unavailable) left by a previous attempt must not be returned for a job
            # that was just accepted: the client would stop polling and report the 3D view unavailable.
            if (_AVATAR_STATE.get(stem) or {}).get("state") in ("failed", "unavailable"):
                _AVATAR_STATE.pop(stem, None)
            _AVATAR_STATE.setdefault(stem, {"state": "queued"})
        return dict(_AVATAR_STATE.get(stem) or {"state": "queued"})


@router.get("/avatar3d/{stem}/status")
def avatar3d_generation_status(stem: str, request: Request):
    _require_stem_access(stem, request)
    if not _valid_stem(stem):
        raise HTTPException(status_code=400, detail="bad analysis id")
    if _avatar_is_current(stem):
        return {"state": "ready"}
    with _AVATAR_LOCK:
        return dict(_AVATAR_STATE.get(stem) or {"state": "absent"})


@router.head("/avatar3d/{stem}", include_in_schema=False)
@router.get("/avatar3d/{stem}", operation_id="get_avatar3d_data")
def avatar3d_data(stem: str, request: Request):
    """Character skeleton: 15 joints per frame plus the measured body angle.

    The client checks that pose data exists with a HEAD request before showing the 3D button, so the route
    answers HEAD as well as GET (`@router.get` alone registers GET only and a HEAD gets 405). Both return the
    same 200/404; HEAD has no body.
    """
    from fastapi.responses import FileResponse, Response

    _require_stem_access(stem, request)
    if not _valid_stem(stem):
        return Response(status_code=400)
    f = _avatar_path(stem)
    if not _avatar_is_current(stem):
        return Response(status_code=404)
    return FileResponse(f, media_type="application/json")


@router.head("/avatar/{stem}", include_in_schema=False)
@router.get("/avatar/{stem}", operation_id="get_avatar_page")
def avatar_page(stem: str, request: Request):
    """The 3D character viewer page. HEAD is answered for the same existence check as /avatar3d/{stem}."""
    from fastapi.responses import Response

    _require_stem_access(stem, request)
    if ".." in stem or "/" in stem:
        return Response(status_code=400)
    p = Path(__file__).parent.parent / "avatar.html"
    if not p.exists():
        return Response(status_code=404)
    return HTMLResponse(p.read_text(encoding="utf-8"))
