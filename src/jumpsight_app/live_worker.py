"""Live mode worker (public edition: interface only).

While the skater records, the worker scans each uploaded part with the
engine and reports attempts a few seconds after the landing. It is built on
the private engine and is not included here; the upload side of live mode
(`upload_parts.py`, `live_queue.py`, `webapp/live_local.py`) is.
"""

from __future__ import annotations

PRIVATE_NOTE = "the live worker depends on the private analysis engine"


def run_live_loop(*args, **kwargs):
    raise RuntimeError(PRIVATE_NOTE)
