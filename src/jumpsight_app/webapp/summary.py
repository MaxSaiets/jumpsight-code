"""Read routes of a finished analysis: `/summary`, `/data`, `/media`,
`/demo_jobs` and the owner's `/train_consent`.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from jumpsight_core.evidence import normalize_result, summary_error_checks

from . import jobs

_GCN_TO_NAME = {"Toeloop": "Toe loop"}
_NORM_DEG_S = {"doubles": 1273.0, "triples": 1465.0}  # Bruening 2018


def _event(j, peak):
    if peak == "null":
        peak = "None"
    for e in j.get("events") or []:
        if str(e.get("peak_frame")) == str(peak):
            return e
    return None


def _rate_fields(ro: dict, call: dict) -> dict:
    """Rotation speed + an honest comparison with the norm (or silence)."""
    m = (ro or {}).get("rate_rev_s")
    if not isinstance(m, dict) or m.get("value") is None:
        return {}
    deg = float(m["value"]) * 360.0
    band = m.get("band68")
    lo_hi = (
        [round(float(band[0]) * 360.0), round(float(band[1]) * 360.0)]
        if isinstance(band, (list, tuple)) and len(band) == 2
        else None
    )
    cnt = call.get("count") if isinstance(call, dict) else None
    key = None
    if isinstance(cnt, int):
        key = "triples" if cnt >= 3 else ("doubles" if cnt == 2 else None)
    out = {"rate_deg_s": round(deg), "rate_band_deg_s": lo_hi}
    if key:
        norm = _NORM_DEG_S[key]
        out["rate_norm_deg_s"] = round(norm)
        out["rate_norm_class"] = key
        if lo_hi and lo_hi[0] <= norm <= lo_hi[1]:
            out["rate_vs_norm"] = "same"
        else:
            out["rate_vs_norm"] = "below" if deg < norm else "above"
    return out


def _summary_row(e: dict) -> dict:
    """The /summary row of one event: timing from the event, everything else from
    the normalized result when it exists."""
    from ..engine_bridge import public_jump_view

    row = {
        "peak_frame": e.get("peak_frame"),
        "t_s": e.get("t_s"),
        "takeoff_s": e.get("takeoff_s"),
        "landing_s": e.get("landing_s"),
        "time_source": e.get("time_source") or "frame_rate_estimate",
        "state": e["state"],
        "seconds": e.get("seconds"),
        # key of the analysis for derived data (3D, journal); without it the client
        # substituted the job id and found nothing
        "stem": e.get("stem"),
        "rank": e.get("rank"),
        "error": e.get("error"),
        "render_error": e.get("render_error"),
    }
    r = normalize_result(e.get("result"))
    if not r:
        return row
    ph, ro = r["phases"], r["rotation"]
    # Completed phases take priority over the preliminary estimate event. Even a
    # null for "unavailable" must displace the FPS estimate.
    if "time_source" in ph:
        row.update(
            t_s=ph.get("takeoff_s"),
            takeoff_s=ph.get("takeoff_s"),
            landing_s=ph.get("landing_s"),
            time_source=ph["time_source"],
        )
    call = ro.get("rotation_count_call") or {}
    nm = r["jump"].get("name_model") or {}
    # One place for the honesty rules: the 'undetermined'-name rule, the
    # suitability of the rotation numbers and the choice of the "top" name are the
    # same in to_result, to_summary_jumps and here (public_jump_view). Before that,
    # /summary lacked the 'undetermined' rule altogether (shown 87%, true 53%).
    pjv = public_jump_view(r["jump"], ro, ph)
    # The skater's track for the "close-up" in the player (engine_bridge.skater_track);
    # older analyses do not have it
    if isinstance(r.get("track"), dict):
        row["track"] = r["track"]
    row.update(
        window=[ph["takeoff"], ph["landing"]],
        air_s=pjv["air_s"],
        rev=pjv["rev"],
        # only for choosing the wording (fragment or slow motion)
        air_s_raw=pjv["air_s_raw"],
        # Height is measured ballistically (h = g*t^2/8: only the flight time is
        # needed, not the frame scale).
        height=ph.get("jump_height_m"),
        # +-68% bands: without them height and flight read as exact measurements
        air_band=ph.get("air_time_ci68"),
        height_band=ph.get("jump_height_ci68"),
        height_withheld=ph.get("jump_height_withheld"),
        band=pjv["band"],
        conf=pjv["conf"],
        # is this number a measurement, or just a number
        rev_usable=pjv["rev_usable"],
        rev_unusable_reason=pjv["rev_unusable_reason"],
        # The exact reason from the engine: the same client text for everyone
        # ("at 30 fps per revolution ~4 frames") is true only for aliasing. In a
        # cache of 124 holds, 27 were aliasing, 48 had a spread wider than half a
        # revolution, 25 had a band including zero, 17 had an implausible flight
        # time, 6 had too few frames in flight.
        rot_reason=pjv["rot_reason"],
        # Rotation speed in flight: a separate channel with its own band, and the
        # only number on screen with an EXTERNAL reference (Bruening 2018). A
        # comparison is called a difference only when the band does not cover the
        # norm, the same as in the advice.
        **_rate_fields(ro, call),
        call=call.get("name"),
        between=call.get("between"),
        turns=pjv["turns"],
        turns_nominal=call.get("nominal"),
        call_family=call.get("family"),
        count_confidence=call.get("confidence"),
        estimated=bool(call.get("estimated")),
        # what the estimate is: between_bands | kinematic | fused
        estimate_kind=call.get("estimate_kind"),
        not_stated_because=call.get("not_stated_because"),
        # `name` stays top-1 (the coach trends and the external regression
        # comparison depend on it); a Lutz vs Flip answer is shown with low
        # confidence, not hidden.
        name=pjv["name"],
        name_conf=r["jump"].get("confidence"),
        # The pair instead of a guessed name: the client shows `name_display` when
        # it is present.
        name_display=pjv["name_display"],
        # When the 'undetermined' rule applies (3+ equal alternatives at low
        # confidence) showing the name is not allowed. Measured on a local cache of
        # 54 clips along the real chain:
        #   top-1 name: shown 87%, correct 77% (11 wrong)
        #   with the flag: shown 70%, correct 89% (4 wrong)
        # Hits are equal (34), wrong ones are three times fewer.
        name_uncertain=pjv["name_uncertain"],
        needs_review=pjv["needs_review"],
        review_reason=pjv["review_reason"],
        # family ("toe" / "edge") when the name cannot be shown (see _family_hint)
        name_family_hint=pjv["name_family_hint"],
        name_is_family=bool(r["jump"].get("name_is_family")),
        name_note=r["jump"].get("alternatives_note"),
        alts=r["jump"].get("alternatives") or [],
        from_model=bool(nm.get("name")),
        family=r["jump"].get("family"),
        torso=ph.get("skater_torso_length_m"),
        # Degraded checks (e.g. the frame scale drifted out of the window) neither
        # claim "clean" nor disappear: a separate list with the reason.
        **summary_error_checks(r),
    )
    return row


def register(app: FastAPI) -> None:
    """Add the read routes to `app`."""

    @app.get("/summary/{job_id}")
    def summary(job_id: str, request: Request):
        """Brief about each jump, for the overview page."""
        j = jobs._job(job_id)
        if not j:
            return JSONResponse({"error": "unknown job"}, status_code=404)
        rows = [_summary_row(e) for e in j.get("events") or []]
        fps = 30.0
        for e in j.get("events") or []:
            r = e.get("result")
            if r:
                fps = (r.get("video") or {}).get("fps") or 30.0
                break
        warn = {k: j[k] for k in jobs._WARN_KEYS if j.get(k)}
        if j.get("declared_turns"):
            from ..engine_bridge import verify_declared_turns

            for row in rows:
                if row.get("state") == "done":
                    row["declared_turns_check"] = verify_declared_turns(
                        row, int(j["declared_turns"]), j.get("declared")
                    )
        if j.get("declared"):
            from ..engine_bridge import verify_declared

            for row, e in zip(rows, j.get("events") or []):
                nm = ((e.get("result") or {}).get("jump") or {}).get("name_model") or {}
                probs = {_GCN_TO_NAME.get(k, k): v for k, v in (nm.get("probs") or {}).items()}
                if row.get("state") == "done":
                    row["declared_check"] = verify_declared({"type_probs": probs or None}, j["declared"])
        return JSONResponse(
            jobs._jsonable(
                {
                    "name": j["name"],
                    "state": j["state"],
                    "jumps": rows,
                    "fps": fps,
                    "declared": j.get("declared"),
                    "declared_turns": j.get("declared_turns"),
                    "demo": bool(j.get("demo")),
                    # The owner can give consent after the numbers are shown, not
                    # only at upload; otherwise the Yes/No label was lost (6 of 7 on
                    # the laptop).
                    "mine": bool(j.get("uid")) and j.get("uid") == getattr(request.state, "app_uid", None),
                    "train_consent": bool(j.get("train_consent")),
                    "spins": j.get("spins") or [],
                    "warnings": warn,
                    "total_frames": (j.get("scan") or {}).get("total_frames"),
                }
            )
        )

    @app.post("/train_consent/{job_id}")
    async def train_consent(job_id: str, request: Request):
        """Explicit consent of the analysis OWNER to training, also after the numbers are shown.

        Consent given only at upload and only together with the jump claim lost almost
        all Yes/No labels shown afterward (6 of 7 were stored
        "without consent"). A coach or a viewer with the link cannot give consent.
        With consent, the video and the pose live longer than the TTL
        (_sweep_old_jobs); withdrawal returns the normal TTL."""
        j = jobs._job(job_id)
        uid = getattr(request.state, "app_uid", None)
        if not j or not uid or j.get("uid") != uid:
            return JSONResponse({"error": "unknown job"}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            body = {}
        on = isinstance(body, dict) and body.get("consent") is True
        j["train_consent"] = on
        jobs.JOBS[job_id] = j
        jobs._persist(job_id)
        return {"ok": True, "train_consent": on}

    @app.get("/demo_jobs")
    def demo_jobs():
        """Analysis examples for a first visit: only the real completed jobs of this
        server, marked by tools/demo_job.py. An empty list is the honest answer "no
        example exists"; the button is then not shown."""
        out = []
        for jid, j in list(jobs.JOBS.items()):
            if j.get("demo") and j.get("state") == "done":
                out.append(
                    {
                        "job": jid,
                        "order": j.get("demo_order", 0),
                        "label_uk": j.get("demo_label_uk") or j.get("name"),
                        "label_en": j.get("demo_label_en") or j.get("name"),
                    }
                )
        out.sort(key=lambda d: (d["order"], d["job"]))
        return JSONResponse(out, headers={"Cache-Control": "no-store"})

    @app.get("/media/{job_id}/{peak}/{kind}")
    def media(job_id: str, peak: str, kind: str):
        j = jobs._job(job_id)
        if not j:
            return JSONResponse({"error": "unknown job"}, status_code=404)
        if kind == "original":
            # A phone .mov is served as video/mp4: Firefox does not accept
            # video/quicktime, although inside it is the same ISO BMFF with H.264 as
            # .mp4, and Chrome and Safari play it.
            if str(j["video"]).lower().endswith(".mov"):
                return FileResponse(j["video"], media_type="video/mp4")
            return FileResponse(j["video"])
        return JSONResponse({"error": "unknown media kind"}, status_code=404)

    @app.get("/data/{job_id}/{peak}")
    def data(job_id: str, peak: str):
        j = jobs._job(job_id)
        e = _event(j, peak) if j else None
        if not e or not e.get("result"):
            return JSONResponse({"error": "not ready"}, status_code=404)
        return JSONResponse(jobs._jsonable(normalize_result(e["result"])))
