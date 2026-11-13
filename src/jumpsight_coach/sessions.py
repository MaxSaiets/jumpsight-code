"""Server-side sessions of accounts. The browser token does not contain the UID."""

from __future__ import annotations

import hashlib
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager

from fastapi import Request
from fastapi.responses import Response

from jumpsight_core.paths import STATE_DIR

from .auth_store import AuthStoreUnavailable

DB = STATE_DIR / "sessions.sqlite3"
COOKIE = "js_session"
SHARE_COOKIE = "js_share"
MAX_AGE = 7 * 24 * 3600
_UID = re.compile(r"[A-Za-z0-9_-]{8,64}\Z")
_REMOTE = None


def use_remote(store) -> None:
    """Shared store; the attempt limit requires atomic_increment."""
    global _REMOTE
    _REMOTE = store


@contextmanager
def _connection():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=10)
    try:
        with con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS sessions "
                "(token_hash TEXT PRIMARY KEY, uid TEXT NOT NULL, expires REAL NOT NULL)"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS attempts "
                "(key_hash TEXT PRIMARY KEY, started REAL NOT NULL, count INTEGER NOT NULL)"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS transfers "
                "(token_hash TEXT PRIMARY KEY, uid TEXT NOT NULL, expires REAL NOT NULL)"
            )
            yield con
    finally:
        con.close()


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def create(uid: str) -> str:
    if not _UID.fullmatch(uid):
        raise ValueError("invalid user id")
    token = secrets.token_urlsafe(32)
    if _REMOTE is not None:
        _REMOTE.put("session:" + _digest(token), (uid, time.time() + MAX_AGE))
        return token
    with _connection() as con:
        con.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
        con.execute("INSERT INTO sessions VALUES (?, ?, ?)", (_digest(token), uid, time.time() + MAX_AGE))
    return token


# Every request to /coach/* would read the Modal Dict for the same session 4 times (two middlewares x before and
# after the response), about 0.4 s per request, so an in-process cache holds it for 30 s; revoke() clears it. Safe
# while the web process is a single one (max_containers=1 in modal_app.web): only it revokes sessions.
_CACHE: dict[str, tuple[str, float, float]] = {}
_CACHE_TTL_S = 30.0


def resolve(token: str | None) -> str | None:
    if not token or len(token) > 128 or not re.fullmatch(r"[A-Za-z0-9_-]+", token):
        return None
    if _REMOTE is not None:
        key = _digest(token)
        now = time.time()
        hit = _CACHE.get(key)
        if hit and now - hit[2] < _CACHE_TTL_S:
            return hit[0] if hit[1] > now else None
        row = _REMOTE.get("session:" + key)
        if row and row[1] > now:
            if len(_CACHE) > 20000:
                _CACHE.clear()
            _CACHE[key] = (row[0], row[1], now)
            return row[0]
        _CACHE.pop(key, None)
        return None
    with _connection() as con:
        row = con.execute(
            "SELECT uid FROM sessions WHERE token_hash=? AND expires>?", (_digest(token), time.time())
        ).fetchone()
    return row[0] if row else None


def revoke(token: str | None) -> None:
    if token and len(token) <= 128 and re.fullmatch(r"[A-Za-z0-9_-]+", token):
        if _REMOTE is not None:
            _CACHE.pop(_digest(token), None)
            _REMOTE.pop("session:" + _digest(token), None)
            return
        with _connection() as con:
            con.execute("DELETE FROM sessions WHERE token_hash=?", (_digest(token),))


def issue_transfer(uid: str, ttl_s: int = 600) -> str:
    """One-time secret for transferring a guest session."""
    token = secrets.token_urlsafe(32)
    row = (uid, time.time() + ttl_s)
    if _REMOTE is not None:
        _REMOTE.put("transfer:" + _digest(token), row)
        return token
    with _connection() as con:
        con.execute("DELETE FROM transfers WHERE expires < ?", (time.time(),))
        con.execute("INSERT INTO transfers VALUES (?, ?, ?)", (_digest(token), *row))
    return token


def consume_transfer(token: str | None) -> str | None:
    if not token or len(token) > 128 or not re.fullmatch(r"[A-Za-z0-9_-]+", token):
        return None
    key, now = _digest(token), time.time()
    if _REMOTE is not None:
        row = _REMOTE.pop("transfer:" + key, None)
        return row[0] if row and row[1] > now else None
    with _connection() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT uid, expires FROM transfers WHERE token_hash=?", (key,)).fetchone()
        con.execute("DELETE FROM transfers WHERE token_hash=?", (key,))
    return row[0] if row and row[1] > now else None


def allow_attempt(purpose: str, address: str, limit: int = 12, window_s: int = 600) -> bool:
    """Limit on guessing codes and passwords, shared by several web processes."""
    key = hashlib.sha256(f"{purpose}:{address}".encode()).hexdigest()
    now = time.time()
    if _REMOTE is not None:
        increment = getattr(_REMOTE, "atomic_increment", None)
        if not callable(increment):
            raise AuthStoreUnavailable("remote auth store requires atomic_increment")
        return bool(increment("attempt:" + key, now, limit, window_s))
    with _connection() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT started, count FROM attempts WHERE key_hash=?", (key,)).fetchone()
        if row and now - row[0] < window_s:
            if row[1] >= limit:
                return False
            con.execute("UPDATE attempts SET count=count+1 WHERE key_hash=?", (key,))
        else:
            con.execute("INSERT OR REPLACE INTO attempts VALUES (?, ?, 1)", (key, now))
    return True


def _local_http(request: Request) -> bool:
    return request.url.scheme == "http" and request.url.hostname in ("localhost", "127.0.0.1", "::1")


def _https(request: Request) -> bool:
    """Behind a proxy (Modal) TLS ends before the application: the scheme may be
    http, and the real one is visible only in X-Forwarded-Proto."""
    return (
        request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https"
    )


def allow_login(request: Request) -> bool:
    return _https(request) or _local_http(request)


def set_cookie(response: Response, request: Request, uid: str, *, guest: bool = False) -> None:
    old = request.cookies.get(COOKIE)
    revoke(old)
    response.set_cookie(
        COOKIE,
        create(uid),
        max_age=MAX_AGE,
        path="/",
        secure=_https(request) if guest else not _local_http(request),
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"


def clear_cookie(response: Response, request: Request) -> None:
    revoke(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/")
    response.headers["Cache-Control"] = "no-store"


def effective_uid(request: Request) -> str | None:
    """Returns only the identity from a valid server-side session."""
    return resolve(request.cookies.get(COOKIE))


def same_origin(request: Request) -> bool:
    """Protects state-changing requests carrying a cookie from requests of another origin."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return True
    origin = request.headers.get("origin")
    if origin:
        from urllib.parse import urlsplit

        given = urlsplit(origin)
        return (given.scheme, given.netloc) == (request.url.scheme, request.url.netloc)
    return request.headers.get("sec-fetch-site", "same-origin") in ("same-origin", "none")
