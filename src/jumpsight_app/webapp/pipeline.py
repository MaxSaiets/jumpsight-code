"""The analysis job: scan a video with the engine, build the per-attempt events,
and write the journal, training-pose and label side files.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from pathlib import Path

from . import early, jobs, live_local


def _prescan_job(job_id: str, video: Path):
    """The user context belongs to the task, not to the whole life of the queue thread."""
    from jumpsight_coach.userctx import reset_uid, set_uid

    token = set_uid(jobs.JOBS[job_id].get("uid"))
    try:
        from ..engine_bridge import run_with_focus_snapshot

        return run_with_focus_snapshot(lambda: _prescan_job_impl(job_id, video))
    finally:
        reset_uid(token)


def _engine_event_handler(job_id: str):
    """Callback for live engine events: "attempt found" is visible at about the 9th
    second, not together with the verdict at the 13th. The jumps row appears in
    /summary with state=running as soon as the windows are confirmed."""
    early_state: dict = {}

    def _on_ev(ev):
        k = ev.get("event")
        j = jobs.JOBS.get(job_id) or {}
        if k == "media.probe":
            j["stage"] = "probe"
            j["fps"] = ev.get("fps") or 30.0
            early_state["fps"] = ev.get("fps")
            jobs._persist(job_id)
        elif k == "attempts.confirmed":
            j["stage"] = "pose"
            rows = []
            for w in ev.get("windows") or []:
                if w.get("status") != "confirmed":
                    continue
                mid = int(((w.get("f0") or 0) + (w.get("f1") or 0)) / 2)
                rows.append(
                    {
                        "peak_frame": mid,
                        "t_s": round((w.get("f0") or 0) / (j.get("fps") or 30.0), 2),
                        "state": "running",
                    }
                )
            if rows:
                j["events"] = rows
            confirmed = early.early_from_confirmed(ev, early_state.get("fps"))
            if confirmed is not None:
                j["early"] = confirmed
            jobs._persist(job_id)
        elif k == "attempt.timing":
            timed = early.early_with_timing(j.get("early"), ev)
            if timed is not None:
                j["early"] = timed
            if timed is not None or j.get("stage") != "verdict":
                j["stage"] = "verdict"
                jobs._persist(job_id)

    return _on_ev


def _write_attempt_history(job_id: str, video: Path, fps, att: dict, ev: dict, n_prev: int) -> None:
    """Journal record and coach result file of one analysed attempt.

    Runs during a recording (`preview_of`) are not written to the journal.
    """
    from jumpsight_coach.jobs import OUT as coach_out
    from jumpsight_coach.jobs import add_history_jumpsight

    add_history = (lambda *_a, **_k: None) if (jobs.JOBS.get(job_id) or {}).get("preview_of") else add_history_jumpsight
    # A unique stem per ATTEMPT: dedup in the journal keys on the stem alone, and
    # without attempt_id several jumps of one video would merge into one record.
    aid = att.get("attempt_id") or (n_prev + 1)
    stem = jobs.attempt_stem(job_id, video, aid)
    # The stem reaches the client: the "3D avatar" button requests
    # /coach/avatar3d/{stem}, and the files on disk are named
    # out/<video>_att<N>_result.json, so a job id would never find them.
    ev["stem"] = stem
    add_history(stem, ev["result"], video_path=video, attempt_id=aid, job_id=job_id)
    # /coach/today and /coach/plan look for out/{stem}_result.json, but the engine
    # does not write such a file (it is the format of the older pipeline). The same
    # dict that goes into the journal is written; coach.load_profile() recognizes
    # "engine": "jumpsight" and reads rotation_count_call and checked_and_clean.
    coach_out.mkdir(parents=True, exist_ok=True)
    # /coach/video/{stem} restores the clip ONLY by the video.path field of the
    # result, and names in uploads/ carry a job_id prefix, so the lookup by stem
    # does not work. The path is known only here, so it goes to the FILE (the
    # client response does not need a local path). fps is known here too: without
    # it the path restoration derived it from (landing-takeoff)/air_time_s and gave
    # another take-off time than the fresh analysis (2.88 s vs 2.98 s).
    res_file = dict(jobs._jsonable(ev["result"]))
    with contextlib.suppress(Exception):
        res_file["video"] = {"path": str(Path(video).resolve()), "fps": fps}
    (coach_out / f"{stem}_result.json").write_text(json.dumps(res_file, ensure_ascii=False), encoding="utf-8")


def _write_unmeasured_history(job_id: str, video: Path, events: list) -> None:
    """No upload disappears without a trace: a video with no usable attempt is also
    a journal record, with the reason and without the right to enter the trend."""
    from jumpsight_coach.jobs import add_history_unmeasured

    add_history = (
        (lambda *_a, **_k: None) if (jobs.JOBS.get(job_id) or {}).get("preview_of") else add_history_unmeasured
    )
    why = "no jump found" if not events else "attempts found, but none measured"
    add_history(
        jobs.attempt_stem(job_id, video, 0),
        reason=("no_jump_found" if not events else "attempts_not_analyzed"),
        detail=why,
        video_path=video,
    )


def _save_pose_windows(job_id: str, report: dict) -> None:
    """Training input of the name model: the pose_window of each attempt, exactly
    what the model sees during the analysis, so that fine-tuning has no input
    mismatch with production.

    Written for EVERY analysis, not only for those with consent, because consent
    given after the reveal (/train_consent) would otherwise have no pose. The pose
    lies in the analysis folder beside the video and is cleaned up with it by the
    same TTL; training uses it only with consent."""
    for n, att in enumerate(report.get("attempts") or [], 1):
        pw = att.get("pose_window") or {}
        if not pw.get("kpts"):
            continue
        try:
            (jobs.WORK / job_id / f"pose_att{att.get('attempt_id') or n}.json").write_text(
                json.dumps(jobs._jsonable({k: pw.get(k) for k in ("kpts", "scores", "fps", "pts", "pts_observed")})),
                encoding="utf-8",
            )
        except Exception as _pe:
            print(f"[train] pose save failed: {_pe}", file=sys.stderr)


def _write_declared_label(job_id: str, events: list) -> None:
    """The person's claim is a label. The jump declared before the analysis is a
    pre_reveal testimony (the name BEFORE the numbers are shown, with no link to the
    system's answer): the most valuable source of labels. It is written for the
    attempt that is shown first."""
    declared = (jobs.JOBS.get(job_id) or {}).get("declared")
    top = min(
        (e for e in events if e.get("state") == "done" and e.get("stem")),
        key=lambda e: e.get("rank") if isinstance(e.get("rank"), int) else 99,
        default=None,
    )
    declared_turns = (jobs.JOBS.get(job_id) or {}).get("declared_turns")
    if (declared or declared_turns) and top is not None and not (jobs.JOBS.get(job_id) or {}).get("preview_of"):
        try:
            from jumpsight_coach.api import VerdictFeedbackIn
            from jumpsight_coach.api import verdict_feedback as record_feedback

            record_feedback(
                VerdictFeedbackIn(stem=top["stem"], jump=declared, turns=declared_turns, source="pre_reveal")
            )
        except Exception as _de:
            print(f"[declared] label write failed: {_de}", file=sys.stderr)


def _generate_avatars(job_id: str, video: Path, report: dict) -> None:
    """Opt-in 3D reconstruction (JS_AVATAR3D=1). It reruns MediaPipe for each
    attempt and holds the scarce analysis worker, so the main analysis does not pay
    for a 3D view that most users do not open."""
    job = jobs.JOBS[job_id]
    if os.environ.get("JS_AVATAR3D", "0") == "1":
        job["avatar3d_status"] = "generating"
        try:
            from ..avatar_generator import generate

            messages = []
            for n, att in enumerate(report.get("attempts") or [], 1):
                if (att.get("status") or "") != "analyzed":
                    continue
                stem = jobs.attempt_stem(job_id, video, att.get("attempt_id") or n)
                msg = generate(stem)
                messages.append(msg)
                print(f"[avatar3d] {stem}: {msg}", file=sys.stderr)
            job["avatar3d_status"] = (
                "ready" if messages and all(m.startswith("ok:") for m in messages) else "unavailable"
            )
        except Exception as _ge:
            job["avatar3d_status"] = "failed"
            print(f"[avatar3d] {type(_ge).__name__}: {_ge}", file=sys.stderr)
    else:
        job["avatar3d_status"] = "disabled"
    jobs._persist(job_id)


def _build_events(job_id: str, video: Path, report: dict, jb) -> list[dict]:
    fps = (report.get("clip") or {}).get("fps_effective") or 30.0
    votes: dict = {}
    rows = jb.to_summary_jumps(report, fps, vote_cache=votes)
    events: list[dict] = []
    for row, att in zip(rows, report.get("attempts") or []):
        ev = {
            "peak_frame": row["peak_frame"],
            "t_s": row["t_s"],
            "state": row["state"],
            "takeoff_s": row.get("takeoff_s"),
            "landing_s": row.get("landing_s"),
            "time_source": row.get("time_source"),
            # The rank is computed from CONTENT (one source of truth for the display
            # order of attempts). Without it clients sorted blindly, and an attempt
            # without a count could come first (measured on the demo Axel: Axel/None
            # was shown ahead of Axel/2.152/medium).
            "rank": row.get("rank"),
            "seconds": report.get("latency_s"),
        }
        if row["state"] == "done":
            ev["result"] = jb.to_result(report, att, vote_cache=votes)
            try:
                _write_attempt_history(job_id, video, fps, att, ev, len(events))
            except Exception as _he:
                print(f"[jumpsight] history write failed: {_he}", file=sys.stderr)
        else:
            ev["error"] = row.get("why")
        events.append(ev)
    return events


def _prescan_job_impl(job_id: str, video: Path):
    """Find ALL takeoffs and analyze each one.

    The whole video cannot be run: on 57 seconds that is twenty minutes and a
    MemoryError for twenty useful frames. But one jump is not enough for the coach
    either; the whole program is needed. So a cheap scan first finds all takeoffs,
    then each is analyzed by the full pipeline, one at a time, and results appear as
    they become ready.
    """
    jobs.JOBS[job_id].update(state="scanning")
    jobs._persist(job_id)
    from .. import engine_bridge as _jb

    if not _jb.available():
        msg = "analysis engine is not available: " + _jb.unavailable_reason()
        print(f"[engine] {msg}", file=sys.stderr, flush=True)
        jobs.JOBS[job_id].update(state="error", error_code="ENGINE_UNAVAILABLE", error=msg)
        jobs._persist(job_id)
        return

    with jobs._stage(job_id, "jumpsight"):
        jobs._persist(job_id)  # the stage is visible in the cloud /status too (via the shared dict)
        scan_path = live_local._live_scan_for_final(job_id)
        rep = _jb.run_streaming(str(video), _engine_event_handler(job_id), scan_path=scan_path)
    if rep is None:
        jobs.JOBS[job_id].update(
            state="error",
            error_code="ENGINE_EMPTY",
            error="the analysis engine returned no report",
            jumpsight_error="engine returned nothing",
        )
        jobs._persist(job_id)
        return

    events = _build_events(job_id, video, rep, _jb)
    if not any(e.get("state") == "done" for e in events):
        try:
            _write_unmeasured_history(job_id, video, events)
        except Exception as _he0:
            print(f"[jumpsight] empty-history write failed: {_he0}", file=sys.stderr)
    _save_pose_windows(job_id, rep)
    _write_declared_label(job_id, events)
    jobs.JOBS[job_id].update(events=events, engine="jumpsight", state="done")
    jobs.JOBS[job_id]["scan"] = {"airborne_events_found": len(events), "total_frames": None, "engine": "jumpsight"}
    jobs._persist(job_id)
    _generate_avatars(job_id, video, rep)
