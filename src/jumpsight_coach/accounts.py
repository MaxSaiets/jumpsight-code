"""Accounts without passwords: profile code, coach ↔ students, coach comments on an analysis, and sharing links.

Why this way. Users are children, parents and coaches at a rink; e-mail/password at the test stage is a barrier that filters everyone out. So a profile is an anonymous device uid (userctx.py) plus a 6-character CODE that "carries" it: enter the code on another phone and it is the same profile. A coach adds students by their codes (or a student enters the coach's code) and sees their analyses. The coach's comment is the only "human recommendation"; it is not mixed with the algorithm's advice.

Storage is one JSON file next to the coach state, under a lock; the volume here is hundreds of records, so no database is needed.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

from jumpsight_core.paths import STATE_DIR

from .userctx import current_uid

STORE = STATE_DIR / "accounts.json"
USERS = STATE_DIR / "users"
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # without 0/O, 1/I: the code is read aloud
_EMPTY = {"codes": {}, "profiles": {}, "teams": {}, "links": {}, "comments": {}, "shares": {}}


def _lock_path():
    """Path of the accounts lock file.

    A lock on a shared volume would be committed while still held and restored after every reload, making each new guest
    wait 20 s and get a 500 "accounts storage is busy". On Modal the web container is single (max_containers=1), so the
    lock lives in the container's local directory (JS_ACCOUNTS_LOCK_DIR), not on the volume. Locally it sits next to
    STORE."""
    d = os.environ.get("JS_ACCOUNTS_LOCK_DIR", "").strip()
    return (Path(d) / (STORE.stem + ".lock")) if d else STORE.with_suffix(".lock")


class _AccountsLock:
    """Cross-process lock next to the coach state.

    `threading.Lock` protected only one Uvicorn process. On Modal several containers see the same volume, so two read-modify-write cycles could overwrite each other. Creating the lock file with O_EXCL is atomic on both Windows and Linux. The lock is reentrant within one thread, so public functions can call each other without a deadlock.
    """

    timeout_s = 20.0
    stale_s = 300.0

    def __init__(self) -> None:
        self._thread_lock = threading.RLock()
        self._local = threading.local()

    def __enter__(self):
        self._thread_lock.acquire()
        depth = getattr(self._local, "depth", 0)
        if depth:
            self._local.depth = depth + 1
            return self
        # STORE is replaced in isolated tests, so the lock path must not be fixed during module import.
        path = _lock_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            deadline = time.monotonic() + self.timeout_s
            while True:
                try:
                    fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    try:
                        os.write(fd, f"pid={os.getpid()}\nts={time.time():.6f}\n".encode())
                    finally:
                        os.close(fd)
                    self._local.depth = 1
                    self._local.path = path
                    return self
                except FileExistsError:
                    try:
                        age = time.time() - path.stat().st_mtime
                        if age > self.stale_s:
                            path.unlink(missing_ok=True)
                            continue
                    except OSError:
                        pass
                    if time.monotonic() >= deadline:
                        raise RuntimeError("accounts storage is busy") from None
                    time.sleep(0.025)
        except BaseException:
            self._thread_lock.release()
            raise

    def __exit__(self, exc_type, exc, tb) -> None:
        depth = getattr(self._local, "depth", 0) - 1
        self._local.depth = depth
        if depth == 0:
            try:
                getattr(self._local, "path", _lock_path()).unlink(missing_ok=True)
                self._local.path = None
            finally:
                self._thread_lock.release()
        else:
            self._thread_lock.release()


_LOCK = _AccountsLock()


def _load() -> dict:
    if not STORE.exists():
        return json.loads(json.dumps(_EMPTY))
    try:
        d = json.loads(STORE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # A corrupted accounts file must not be treated as empty:
        # that would let a bare UID header open a registered profile.
        raise RuntimeError("accounts storage unreadable") from exc
    for k, v in _EMPTY.items():
        d.setdefault(k, json.loads(json.dumps(v)))
    return d


def _save(d: dict) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STORE)


def _uid() -> str:
    uid = current_uid()
    if not uid:
        raise PermissionError("no session: open the app first or sign in")
    return uid


def is_registered(uid: str) -> bool:
    """An account with a confirmed sign-in method does not accept a bare UID header."""
    with _LOCK:
        p = _load()["profiles"].get(uid) or {}
    return bool(p.get("email_hash") or p.get("google_sub") or p.get("apple_sub"))


def code_is_registered(code: str) -> bool:
    with _LOCK:
        d = _load()
        p = d["profiles"].get(d["codes"].get(_norm_code(code)) or "") or {}
    return bool(p.get("email_hash") or p.get("google_sub") or p.get("apple_sub"))


def _code_of(d: dict, uid: str) -> str:
    for code, u in d["codes"].items():
        if u == uid:
            return code
    while True:
        code = "".join(secrets.choice(_ALPHABET) for _ in range(6))
        if code not in d["codes"]:
            d["codes"][code] = uid
            return code


def _norm_code(code: str) -> str:
    return "".join(ch for ch in str(code or "").upper() if ch.isalnum())


# ── profile ───────────────────────────────────────────────────────────────


def me() -> dict:
    uid = _uid()
    with _LOCK:
        d = _load()
        code = _code_of(d, uid)
        prof = d["profiles"].setdefault(uid, {"name": "", "role": "skater", "ts": time.time()})
        coach_uid = next((c for c, t in d["teams"].items() if uid in t.get("students", [])), None)
        coach = None
        if coach_uid:
            cp = d["profiles"].get(coach_uid, {})
            coach = {"name": cp.get("name") or "", "code": _code_of(d, coach_uid)}
        team = d["teams"].get(uid, {}).get("students", [])
        pending = next(
            (
                link
                for link in d.setdefault("links", {}).values()
                if link.get("student_uid") == uid
                and link.get("state") == "pending"
                and link.get("expires_at", 0) >= time.time()
            ),
            None,
        )
        pending_coach = None
        if pending:
            cp = d["profiles"].get(pending["coach_uid"], {})
            pending_coach = {"name": cp.get("name") or "", "code": _code_of(d, pending["coach_uid"])}
        _save(d)
    return {
        "uid": uid,
        "code": code,
        "name": prof.get("name") or "",
        "role": prof.get("role") or "skater",
        "coach": coach,
        "pending_coach": pending_coach,
        "students_n": len(team),
        "google": bool(prof.get("google_sub")),
        "apple": bool(prof.get("apple_sub")),
        "provider": prof.get("provider") or ("google" if prof.get("google_sub") else ""),
        "signed_in": bool(prof.get("google_sub") or prof.get("apple_sub") or prof.get("email_hash")),
        "email": prof.get("email") or "",
        "picture": prof.get("picture") or "",
    }


def _clean_name(name) -> str:
    """The name is seen by OTHER people (the coach sees the student, the student sees the coach), so angle brackets and control characters never get in here at all: protection on the server, not only escaping in every place in the interface."""
    s = "".join(
        " " if ch.isspace() else ch for ch in str(name) if ch not in "<>" and (ch.isprintable() or ch.isspace())
    )
    return " ".join(s.split())[:40]


def update_me(name: str | None = None, role: str | None = None) -> dict:
    uid = _uid()
    with _LOCK:
        d = _load()
        prof = d["profiles"].setdefault(uid, {"name": "", "role": "skater", "ts": time.time()})
        if name is not None:
            prof["name"] = _clean_name(name)
        if role in ("skater", "coach", "parent"):
            prof["role"] = role
        _save(d)
    return me()


def uid_for_code(code: str) -> str | None:
    """Sign in with a code on another device: the client takes this uid as its own."""
    with _LOCK:
        return _load()["codes"].get(_norm_code(code))


# ── team ───────────────────────────────────────────────────────────────


def link(code: str, as_coach: bool) -> dict:
    """as_coach=True: I am the coach, adding a student by their code.
    as_coach=False: I am a student, joining a coach by their code."""
    uid = _uid()
    with _LOCK:
        d = _load()
        other = d["codes"].get(_norm_code(code))
        if not other or other == uid:
            raise KeyError("code")
        coach_uid, student_uid = (uid, other) if as_coach else (other, uid)
        links = d.setdefault("links", {})
        if any(
            link.get("student_uid") == student_uid
            and link.get("coach_uid") != coach_uid
            and link.get("state") == "accepted"
            for link in links.values()
        ):
            raise PermissionError("student already has an accepted coach")
        links[f"{coach_uid}:{student_uid}"] = {
            "coach_uid": coach_uid,
            "student_uid": student_uid,
            "state": "pending",
            "created_at": time.time(),
            "expires_at": time.time() + 7 * 86400,
        }
        if as_coach:
            d["profiles"].setdefault(uid, {"name": "", "role": "coach", "ts": time.time()})["role"] = "coach"
        _save(d)
    return {"state": "pending", **me()}


def accept_link(code: str) -> dict:
    student_uid = _uid()
    with _LOCK:
        d = _load()
        coach_uid = d["codes"].get(_norm_code(code))
        link = d.setdefault("links", {}).get(f"{coach_uid}:{student_uid}") if coach_uid else None
        if not link or link.get("state") != "pending" or link.get("expires_at", 0) < time.time():
            raise KeyError("link")
        link["state"] = "accepted"
        team = d["teams"].setdefault(coach_uid, {"students": []})
        if student_uid not in team["students"]:
            team["students"].append(student_uid)
        _save(d)
    return me()


def reject_link(code: str) -> dict:
    student_uid = _uid()
    with _LOCK:
        d = _load()
        coach_uid = d["codes"].get(_norm_code(code))
        link = d.setdefault("links", {}).get(f"{coach_uid}:{student_uid}") if coach_uid else None
        if not link or link.get("state") != "pending":
            raise KeyError("link")
        link["state"] = "revoked"
        _save(d)
    return me()


def unlink(student_uid: str | None = None) -> dict:
    """The coach removes a student (uid), or the student leaves the coach (None)."""
    uid = _uid()
    with _LOCK:
        d = _load()
        if student_uid:
            t = d["teams"].get(uid, {})
            if student_uid in t.get("students", []):
                t["students"].remove(student_uid)
            link = d.setdefault("links", {}).get(f"{uid}:{student_uid}")
            if link:
                link["state"] = "revoked"
        else:
            for coach_uid, t in d["teams"].items():
                if uid in t.get("students", []):
                    t["students"].remove(uid)
                    link = d.setdefault("links", {}).get(f"{coach_uid}:{uid}")
                    if link:
                        link["state"] = "revoked"
        _save(d)
    return me()


class HistoryUnavailable(RuntimeError):
    """The journal cannot be read; we do not replace it with an empty one."""


class ReviewConflict(ValueError):
    """The mark concerns an analysis that has already changed."""


def _history_of(uid: str) -> list[dict]:
    p = USERS / uid / "history.json"
    try:
        rows = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    except (OSError, ValueError, UnicodeError):
        raise HistoryUnavailable("history temporarily unavailable") from None
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        raise HistoryUnavailable("history temporarily unavailable")
    return list(reversed(rows))


def _review_versions(rows: list[dict]) -> dict[str, str]:
    import hashlib

    grouped: dict[str, list] = {}
    for row in rows:
        if row.get("job"):
            grouped.setdefault(row["job"], []).append(row)
    return {
        job: hashlib.sha256(json.dumps(group, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        for job, group in grouped.items()
    }


def _reviewed(record: dict, version: str) -> bool:
    return record.get("version") == version and record.get("status") == "reviewed"


def team() -> list[dict]:
    """The coach's students with the latest analysis of each one and a "new" marker."""
    uid = _uid()
    with _LOCK:
        d = _load()
        students = list(d["teams"].get(uid, {}).get("students", []))
        reviews = d["teams"].get(uid, {}).get("reviews", {})
        profiles = d["profiles"]
        codes = {u: c for c, u in d["codes"].items()}
    out = []
    from .core import CODE_ALIASES

    for s in students:
        hist = _history_of(s)
        last = next((r for r in hist if r.get("job")), None)
        versions = _review_versions(hist)
        records = reviews.get(s, {})
        pending = {job for job, version in versions.items() if not _reviewed(records.get(job, {}), version)}
        # Attempts on the card = measured records: an unmeasured fragment must not count as a new attempt.
        new_n = sum(1 for r in hist if r.get("job") in pending and r.get("outcome") != "not_measured")
        # The coach needs signals, not just the "last analysis":
        # how many days of silence, which error persists (≥3 of the last 4
        # analyses, for base purposes), and what is assigned. All from the journal, nothing
        # is invented.
        measured = [r for r in hist if r.get("outcome") != "not_measured"][:4]
        cnt: dict[str, int] = {}
        for r in measured:
            for g in {CODE_ALIASES.get(e, e) for e in (r.get("errors") or [])}:
                cnt[g] = cnt.get(g, 0) + 1
        stuck = sorted([g for g, k in cnt.items() if len(measured) >= 3 and k >= 3])
        last_ts = float((last or {}).get("ts") or 0)
        days = int((time.time() - last_ts) // 86400) if last_ts else None
        week = sum(1 for r in hist if float(r.get("ts") or 0) > time.time() - 7 * 86400)
        out.append(
            {
                "uid": s,
                "name": profiles.get(s, {}).get("name") or "",
                "code": codes.get(s, ""),
                "attempts": sum(1 for r in hist if r.get("outcome") != "not_measured"),
                "new": new_n,
                "review_pending": len(pending),
                "reviewed": len(versions) - len(pending),
                "days_since": days,
                "attempts_7d": week,
                "stuck": stuck,
                "coach_focus": coach_focus_of(s),
                "last": (
                    {
                        k: last.get(k)
                        for k in (
                            "job",
                            "stem",
                            "jump",
                            "count_named",
                            "count_estimated",
                            "count_supported",
                            "clean",
                            "errors",
                            "ts",
                            "name_confidence",
                            "count_confidence",
                            "errors_conf",
                            "air_time_s",
                            "execution_state",
                            "name_uncertain",
                            "name_display",
                            "name_is_family",
                            "rev_usable",
                            # Without them, a student's row could not honestly say
                            # "no errors found" (how many signs were checked)
                            "checks_run",
                            "errors_checked_clean",
                            "revolutions",
                        )
                    }
                    if last
                    else None
                ),
            }
        )
    out.sort(key=lambda r: -(float((r["last"] or {}).get("ts") or 0)))
    return out


def pending_students() -> list[dict]:
    """Coach requests without access to the student's data before the student's accept."""
    uid = _uid()
    with _LOCK:
        d = _load()
        now = time.time()
        rows = [
            link
            for link in d.setdefault("links", {}).values()
            if link.get("coach_uid") == uid and link.get("state") == "pending" and link.get("expires_at", 0) >= now
        ]
        profiles, codes = d["profiles"], {u: c for c, u in d["codes"].items()}
    return [
        {
            "uid": r["student_uid"],
            "name": profiles.get(r["student_uid"], {}).get("name") or "",
            "code": codes.get(r["student_uid"], ""),
            "expires_at": r["expires_at"],
        }
        for r in rows
    ]


def coach_focus_of(student_uid: str) -> dict | None:
    p = USERS / student_uid / "coach_focus.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except Exception:  # noqa: BLE001
        d = None
    return d if isinstance(d, dict) and d.get("goal") else None


def set_coach_focus(student_uid: str, goal: str | None) -> dict:
    """The coach assigns the session goal to the student (goal = the knowledge base goal code, or empty = clear). The student's session takes it ahead of the automatic 14-day focus."""
    uid = _uid()
    with _LOCK:
        d = _load()
        if student_uid not in d["teams"].get(uid, {}).get("students", []):
            raise PermissionError("not my student")
        name = d["profiles"].get(uid, {}).get("name") or ""
        # The permission and the write must be one critical section: otherwise a parallel
        # unlink could remove the student between the check and the goal write.
        p = USERS / student_uid / "coach_focus.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        goal = re.sub(r"[^a-z_]", "", str(goal or "").lower())[:40]
        if not goal:
            p.unlink(missing_ok=True)
            return {"ok": True, "goal": None}
        rec = {"goal": goal, "ts": time.time(), "coach_uid": uid, "coach_name": name}
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)
        return {"ok": True, **rec}


