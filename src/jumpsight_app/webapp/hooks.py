"""Cloud integration hooks of the analyzer, all None locally.
The cloud entry point assigns them through the `webapp` package; readers look them up on this module at call time.
"""

from __future__ import annotations

# Readers must use `hooks._warm_hook`, never copy a name with `from .hooks import ...`,
# so that an assignment through the package reaches them.

# Status hook for fast /status: the cloud worker publishes a light projection of
# the job state into a shared dict, so /status sees changes within milliseconds
# instead of after a volume commit and re-read (2 s + 2 s).
_on_persist = None

# Warm-up on recording start: the first run during a recording paid ~40 s of
# cold start for the worker and GPU services. The cloud hook starts the CPU worker
# and the GPU service at /upload_start, while the person is still filming.
_warm_hook = None

# Warm up as soon as the person opened the app: wakes the GPU worker while the
# person picks a video (first analysis 40-75 s -> ~15-25 s).
_prewarm_hook = None

# Cloud: the state of the live worker from the shared dict (<job>:live).
_live_status = None

# Cloud: after each recording part, commit the volume so that the live worker
# (another container) sees the new bytes.
_part_hook = None

# Cloud: end of recording for the live worker (marker in the part queue).
_live_end_hook = None

# Cloud: wait for the live worker's scan for the final run (path or None).
_live_scan_hook = None
