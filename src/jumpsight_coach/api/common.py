"""Helpers shared by the route modules: share cookie, stem validation, error mapping."""

from __future__ import annotations

import re

from fastapi import HTTPException, Request

from .. import accounts as _acc


def _share_cookie() -> str:
    from ..sessions import SHARE_COOKIE

    return SHARE_COOKIE


def _require_stem_access(stem: str, request: Request) -> None:
    from .. import accounts
    from ..userctx import current_uid

    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,180}", stem):
        raise HTTPException(404, "analysis not found")
    if not accounts.can_view_stem(stem, current_uid(), request.cookies.get(_share_cookie())):
        raise HTTPException(404, "analysis not found")


def _valid_stem(stem: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_.-]{1,180}", stem))


def _acc_call(fn, *args):
    try:
        return fn(*args)
    except PermissionError as e:
        raise HTTPException(403, str(e)) from None
    except KeyError:
        raise HTTPException(404, "code not found") from None
    except _acc.ReviewConflict as e:
        raise HTTPException(409, str(e)) from None
    except _acc.HistoryUnavailable:
        raise HTTPException(503, "history temporarily unavailable") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