def student_history(student_uid: str, limit: int = 30) -> list[dict]:
    uid = _uid()
    with _LOCK:
        d = _load()
        if student_uid not in d["teams"].get(uid, {}).get("students", []):
            raise PermissionError("not my student")
        rows = _history_of(student_uid)
        versions = _review_versions(rows)
        records = d["teams"][uid].get("reviews", {}).get(student_uid, {})
    return [
        {
            **r,
            "review_version": versions.get(r.get("job")),
            "review_status": "reviewed"
            if _reviewed(records.get(r.get("job"), {}), versions.get(r.get("job")))
            else "pending",
        }
        for r in rows[:limit]
    ]


def set_review_status(student_uid: str, job: str, version: str, reviewed: bool) -> dict:
    """An explicit coach action; permission, version and write under one lock."""
    uid = _uid()
    with _LOCK:
        d = _load()
        if student_uid not in d["teams"].get(uid, {}).get("students", []):
            raise PermissionError("not my student")
        rows = _history_of(student_uid)
        versions = _review_versions(rows)
        if job not in versions:
            raise KeyError(job)
        if versions[job] != version:
            raise ReviewConflict("analysis changed; reload history")
        records = d["teams"][uid].setdefault("reviews", {}).setdefault(student_uid, {})
        status = "reviewed" if reviewed else "pending"
        previous = records.get(job, {})

        def response(record):
            pending = {j for j, v in versions.items() if not _reviewed(records.get(j, {}), v)}
            return {
                "ok": True,
                **record,
                "review_pending": len(pending),
                "new": sum(1 for row in rows if row.get("job") in pending and row.get("outcome") != "not_measured"),
            }

        if previous.get("version") == version and previous.get("status") == status:
            return response(previous)
        record = {"version": version, "status": status, "updated_at": time.time()}
        records[job] = record
        _save(d)
        return response(record)


