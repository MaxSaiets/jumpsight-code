"""Accounts, team, comments and sharing routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from .. import accounts as _acc
from ..core import load_kb
from .common import _acc_call, _share_cookie

router = APIRouter()


class _Name(BaseModel):
    name: str | None = None
    role: str | None = None


class _Code(BaseModel):
    code: str


class _Comment(BaseModel):
    job: str
    text: str


class _Job(BaseModel):
    job: str


@router.get("/me")
def acc_me() -> dict:
    return _acc_call(_acc.me)


@router.post("/me")
def acc_update(body: _Name) -> dict:
    return _acc_call(_acc.update_me, body.name, body.role)


@router.post("/team/add")
def acc_team_add(body: _Code, request: Request) -> dict:
    from ..sessions import allow_attempt

    if not allow_attempt("team_code", request.client.host if request.client else "unknown", 30):
        raise HTTPException(429, "too many attempts")
    return _acc_call(_acc.link, body.code, True)


@router.post("/coach/join")
def acc_coach_join(body: _Code, request: Request) -> dict:
    from ..sessions import allow_attempt

    if not allow_attempt("team_code", request.client.host if request.client else "unknown", 30):
        raise HTTPException(429, "too many attempts")
    return _acc_call(_acc.link, body.code, False)


@router.post("/link/accept")
def acc_link_accept(body: _Code) -> dict:
    return _acc_call(_acc.accept_link, body.code)


@router.post("/link/reject")
def acc_link_reject(body: _Code) -> dict:
    return _acc_call(_acc.reject_link, body.code)


@router.post("/team/remove")
def acc_team_remove(body: dict) -> dict:
    return _acc_call(_acc.unlink, body.get("uid"))


@router.get("/team/pending")
def acc_team_pending() -> list[dict]:
    return _acc_call(_acc.pending_students)


@router.post("/coach/leave")
def acc_coach_leave() -> dict:
    return _acc_call(_acc.unlink, None)


@router.get("/team")
def acc_team(lang: str = "en") -> list[dict]:
    return _acc_call(_acc.team)


class _Focus(BaseModel):
    goal: str | None = None


@router.post("/team/{student_uid}/focus")
def acc_student_focus(student_uid: str, body: _Focus) -> dict:
    """The coach assigns the student a session goal (goal code from the base, empty = clear)."""

    if body.goal:
        drills, _ = load_kb()
        targets = {t for d in drills for t in (d.get("targets") or [])}
        if body.goal not in targets:
            raise HTTPException(400, "unknown goal")
    return _acc_call(_acc.set_coach_focus, student_uid, body.goal)


@router.get("/team/{student_uid}/history")
def acc_student_history(student_uid: str, lang: str = "en") -> list[dict]:
    return _acc_call(_acc.student_history, student_uid)


class _ReviewStatus(BaseModel):
    job: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    version: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewed: bool


@router.post("/team/{student_uid}/review")
def acc_student_review(student_uid: str, body: _ReviewStatus) -> dict:
    return _acc_call(_acc.set_review_status, student_uid, body.job, body.version, body.reviewed)


@router.get("/comments/{job}")
def acc_comments(job: str, request: Request) -> list[dict]:
    from ..userctx import current_uid

    owner = _acc._owner_of_job(job)
    if owner is None or not _acc.can_view_job(owner, current_uid(), job, request.cookies.get(_share_cookie())):
        raise HTTPException(404, "unknown job")
    return _acc.comments(job)


@router.post("/comment")
def acc_comment(body: _Comment) -> list[dict]:
    return _acc_call(_acc.add_comment, body.job, body.text)


@router.get("/coach_comment")
def acc_coach_comment() -> dict:
    return {"comment": _acc_call(_acc.latest_coach_comment)}


@router.post("/share")
def acc_share(body: _Job) -> dict:
    return {"token": _acc_call(_acc.share, body.job)}


@router.post("/share/revoke")
def acc_share_revoke(body: _Job) -> dict:
    return {"revoked": _acc_call(_acc.revoke_share, body.job)}


@router.get("/s/{token}")
def acc_open_share(token: str, request: Request):
    job = _acc.job_for_share(token)
    if not job:
        raise HTTPException(404, "link expired")
    response = RedirectResponse(url=f"/?job={job}", status_code=302)
    response.set_cookie(
        _share_cookie(),
        token,
        max_age=3600,
        path="/",
        secure=request.url.scheme == "https",
        httponly=True,
        samesite="lax",
    )
    return response
