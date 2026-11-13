"""Character demo videos: publication gates, variants, cues, poster, list."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import threading
from pathlib import Path

from fastapi import APIRouter

from jumpsight_core.paths import MASCOT_WORK_DIR, STATE_DIR

from ..core import load_kb

router = APIRouter()


POSTERS = STATE_DIR / "posters"
MASCOT_WORK = MASCOT_WORK_DIR
# The mascot package publishes folders named <prefix><id> under MASCOT_WORK/out.
CLIP_PREFIX = os.environ.get("JS_CLIP_PREFIX", "clip_")


def _mascot_ok(stem: str) -> bool:
    """Whether the character passed its own subsystem checks.

    Measured: of four rendered clips only one passed the gates; the rest failed on `jitter_vs_source` (2.4-4.6
    against a threshold of 1.6) and `residual_penetration_mm` (70 against 1.0), yet the files look finished.
    A known-worse demo must not be shown silently, so the list of ready demos is built from report.json, not
    from the presence of an mp4.
    """
    rep = MASCOT_WORK / "out" / stem / "report.json"
    if not rep.exists():
        return False
    try:
        return bool(json.loads(rep.read_text(encoding="utf-8")).get("ok"))
    except Exception:
        return False


_DUR_CACHE: dict = {}


def _media_duration_s(path: Path) -> float | None:
    """Video duration via ffprobe, cached by (size, mtime)."""
    try:
        st = path.stat()
    except OSError:
        return None
    key = (str(path), st.st_size, st.st_mtime_ns)
    if key in _DUR_CACHE:
        return _DUR_CACHE[key]
    val = None
    try:
        import subprocess

        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True,
            text=True,
            timeout=20,
        ).stdout.strip()
        val = float(out) if out else None
    except Exception:
        val = None
    _DUR_CACHE[key] = val
    if len(_DUR_CACHE) > 200:
        _DUR_CACHE.pop(next(iter(_DUR_CACHE)))
    return val


# A duration mismatch above this tolerance means the demo is a different clip. Measured on seven rendered
# demos: five matched their source to <= 0.02 s (26.0/25.98, 30.33/30.32, 21.87/21.85, 30.83/30.83,
# 31.4/31.4) and two differed by seconds (26.2/31.7, 30.37/5.99).
_MASCOT_DUR_TOL_S = 0.25


_SHA_CACHE: dict = {}


def _sha256(path: Path) -> str | None:
    """sha256 of a file, cached by (size, mtime): computing it each time is expensive."""

    try:
        st = path.stat()
    except OSError:
        return None
    key = (str(path), st.st_size, st.st_mtime_ns)
    if key in _SHA_CACHE:
        return _SHA_CACHE[key]
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return None
    _SHA_CACHE[key] = h.hexdigest()
    if len(_SHA_CACHE) > 100:
        _SHA_CACHE.pop(next(iter(_SHA_CACHE)))
    return _SHA_CACHE[key]


def _mascot_binding_ok(stem: str, mascot: Path) -> bool:
    """Whether the report describes this exact file.

    When the report carries a fingerprint (`binding`), the size and sha256 must match the file about to be
    shown. A report without a fingerprint does not block display (older renders have none), but it proves
    less, and a mismatch is logged.
    """
    rep = MASCOT_WORK / "out" / stem / "report.json"
    try:
        data = json.loads(rep.read_text(encoding="utf-8"))
    except Exception:
        return False
    b = (data.get("binding") or {}).get("video") or {}
    if not b:
        return True  # report without a fingerprint
    try:
        size = mascot.stat().st_size
    except OSError:
        return False
    if b.get("size") is not None and int(b["size"]) != size:
        print(
            f"[mascot] {stem}: file size {size} vs {b['size']} in the report - not the clip the report describes",
            flush=True,
        )
        return False
    if b.get("sha256") and _sha256(mascot) != b["sha256"]:
        print(f"[mascot] {stem}: file hash does not match the report - not the clip the report describes", flush=True)
        return False
    return True


def _mascot_matches_report(stem: str, mascot: Path) -> bool:
    """Whether the demo is the clip the report describes.

    The report's `ok` is not tied to a file, so the demo's duration must match
    the source duration recorded at publication (`lesson_duration_s`).
    """
    d_m = _media_duration_s(mascot)
    try:
        d_l = float(
            json.loads((MASCOT_WORK / "out" / stem / "report.json").read_text(encoding="utf-8"))["lesson_duration_s"]
        )
    except Exception:
        d_l = None
    if d_m is None or d_l is None:
        print(f"[mascot] {stem}: duration cannot be verified (demo {d_m}, source {d_l}) - not shown", flush=True)
        return False
    if abs(d_m - d_l) > _MASCOT_DUR_TOL_S:
        print(f"[mascot] {stem}: demo {d_m:.2f} s vs source {d_l:.2f} s - a different clip, not shown", flush=True)
        return False
    return True


_AUDIO_CACHE: dict = {}


def _media_has_audio(path: Path) -> bool | None:
    """Whether the file has an audio track (ffprobe, cached by (size, mtime)).
    None means the check could not be done."""
    try:
        st = path.stat()
    except OSError:
        return None
    key = (str(path), st.st_size, st.st_mtime_ns)
    if key in _AUDIO_CACHE:
        return _AUDIO_CACHE[key]
    val = None
    try:
        import subprocess

        out = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        val = bool(out.stdout.strip()) if out.returncode == 0 else None
    except Exception:
        val = None
    _AUDIO_CACHE[key] = val
    if len(_AUDIO_CACHE) > 200:
        _AUDIO_CACHE.pop(next(iter(_AUDIO_CACHE)))
    return val


def _mascot_character_only(stem: str, mascot: Path) -> bool:
    """Whether the clip contains only the character.

    Policy: original instructional videos are not shown anywhere. Older demo layouts (1920x1080 "character +
    lesson panel") contain the coach's frames and the rink's sound, so two independent conditions apply: the
    report must state layout=character-only, and an audio track is allowed only as declared synthetic
    (audio=tts, lesson_audio=false). Unverifiable means not shown.
    """
    rep = MASCOT_WORK / "out" / stem / "report.json"
    try:
        data = json.loads(rep.read_text(encoding="utf-8"))
    except Exception:
        return False
    if data.get("layout") != "character-only" or data.get("lesson_footage") is not False:
        print(
            f"[mascot] {stem}: the report does not declare layout=character-only - "
            f"old layout with source footage, not shown",
            flush=True,
        )
        return False
    has_audio = _media_has_audio(mascot)
    if has_audio is None:
        print(f"[mascot] {stem}: audio track cannot be checked - not shown", flush=True)
        return False
    # Narration is allowed only in synthetic form (a neural voice
    # reads the instructions); the report must declare this. A file with
    # sound without such a declaration is coach filming.
    if has_audio and not (data.get("audio") == "tts" and data.get("lesson_audio") is False):
        print(
            f"[mascot] {stem}: has an audio track but the report does not declare audio=tts - "
            f"not a character-only clip, not shown",
            flush=True,
        )
        return False
    return True


def _mascot_file(drill_id: str) -> Path | None:
    """Character video for a drill, if it has already been rendered.

    The character is computed by a separate subsystem (lesson video -> skeleton -> rig -> Blender) and lands
    under the mascot work folder. This is only a lookup of the finished file: a render takes minutes and is
    never done per request.
    """
    drills, _ = load_kb()
    d = next((x for x in drills if x.get("id") == drill_id), None)
    return _mascot_file_for(d)


def _mascot_file_for(d: dict | None) -> Path | None:
    """Published demo of a drill (`<prefix><id>`), if it exists and passes every gate."""
    if not d or not d.get("id"):
        return None
    stem = CLIP_PREFIX + d["id"]
    f = MASCOT_WORK / "out" / stem / f"{stem}_mascot.mp4"
    if not (f.exists() and _mascot_ok(stem)):
        return None
    if not _mascot_matches_report(stem, f):
        return None
    if not _mascot_binding_ok(stem, f):
        return None
    return f if _mascot_character_only(stem, f) else None


def _mascot_voice_note(mascot: Path) -> str | None:
    """Caption under the demo if the voice is synthesized: "AI-generated voice"."""
    try:
        rep = json.loads((mascot.parent / "report.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    return rep.get("voice_disclosure") if rep.get("audio") == "tts" else None


def _mascot_variant(drill_id: str, lang: str) -> Path | None:
    """The demo file in the interface language.

    Narration is synthesized separately for each language over the same video. The main file
    `<stem>_mascot.mp4` is English; `<stem>_mascot.<lang>.mp4` is described in report.json variants[lang] with
    its own sha256. A variant without a matching fingerprint is not served: the main file, which has already
    passed every check in _mascot_file, is returned instead."""
    base = _mascot_file(drill_id)
    if base is None or lang in ("", "en"):
        return base
    stem = base.name.replace("_mascot.mp4", "")
    try:
        rep = json.loads((base.parent / "report.json").read_text(encoding="utf-8"))
        v = (rep.get("variants") or {}).get(lang) or {}
    except Exception:
        return base
    f = base.parent / str(v.get("file") or "")
    if not v or not f.is_file() or f.parent != base.parent:
        return base
    if v.get("size") is not None and int(v["size"]) != f.stat().st_size:
        print(f"[mascot] {stem}: variant {lang} size does not match the report, serving the main file", flush=True)
        return base
    if v.get("sha256") and _sha256(f) != v["sha256"]:
        print(f"[mascot] {stem}: variant {lang} hash does not match the report, serving the main file", flush=True)
        return base
    return f


def _mascot_cues(drill_id: str, lang: str) -> list[dict]:
    """Narration lines with timing, for subtitles under the demo (phone without sound)."""
    base = _mascot_file(drill_id)
    if base is None:
        return []
    try:
        rep = json.loads((base.parent / "report.json").read_text(encoding="utf-8"))
        cues = rep.get("cues") or {}
        rows = cues.get(lang) or cues.get("en") or []
        return [{"t": float(c["t"]), "text": str(c["text"])} for c in rows]
    except Exception:
        return []


_MASCOT_CACHE: dict = {"t": 0.0, "v": []}


def _mascot_list_compute() -> list[str]:
    drills, _ = load_kb()
    out = []
    for d in drills:
        did = d.get("id")
        if not did:
            continue
        # The same rules as the display (gates, duration, fingerprint, character-only, synthetic sound
        # only); otherwise the "3D" badge would stand beside a drill whose demo the player refuses to serve.
        if _mascot_file_for(d) is not None:
            out.append(did)
    return out


def _mascot_list_refresh() -> None:
    import time as _t

    try:
        out = _mascot_list_compute()
        _MASCOT_CACHE.update(t=_t.time(), v=out)
        with contextlib.suppress(OSError):
            (MASCOT_WORK / "mascot_list.json").write_text(json.dumps(out), encoding="utf-8")
    finally:
        _MASCOT_CACHE["busy"] = False


@router.get("/mascot_list")
def mascot_list() -> list[str]:
    """Drills for which the character is already ready. The UI asks this once.

    The drill base is read once, not per drill: calling _mascot_file() in a loop parsed drills.yaml 51 times
    (5.1 s per request).

    Full verification (ffprobe twice and sha256 per demo) from a cold disk takes 27 s on 21 lessons. The
    response is therefore instant from the saved list (mascot_list.json in the mascot work folder, which
    survives a restart); the recalculation runs in the background, and a list older than a minute triggers
    one without waiting for it.
    """
    import time as _t

    if not _MASCOT_CACHE["v"] and not _MASCOT_CACHE.get("loaded"):
        _MASCOT_CACHE["loaded"] = True
        try:
            saved = json.loads((MASCOT_WORK / "mascot_list.json").read_text(encoding="utf-8"))
            if isinstance(saved, list):
                _MASCOT_CACHE.update(t=0.0, v=[str(x) for x in saved])
        except Exception:
            pass
    stale = _t.time() - _MASCOT_CACHE["t"] >= 60
    if stale and not _MASCOT_CACHE.get("busy"):
        _MASCOT_CACHE["busy"] = True
        if _MASCOT_CACHE["v"]:
            threading.Thread(target=_mascot_list_refresh, daemon=True).start()
        else:
            _mascot_list_refresh()  # nothing to show: we count now
    return _MASCOT_CACHE["v"]


@router.get("/mascot_face/{drill_id}.jpg")
def mascot_face(drill_id: str):
    """Coach portrait: a clean frame from Blender, without the service panel.

    The finished video (`*_mascot.mp4`) has burned-in measurement captions and an inset of the source video.
    The frames it was assembled from lie beside it and are clean, so one of them is used without a re-render.
    """
    from fastapi.responses import FileResponse, Response

    drills, _ = load_kb()
    d = next((x for x in drills if x.get("id") == drill_id), None)
    if not d:
        return Response(status_code=404)
    stem = CLIP_PREFIX + d["id"]
    frames = sorted((MASCOT_WORK / "out" / stem / "frames").glob("f_*.png"))
    if not frames:
        return Response(status_code=404)
    # A frame from the middle: at the start and the end the skater is often facing away.
    return FileResponse(frames[len(frames) // 2], media_type="image/png")


@router.get("/mascot/{drill_id}")
def mascot_video(drill_id: str, lang: str = ""):
    from fastapi.responses import FileResponse, Response

    f = _mascot_variant(drill_id, lang)
    if not f:
        return Response(status_code=404)
    return FileResponse(f, media_type="video/mp4")


@router.get("/kb/poster/{drill_id}.jpg")
def poster(drill_id: str):
    """Drill poster: a frame from the character demo (cached on disk).

    The only source is the character demo; without it there is no poster (404, the card draws a placeholder)."""
    import subprocess

    from fastapi.responses import FileResponse, Response

    POSTERS.mkdir(parents=True, exist_ok=True)
    cached = POSTERS / f"{drill_id}.jpg"
    v = _mascot_file(drill_id)
    if not v:
        return Response(status_code=404)
    # The cache lives as long as the demo does: after a re-render the old poster would show a frame
    # that is no longer in the video.
    stale = cached.exists() and cached.stat().st_mtime < v.stat().st_mtime
    if not cached.exists() or stale:
        # The poster moment is chosen at publication (report.json poster_t: the widest pose that is fully
        # in frame); without it, the 12th second.
        t = 12.0
        try:
            rep = json.loads((v.parent / "report.json").read_text(encoding="utf-8"))
            if isinstance(rep.get("poster_t"), (int, float)) and rep["poster_t"] > 0:
                t = float(rep["poster_t"])
        except Exception:
            pass
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-ss",
                f"{t:.2f}",
                "-i",
                str(v),
                "-frames:v",
                "1",
                "-vf",
                "scale=480:-1",
                "-y",
                str(cached),
            ],
            timeout=60,
        )
        if not cached.exists():
            return Response(status_code=404)
    return FileResponse(cached, media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})