# ── coach comments ─────────────────────────────────────────────────────


def _owner_of_job(job: str) -> str | None:
    """Whose analysis this is: we look up the job in the histories of all users."""
    from .integration import HOST

    current = HOST.find_job(job)
    if current and current.get("uid"):
        return current["uid"]
    if not USERS.exists():
        return None
    for p in USERS.glob("*/history.json"):
        try:
            if any(r.get("job") == job for r in json.loads(p.read_text(encoding="utf-8"))):
                return p.parent.name
        except Exception:  # noqa: BLE001
            continue
    return None


def add_comment(job: str, text: str) -> list[dict]:
    uid = _uid()
    text = str(text or "").strip()[:500]
    if not text:
        raise ValueError("empty")
    with _LOCK:
        d = _load()
        owner = _owner_of_job(job)
        my_students = d["teams"].get(uid, {}).get("students", [])
        if owner is None or (owner != uid and owner not in my_students):
            raise PermissionError("not my student")
        name = d["profiles"].get(uid, {}).get("name") or ""
        d["comments"].setdefault(job, []).append(
            {
                "from": uid,
                "name": name,
                "role": d["profiles"].get(uid, {}).get("role") or "skater",
                "text": text,
                "ts": time.time(),
            }
        )
        _save(d)
    return comments(job)


