"""Production ASGI entry: the analyzer API, the static client and the coach app.
Run with `python -m jumpsight_app.web` (http://127.0.0.1:8000).
"""

from __future__ import annotations

import os

# The analyzer routes come from `jumpsight_app.webapp`; this module adds the client
# from `paths.WEB_DIR`, security headers, health/warm-state endpoints and mounts the
# coach API under /coach.
# Pin the matplotlib backend before any project import: a Tk backend used from
# a worker thread crashes the whole server (Tcl_AsyncDelete).

os.environ["MPLBACKEND"] = "Agg"

import argparse

from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from jumpsight_core import paths

from .webapp import build_app

WEB = paths.WEB_DIR


def build():
    app = build_app()

    # Assets with a hash in the URL are cached; HTML and unversioned addresses
    # are checked on every visit, so edits do not hide in the cache.
    class _VersionedStatic(StaticFiles):
        def file_response(self, *a, **kw):  # noqa: D102
            r = super().file_response(*a, **kw)
            from urllib.parse import parse_qs

            scope = kw.get("scope") or (a[2] if len(a) > 2 else {})
            query = parse_qs(scope.get("query_string", b"").decode("ascii", "ignore"))
            # index adds a content hash to the URL: a repeat visit does not reload JS/CSS.
            r.headers["Cache-Control"] = "public, max-age=31536000, immutable" if query.get("v") else "no-cache"
            return r

    app.mount("/static", _VersionedStatic(directory=str(WEB)), name="static")

    # ── SECURITY HEADERS AND HEALTH CHECK ──────────────
    # Responses carried no security headers. The most sensitive one is
    # Referrer: the "share" link (/coach/s/<token>) carries the token in the address,
    # and a jump from an analysis to an external source would pass it to a foreign site.
    # A full CSP is deliberately not set here: Google sign-in, fonts and inline
    # scripts need a separate allowlist, and an error in it breaks sign-in.
    @app.middleware("http")
    async def _security_headers(request, call_next):
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # 'self', not 'none': the answer screen embeds its own 3D avatar page
        h.setdefault("X-Frame-Options", "SAMEORIGIN")
        h.setdefault("Content-Security-Policy", "frame-ancestors 'self'")
        h.setdefault("Permissions-Policy", "camera=(self), microphone=(self), geolocation=()")
        if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
            h.setdefault("Strict-Transport-Security", "max-age=31536000")
        return response

    @app.get("/healthz")
    def healthz():
        """For availability monitoring: the process is alive and responding. No
        user data; warm-up state is included to tell "alive but still cold" from "ready"."""
        from fastapi.responses import JSONResponse as _JR

        try:
            from .webapp import JOBS as _J

            active = sum(1 for j in list(_J.values()) if j.get("state") in ("queued", "scanning", "running"))
        except Exception:  # noqa: BLE001
            active = None
        return _JR({"ok": True, "jobs_active": active}, headers={"Cache-Control": "no-store"})

    # The loop lives at one address: the coach is a sub-application under /coach, so a
    # phone sees one port, one service worker and one visibility scope for the offline
    # shell (two servers on two ports meant two addresses and CORS between them).
    try:
        from jumpsight_app import coach_host
        from jumpsight_coach.api import app as coach_app

        coach_host.install()

        app.mount("/coach", coach_app)
    except Exception as e:  # noqa: BLE001
        # A silent failure cannot happen here: without this, half the
        # app is missing, and that must be visible in the log, not as "empty in the UI".
        print(f"[web] coach API not mounted: {type(e).__name__}: {e}")

    # Warm-up does not hold the socket. Measured: from process start to the first TCP
    # accept took 82.3 s on a cold file cache (6.1 s on a warm one), and for all this
    # time the browser gets "connection refused", because uvicorn runs
    # @app.on_event("startup") BEFORE binding the socket.
    #
    # Warm-ups are needed (without them the first user paid 31 s for e2e and ~50 s for
    # ONNX), but the server should pay for them while idle. So all three live in ONE
    # background thread. Order matters: torch is imported FIRST and synchronously inside
    # this thread, otherwise the partial-initialization race described in
    # coach/api._warmup comes back.
    _WARM: dict = {"state": "pending", "started": None, "seconds": None, "steps": {}}

    @app.get("/warm_state")
    def warm_state():
        """Warm-up state for the UI: the page is served at once, and it shows
        "models loading" by itself until ready here."""
        return dict(_WARM)

    @app.on_event("startup")
    def _warm_all_background():
        if os.environ.get("JS_SKIP_WARMUP") == "1":
            _WARM.update(state="skipped", seconds=0)
            return
        # API container without models. On Modal the web function has no GPU, and
        # warm-up pulling torch/E2E/jumpsight into a container with a CUDA image but no
        # driver crashes with SIGSEGV (exit 139) and Modal answers "Server has lost track
        # of input". Models are warmed by the GPU worker run_job; the API only accepts
        # files and returns state.
        if os.environ.get("JS_API_ONLY") == "1":
            _WARM.update(state="remote", seconds=0)
            print("[warm] analysis models skipped: JS_API_ONLY=1", flush=True)
            # Chat search (e5-small on CPU) is warmed here too: loading it on the first
            # non-standard question costs the same, later, and the user saw "search is
            # still starting up" (cloud test: 8.5-21.6 s). The SIGSEGV comes from the
            # analysis torch models with CUDA and no driver, not from e5.
            if os.environ.get("JS_CHAT_WARM", "1") == "1":
                from jumpsight_coach.knowledge import warm_fallback

                warm_fallback(background=True)
                print("[warm] chat search in background", flush=True)
            return
        import threading as _th
        import time as _t

        def _step(name: str, fn) -> None:
            t0 = _t.time()
            try:
                fn()
                _WARM["steps"][name] = {"ok": True, "seconds": round(_t.time() - t0, 1)}
            except Exception as e:  # noqa: BLE001
                _WARM["steps"][name] = {
                    "ok": False,
                    "seconds": round(_t.time() - t0, 1),
                    "error": f"{type(e).__name__}: {e}",
                }
                print(f"[warm] {name} failed: {type(e).__name__}: {e}", flush=True)

        def _torch_first():
            import torch  # noqa: F401

        def _coach():
            from jumpsight_coach.api import _warmup

            _warmup()

        def _chat():
            """Only what the chat answer needs beyond the ready branches: e5-small and the LLM client. Full coach warm-up is disabled for memory reasons, and the first non-standard question after startup waited for the model to load (measured 83–100+ s on a machine with 2 GB of free memory; ask itself 5.6 s)."""
            from jumpsight_coach.knowledge import warm_fallback

            warm_fallback()

        def _seq():
            t0 = _t.time()
            _WARM["state"], _WARM["started"] = "warming", t0
            # torch first (partial-initialisation race). The private engine and
            # its live worker are warmed here in the full edition; the public
            # edition has no engine (see jumpsight_app.engine_bridge).
            steps = [("torch", _torch_first)]
            if os.environ.get("JS_WARM_COACH", "0") == "1":
                steps.append(("coach", _coach))
            elif os.environ.get("JS_WARM_CHAT", "1") == "1":
                steps.append(("chat", _chat))
            for name, fn in steps:
                _step(name, fn)
            _WARM["seconds"] = round(_t.time() - t0, 1)
            _WARM["state"] = "ready" if all(s["ok"] for s in _WARM["steps"].values()) else "degraded"
            print(f"[warm] all done in {_WARM['seconds']} s", flush=True)

        _th.Thread(target=_seq, daemon=True).start()

    # ── DRILL VIDEO: HONEST SOURCE RESOLUTION ─────────────────────────
    # Measured on the live database: of 51 drills, 21 have video, while the day's session
    # regularly consists of drills that have none, and an empty player space reads as
    # "this video is not from the coach system."
    # One answer to "what exactly to show" lives here, with the source name:
    #   own     — video of this same drill from the knowledge base
    #   mascot  — rendered character that passed its own gates
    #   related — video of a RELATED drill (shared targets), and this is shown
    #   none    — nothing available, and the reason is stated
    # Inventing video from nowhere is not allowed: a related video is labeled as
    # related, otherwise a person would silently learn a movement from a different drill.
    @app.get("/api/drill_media/{drill_id}")
    def drill_media(drill_id: str, lang: str = ""):
        """What to show under a drill. ONLY the 3D character, or an honest "none".

        Original instructional videos (coach filming) and any "related" videos from the same library are never served: the app is not linked to the lesson source. The character demo is served only when it has passed the gates (coach/api._mascot_file: report.ok, duration match, sha256)."""
        try:
            from jumpsight_coach.api import _mascot_cues, _mascot_file
            from jumpsight_coach.core import load_kb
        except Exception as e:  # noqa: BLE001
            return {"kind": "none", "why": f"coach KB unavailable: {e}"}
        drills, _ = load_kb()
        d = next((x for x in drills if x.get("id") == drill_id), None)
        if not d:
            return {"kind": "none", "why": "no such drill in the knowledge base"}
        try:
            base = _mascot_file(drill_id)
            if base:
                url = f"/coach/mascot/{drill_id}"
                # the speech synthesis terms require telling the person that the voice is
                # generated (65_revoice.py writes voice_disclosure into the report)
                from jumpsight_coach.api import _mascot_voice_note

                return {
                    "kind": "mascot",
                    "url": url,
                    "lang": "en",
                    "cues": _mascot_cues(drill_id, "en"),
                    "voice_note": _mascot_voice_note(base),
                    "drill_id": drill_id,
                    "name": d.get("name"),
                }
        except Exception:  # noqa: BLE001
            pass
        # A session's demo must cover every drill. The demo is of a RELATED drill: the
        # same character, not the lesson video; shared targets, the same place
        # (ice / off-ice), the nearest level. It is labelled "Similar exercise: ..." so
        # the person does not silently learn the movement from a different drill.
        try:
            from jumpsight_coach.api import mascot_list

            demo = set(mascot_list())
            tg = set(d.get("targets") or [])
            best = None
            for x in drills:
                if x.get("id") not in demo or x.get("id") == drill_id:
                    continue
                common = len(tg & set(x.get("targets") or []))
                # only the same place (ice / off-ice): a T-stop on ice must not
                # be shown as a turn demo on the floor
                # place, as in the session (coach/session: kind == off_ice)
                if not common or (x.get("kind") == "off_ice") != (d.get("kind") == "off_ice"):
                    continue
                score = (common, -abs(int(x.get("level") or 1) - int(d.get("level") or 1)))
                if best is None or score > best[0]:
                    best = (score, x)
            if best is not None:
                rel = best[1]
                r_base = _mascot_file(rel["id"])
                if r_base:
                    from jumpsight_coach.api import _mascot_voice_note

                    rel_name = rel.get("name") or rel["id"]
                    return {
                        "kind": "related",
                        "url": f"/coach/mascot/{rel['id']}",
                        "lang": "en",
                        "cues": _mascot_cues(rel["id"], "en"),
                        "voice_note": _mascot_voice_note(r_base),
                        "drill_id": drill_id,
                        "related_id": rel["id"],
                        "related_name": rel_name,
                        "note": f"Similar exercise: {rel_name}",
                    }
        except Exception:  # noqa: BLE001
            pass
        return {"kind": "none", "drill_id": drill_id, "why": "no 3D demo for this drill yet"}

    # ── FAST RETRIEVAL WITHOUT LLM ────────────────────────────────────────
    # MEASURED: POST /coach/ask = 65 s, because the LLM writes the summary.
    # The whole time the chat showed "searching the knowledge base" and nothing else.
    # Retrieval itself takes fractions of a second and already contains what the
    # user came for: an excerpt from the knowledge base and its source. So the answer is two-stage:
    # first what was found, then the summary on top of it. This does not speed up the LLM,
    # it removes the empty wait.
    @app.get("/api/ask_sources")
    def ask_sources(q: str, k: int = 5, lang: str = "en"):
        try:
            import numpy as _np

            from jumpsight_coach import knowledge as K

            rows, emb = K._load()
            v = K._m().encode([f"query: {q}"[:400]], normalize_embeddings=True)
            sims = (emb @ v.T).ravel()
            order = list(_np.argsort(-sims))
            order = order[: max(1, min(int(k), 10))]
            return {
                "hits": [
                    {
                        "source": rows[i].get("source", ""),
                        "url": rows[i].get("url", ""),
                        "text": (rows[i].get("text") or "")[:400],
                        "score": round(float(sims[i]), 3),
                    }
                    for i in order
                ]
            }
        except Exception as e:  # noqa: BLE001
            return {"hits": [], "why": f"{type(e).__name__}: {e}"}

    _ASSET_V: dict = {}

    @app.get("/")
    def index():
        # The content version goes into the static file URL: on Modal mtime = 0, so the
        # Starlette ETag (mtime+size) does not change at the same size, and the
        # browser/service worker would keep stale JS after a deploy.
        import hashlib as _hl
        import re as _re

        from fastapi.responses import HTMLResponse as _HR

        html = (WEB / "index.html").read_text(encoding="utf-8")

        def _v(name: str) -> str:
            f = WEB / name
            try:
                stat = f.stat()
                key = (name, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
                if key not in _ASSET_V:
                    if len(_ASSET_V) > 64:
                        _ASSET_V.clear()
                    _ASSET_V[key] = _hl.md5(f.read_bytes()).hexdigest()[:10]
                return _ASSET_V[key]
            except OSError:
                return "0"

        html = _re.sub(
            r"/static/([A-Za-z0-9_.-]+\.(?:js|css))(?![A-Za-z0-9_.-])",
            lambda m: f"/static/{m.group(1)}?v={_v(m.group(1))}",
            html,
        )
        return _HR(html, headers={"Cache-Control": "no-cache"})

    @app.get("/sw.js")
    def sw():
        # The service worker must sit at the root of the scope, otherwise
        # it does not control "/" and the offline shell does not activate.
        return FileResponse(WEB / "sw.js", media_type="application/javascript", headers={"Cache-Control": "no-cache"})

    @app.get("/privacy")
    def privacy():
        """Privacy policy. The address for requests comes from JS_CONTACT_EMAIL (a production secret), not hardcoded in the repository."""
        import html as _html

        from fastapi.responses import HTMLResponse as _HR

        contact = (
            os.environ.get("JS_CONTACT_EMAIL", "").strip()
            or "the contact address you received with your test invitation"
        )
        page = (WEB / "privacy.html").read_text(encoding="utf-8").replace("{{CONTACT}}", _html.escape(contact))
        return _HR(page, headers={"Cache-Control": "no-cache"})

    @app.get("/favicon.ico")
    def favicon():
        return Response(status_code=204)

    return app


app = build()


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    uvicorn.run(app, host=a.host, port=a.port, log_level="info")


if __name__ == "__main__":
    main()
