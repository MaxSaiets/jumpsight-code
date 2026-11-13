"""Per-request user identity for the coach stores.

The session middleware puts the user id into a contextvar; every state file
is taken from STATE_DIR/users/<uid>/. Outside HTTP (CLI, tests, tools) the
shared base path is used.
"""

from __future__ import annotations

import contextvars
import re
from pathlib import Path

_UID: contextvars.ContextVar[str | None] = contextvars.ContextVar("app_uid", default=None)
# An HTTP request without a session does not fall back to the shared paths: the shared journal of all ownerless
# tasks lives there, and every new visitor (the first page request comes before the guest session is created) would
# see someone else's 'last answer'. For such a request the state lives in its own temporary directory: reads are
# empty, and writes vanish with the request and are not mixed with anyone else's.
_ANON_DIR: contextvars.ContextVar[Path | None] = contextvars.ContextVar("anon_dir", default=None)
_OK = re.compile(r"^[A-Za-z0-9_-]{4,40}$")


def set_uid(uid: str | None):
    uid = uid if uid and _OK.match(uid) else None
    return _UID.set(uid)


def reset_uid(token) -> None:
    _UID.reset(token)


def current_uid() -> str | None:
    return _UID.get()


def run_for_user(uid: str, work):
    """Run the owner's background task and restore the context even on failure."""
    if not isinstance(uid, str) or not _OK.fullmatch(uid):
        raise ValueError("background job owner unavailable")
    token = _UID.set(uid)
    try:
        return work()
    finally:
        _UID.reset(token)


def begin_anonymous_request():
    """For an HTTP request without a session: an isolated temporary state directory."""
    import tempfile

    return _ANON_DIR.set(Path(tempfile.mkdtemp(prefix="anon_")))


def end_anonymous_request(token) -> None:
    import shutil

    d = _ANON_DIR.get()
    _ANON_DIR.reset(token)
    if d is not None:
        shutil.rmtree(d, ignore_errors=True)


def user_path(legacy: Path) -> Path:
    """State file for the current user (or the shared path without a uid).

    The shared path is used only outside HTTP (CLI, tests, tools).
    """
    uid = current_uid()
    if not uid:
        anon = _ANON_DIR.get()
        return anon / legacy.name if anon is not None else legacy
    return legacy.parent / "users" / uid / legacy.name