def comments(job: str) -> list[dict]:
    with _LOCK:
        d = _load()
        rows = list(d["comments"].get(job, []))
        me_uid = current_uid()
    return [
        {
            "name": r.get("name") or "",
            "role": r.get("role"),
            "text": r["text"],
            "ts": r["ts"],
            "mine": r.get("from") == me_uid,
        }
        for r in rows
    ]


def latest_coach_comment() -> dict | None:
    """The coach's latest comment on any of my analyses, for "Training"."""
    uid = _uid()
    jobs = {r.get("job") for r in _history_of(uid) if r.get("job")}
    with _LOCK:
        d = _load()
        best = None
        for job, rows in d["comments"].items():
            if job not in jobs:
                continue
            for r in rows:
                if r.get("role") == "coach" and (best is None or r["ts"] > best["ts"]):
                    best = {**r, "job": job}
    if not best:
        return None
    return {"job": best["job"], "name": best.get("name") or "", "text": best["text"], "ts": best["ts"]}


# ── sharing ─────────────────────────────────────────────────────────────


def share(job: str) -> str:
    uid = _uid()
    owner = _owner_of_job(job)
    if owner is None or not can_view_job(owner, uid, job):
        raise PermissionError("not your analysis")
    with _LOCK:
        d = _load()
        for tok, rec in d["shares"].items():
            if (
                isinstance(rec, dict)
                and rec.get("job") == job
                and not rec.get("revoked_at")
                and rec.get("expires_at", 0) > time.time()
            ):
                return tok
        tok = secrets.token_urlsafe(9)
        d["shares"][tok] = {
            "job": job,
            "scope": "read",
            "created_at": time.time(),
            "expires_at": time.time() + 24 * 3600,
            "revoked_at": None,
        }
        _save(d)
    return tok


