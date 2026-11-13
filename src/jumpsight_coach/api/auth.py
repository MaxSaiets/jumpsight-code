"""Sign-in routes: guest sessions, transfer, Google, Apple, e-mail."""

from __future__ import annotations

import json
import os
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from jumpsight_core.paths import STATE_DIR

from .. import accounts as _acc
from .common import _acc_call

router = APIRouter()


class _TransferToken(BaseModel):
    token: str


@router.post("/claim")
def acc_claim(body: _TransferToken, request: Request, response: Response) -> dict:
    """One-time transfer of the guest profile to this device."""
    from ..sessions import allow_attempt

    if not allow_attempt("claim", request.client.host if request.client else "unknown"):
        raise HTTPException(429, "too many attempts")
    from ..sessions import consume_transfer

    uid = consume_transfer(body.token)
    if not uid:
        raise HTTPException(404, "transfer not found")
    from ..sessions import set_cookie

    set_cookie(response, request, uid, guest=True)
    return {"uid": uid}


@router.post("/auth/transfer")
def auth_transfer(request: Request) -> dict:
    from ..sessions import effective_uid, issue_transfer

    uid = effective_uid(request)
    if not uid:
        raise HTTPException(403, "session required")
    if _acc.is_registered(uid):
        raise HTTPException(403, "account requires sign-in")
    return {"token": issue_transfer(uid), "expires_in_s": 600}


def _google_client_id() -> str:
    cid = os.environ.get("JS_GOOGLE_CLIENT_ID", "").strip()
    if not cid:
        f = STATE_DIR / "google_client_id.txt"
        if f.exists():
            cid = f.read_text(encoding="utf-8").strip()
    return cid


class _Cred(BaseModel):
    credential: str


def _apple_client_id() -> str:
    cid = os.environ.get("JS_APPLE_CLIENT_ID", "").strip()
    if not cid:
        f = STATE_DIR / "apple_client_id.txt"
        if f.exists():
            cid = f.read_text(encoding="utf-8").strip()
    return cid


@router.get("/auth/config")
def auth_config() -> dict:
    return {"google_client_id": _google_client_id(), "apple_client_id": _apple_client_id()}


_APPLE_JWKS: dict = {"t": 0.0, "keys": None}


def _apple_key_for(token: str):
    import urllib.request as _ur

    import jwt as _jwt

    if not _APPLE_JWKS["keys"] or time.time() - _APPLE_JWKS["t"] > 6 * 3600:
        with _ur.urlopen("https://appleid.apple.com/auth/keys", timeout=10) as r:
            _APPLE_JWKS["keys"] = json.loads(r.read().decode("utf-8")).get("keys") or []
            _APPLE_JWKS["t"] = time.time()
    kid = _jwt.get_unverified_header(token).get("kid")
    for k in _APPLE_JWKS["keys"]:
        if k.get("kid") == kid:
            return _jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(k))
    raise KeyError("apple key not found")


class _AppleCred(BaseModel):
    id_token: str
    name: str | None = None


@router.post("/auth/apple")
def auth_apple(body: _AppleCred, request: Request, response: Response) -> dict:
    from ..sessions import allow_login, set_cookie

    if not allow_login(request):
        raise HTTPException(403, "sign-in requires HTTPS")
    cid = _apple_client_id()
    if not cid:
        raise HTTPException(503, "apple sign-in is not configured")
    try:
        import jwt as _jwt

        key = _apple_key_for(body.id_token)
        info = _jwt.decode(body.id_token, key, algorithms=["RS256"], audience=cid, issuer="https://appleid.apple.com")
    except Exception as e:
        raise HTTPException(401, f"invalid apple token: {type(e).__name__}") from None
    if not info.get("sub"):
        raise HTTPException(401, "apple token has no subject")
    # Apple gives the name only at the FIRST sign-in, so the client passes it separately
    result = _acc_call(_acc.provider_login, "apple", str(info.get("sub")), info.get("email") or "", body.name or "", "")
    set_cookie(response, request, result["uid"])
    return result


_GCERTS: dict = {"t": 0.0, "certs": None}


def _google_certs() -> dict:
    """Public Google certificates for id_token, cached for an hour."""
    import time as _tm

    if _GCERTS["certs"] is None or _tm.time() - _GCERTS["t"] > 3600:
        import requests as _rq

        r = _rq.get("https://www.googleapis.com/oauth2/v1/certs", timeout=10)
        r.raise_for_status()
        _GCERTS.update(t=_tm.time(), certs=r.json())
    return _GCERTS["certs"]


@router.post("/auth/google")
def auth_google(body: _Cred, request: Request, response: Response) -> dict:
    from ..sessions import allow_login, set_cookie

    if not allow_login(request):
        raise HTTPException(403, "sign-in requires HTTPS")
    cid = _google_client_id()
    if not cid:
        raise HTTPException(503, "google sign-in is not configured")
    try:
        # Signature, audience and expiry are checked against Google certificates cached for an hour,
        # so a sign-in does not make a network request. The issuer is checked below.
        from google.auth import jwt as _gjwt

        info = _gjwt.decode(body.credential, certs=_google_certs(), audience=cid, clock_skew_in_seconds=10)
    except Exception as e:
        raise HTTPException(401, f"invalid google token: {type(e).__name__}") from None
    if info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise HTTPException(401, "wrong issuer")
    if not info.get("sub"):
        raise HTTPException(401, "google token has no subject")
    result = _acc_call(
        _acc.google_login,
        str(info.get("sub")),
        info.get("email") or "",
        info.get("name") or "",
        info.get("picture") or "",
    )
    set_cookie(response, request, result["uid"])
    return result


@router.post("/auth/logout")
def auth_logout(request: Request, response: Response) -> dict:
    from ..sessions import set_cookie

    result = _acc.logout()
    set_cookie(response, request, result["uid"], guest=True)
    return result


@router.post("/auth/guest")
def auth_guest(request: Request, response: Response) -> dict:
    """Explicitly creates a guest session; the UID from the client is not a credential."""
    from ..sessions import effective_uid, set_cookie

    uid = effective_uid(request)
    if uid:
        return {"uid": uid, "created": False}
    # A client-supplied id with no data on the server has nothing to protect, and refusing it would
    # put a sign-in wall on the very first visit. A new guest loses nothing.
    uid = _acc.create_guest()
    set_cookie(response, request, uid, guest=True)
    return {"uid": uid, "created": True}


class _EmailCred(BaseModel):
    email: str
    password: str
    name: str | None = None


@router.post("/auth/register")
def auth_register(body: _EmailCred, request: Request, response: Response) -> dict:
    from ..sessions import allow_attempt, allow_login, set_cookie

    if not allow_login(request):
        raise HTTPException(403, "sign-in requires HTTPS")
    if not allow_attempt("register", request.client.host if request.client else "unknown"):
        raise HTTPException(429, "too many attempts")
    result = _acc_call(_acc.email_register, body.email, body.password, body.name or "")
    set_cookie(response, request, result["uid"])
    return result


@router.post("/auth/login")
def auth_login(body: _EmailCred, request: Request, response: Response) -> dict:
    from ..sessions import allow_attempt, allow_login, set_cookie

    if not allow_login(request):
        raise HTTPException(403, "sign-in requires HTTPS")
    address = (request.client.host if request.client else "unknown") + ":" + body.email.strip().lower()
    if not allow_attempt("login", address):
        raise HTTPException(429, "too many attempts")
    try:
        result = _acc.email_login(body.email, body.password)
        set_cookie(response, request, result["uid"])
        return result
    except PermissionError as e:
        raise HTTPException(401, str(e)) from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
