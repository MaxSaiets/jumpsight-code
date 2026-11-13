"""Upload, job and status API of the analyzer (`python -m jumpsight_app.web`).
Analysis runs in the `jumpsight` engine through `engine_bridge`; job state is persisted as WORK_DIR/<job>/job.json.
"""

from __future__ import annotations

from jumpsight_core.facade import install_facade

from . import dispatch, early, factory, hooks, jobs, live_local, pipeline, summary, uploads
from .factory import build_app

# Routes: /upload, /upload_start, /upload_part, /upload_finish, /status, /events (SSE),
# /summary, /media, /data, /cancel, /train_consent, /prewarm.
#
# Submodules: `hooks` (cloud hooks), `jobs` (state and persistence), `dispatch`
# (who computes), `pipeline` (the analysis job), `live_local` (in-process live
# worker), `preview` (preview runs), `early` (early numbers), `uploads`, `status`
# and `summary` (route groups), `factory` (`build_app`, middleware).
#
# Module state that the cloud entry point or tests assign (`WORK`, `JOBS`, the
# hooks, `_dispatch`, `_probe_duration`, ...) has a single owner submodule. This
# package forwards reads and writes of those names to the owner, so
# `monkeypatch.setattr(webapp, "WORK", path)` and `webapp._warm_hook = fn` change
# the one value that the code reads (see `jumpsight_core.facade`).

_OWNED_NAMES = {
    hooks: (
        "_on_persist",
        "_warm_hook",
        "_prewarm_hook",
        "_live_status",
        "_part_hook",
        "_live_end_hook",
        "_live_scan_hook",
    ),
    jobs: (
        "WORK",
        "JOBS",
        "_ANALYSIS_QUEUE",
        "_WARN_KEYS",
        "_ALLOWED_EXT",
        "_MAX_UPLOAD_MB",
        "_MAX_DURATION_S",
        "_JOB_TTL_H",
        "_last_sweep",
        "_PERSIST_LOCK",
        "_jsonable",
        "_status_projection",
        "_probe_duration",
        "_sweep_old_jobs",
        "_persist",
        "_job",
        "_stage",
        "attempt_stem",
        "_recover",
    ),
    dispatch: ("_dispatch_thread", "_dispatch", "_enqueue"),
    live_local: (
        "_LIVE_LOCAL",
        "_LIVE_ACTIVE",
        "_LIVE_SLOTS",
        "_live_local_status",
        "_live_scan_for_final",
        "_start_live_local",
    ),
    pipeline: ("_prescan_job", "_prescan_job_impl"),
    early: ("_num", "early_from_confirmed", "early_with_timing"),
    summary: ("_GCN_TO_NAME", "_NORM_DEG_S", "_event", "_rate_fields"),
    uploads: ("_DECLARABLE",),
    factory: ("_guard_jobs", "_protect_jobs"),
}
_OWNER_OF = {name: module for module, names in _OWNED_NAMES.items() for name in names}


install_facade(__name__, owned=_OWNER_OF)

__all__ = ["build_app"]