def job_for_share(token: str) -> str | None:
    with _LOCK:
        rec = _load()["shares"].get(token)
        if (
            not isinstance(rec, dict)
            or rec.get("scope") != "read"
            or rec.get("revoked_at")
            or rec.get("expires_at", 0) <= time.time()
        ):
            return None
        return rec.get("job")


def revoke_share(job: str) -> bool:
    uid = _uid()
    owner = _owner_of_job(job)
    if owner is None or not can_view_job(owner, uid, job):
        raise PermissionError("not your analysis")
    with _LOCK:
        d = _load()
        changed = False
        for rec in d["shares"].values():
            if isinstance(rec, dict) and rec.get("job") == job and not rec.get("revoked_at"):
                rec["revoked_at"] = time.time()
                changed = True
        _save(d)
    return changed


def can_view_job(owner: str | None, viewer: str | None, job: str, share_token: str | None = None) -> bool:
    if not owner:
        return False  # without a provable owner, the result is not public
    if viewer == owner:
        return True
    with _LOCK:
        d = _load()
        if viewer and owner in d["teams"].get(viewer, {}).get("students", []):
            return True
        return bool(share_token and job_for_share(share_token) == job)


def coach_of_stem_owner(stem: str, viewer: str | None) -> str | None:
    """The student's uid, if the stem belongs to EXACTLY one person and the viewer is that person's coach.

    The coach's mark on a student's analysis is an expert mark (the coach knows which element the student performed). An ambiguous stem is not a coach mark."""
    if not viewer or not USERS.exists():
        return None
    owners = set()
    for path in USERS.glob("*/history.json"):
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if any(r.get("stem") == stem for r in rows):
            owners.add(path.parent.name)
    if len(owners) != 1:
        return None
    owner = next(iter(owners))
    if owner == viewer:
        return None
    with _LOCK:
        d = _load()
        ok = owner in d["teams"].get(viewer, {}).get("students", [])
    return owner if ok else None


def can_view_stem(stem: str, viewer: str | None, share_token: str | None = None) -> bool:
    """Find the owner of a derived file by the journal, not by the file name."""
    if not USERS.exists():
        return False
    owners: dict[str, str] = {}
    for path in USERS.glob("*/history.json"):
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for row in rows:
            if row.get("stem") == stem:
                owners.setdefault(path.parent.name, row.get("job") or "")
    # Stems that predate unique naming (src/webapp.attempt_stem) are ambiguous: an identical file name for different
    # people gave one stem, and the derived file out/<stem>_result.json belonged to whoever wrote last. An ambiguous
    # stem is closed to everyone: the numbers stay in each person's journal, but another person's video or 3D
    # cannot be shown.
    if len(owners) != 1:
        return False
    ((owner, job),) = owners.items()
    return can_view_job(owner, viewer, job, share_token)


# ── Google ────────────────────────────────────────────────────────────────


def google_login(sub: str, email: str, name: str, picture: str) -> dict:
    return provider_login("google", sub, email, name, picture)


def provider_login(provider: str, sub: str, email: str, name: str, picture: str) -> dict:
    """Verified provider account (google | apple) -> uid. If this account is already linked to another profile (another phone), we return THAT uid and the client switches to it; otherwise we link it to the current profile."""
    uid = current_uid() or _new_guest_uid()
    key = f"{provider}_sub"
    with _LOCK:
        d = _load()
        owner = next((u for u, p in d["profiles"].items() if p.get(key) == sub), None)
        target = owner or uid
        prof = d["profiles"].setdefault(target, {"name": "", "role": "skater", "ts": time.time()})
        prof[key] = sub
        prof["provider"] = provider
        prof["email"] = email or prof.get("email") or ""
        prof["picture"] = picture or prof.get("picture") or ""
        if not prof.get("name") and name:
            prof["name"] = _clean_name(name)
        _code_of(d, target)
        _save(d)
    return {"uid": target, "switched": target != uid}


# ── EMAIL + PASSWORD ──────────────────────────────────────────────────────
# Google sign-in from a phone on the home network does not work at all (origin_mismatch on a private IP), so e-mail
# sign-in exists too. The password is hashed with stdlib scrypt (n=2**14, r=8, p=1), with no new dependencies.


def _norm_email(email: str) -> str:
    e = str(email or "").strip().lower()
    if "@" not in e or "." not in e.split("@")[-1] or len(e) > 120:
        raise ValueError("bad email")
    return e


def _hash_pw(password: str, salt: bytes) -> str:
    import hashlib

    if len(password) < 8:
        raise ValueError("password too short (min 8)")
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1).hex()


def email_register(email: str, password: str, name: str = "") -> dict:
    """New account on the CURRENT uid (the guest profile becomes the account, so the journal and sessions are not lost). An occupied email raises a KeyError-like ValueError whose text the UI shows as is."""
    import os

    uid = _uid()
    e = _norm_email(email)
    salt = os.urandom(16)
    h = _hash_pw(password, salt)
    with _LOCK:
        d = _load()
        if any(p.get("email_norm") == e for p in d["profiles"].values()):
            raise ValueError("email already registered")
        if any(d["profiles"].get(uid, {}).get(k) for k in ("email_hash", "google_sub", "apple_sub")):
            raise ValueError("account already registered")
        prof = d["profiles"].setdefault(uid, {"name": "", "role": "skater", "ts": time.time()})
        prof.update(email_norm=e, email=e, email_salt=salt.hex(), email_hash=h, provider="email")
        if name and not prof.get("name"):
            prof["name"] = _clean_name(name)
        _code_of(d, uid)
        _save(d)
    return {"uid": uid, "switched": False}


def email_login(email: str, password: str) -> dict:
    """Sign-in -> owner's uid. Wrong pair -> PermissionError (401 in the API). Brute force is slowed by scrypt itself (~0.1 s per attempt)."""
    e = _norm_email(email)
    with _LOCK:
        d = _load()
        owner, prof = next(((u, p) for u, p in d["profiles"].items() if p.get("email_norm") == e), (None, None))
    if not owner or not prof.get("email_salt"):
        raise PermissionError("wrong email or password")
    h = _hash_pw(password, bytes.fromhex(prof["email_salt"]))
    import hmac

    if not hmac.compare_digest(h, prof.get("email_hash") or ""):
        raise PermissionError("wrong email or password")
    return {"uid": owner, "switched": owner != current_uid()}


def logout() -> dict:
    """Sign-out = a NEW guest uid for this device. The account link stays intact."""
    return {"uid": _new_guest_uid(), "switched": True}


def create_guest() -> str:
    """Creates a new guest profile only on an explicit request from the server."""
    uid = _new_guest_uid()
    with _LOCK:
        d = _load()
        d["profiles"][uid] = {"name": "", "role": "skater", "ts": time.time()}
        _code_of(d, uid)
        _save(d)
    return uid


def _new_guest_uid() -> str:
    import secrets

    return secrets.token_hex(10)


def google_logout() -> dict:
    return logout()
    return me()
