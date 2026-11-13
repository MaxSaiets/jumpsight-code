"""Browser gates with real fixtures - one command.

The gate scripts in `tools/ui_gates/` expect injected data (`__REAL_REPORT_FIXTURES__`,
`__FIXTURES__`, `__VIDEOS__` ...). This builds those fixtures from REAL finished
analyses in `<work>/<job>/job.json`, through the real `GET /summary` and `GET /data`
routes (TestClient with a temporary owner; user profiles are not touched). No number
is invented: what the server returns is what the interface sees.

    python -m tools.run_ui_gates --work var/jobs            # all gates
    python -m tools.run_ui_gates --work var/jobs --list     # show the fixtures only
    python -m tools.run_ui_gates --work var/jobs real_report

`--work` is the jobs directory of a server that has finished analyses with their
videos (default: `jumpsight_core.paths.WORK_DIR`). A UI server must be running on
the gate port: `python tools/serve_ui.py --port 8029` (start it detached). The
browser is Chrome (`--browser=chrome` in the playwright-cli runner): the Chromium
bundled with Playwright does not play H.264 and the video checks would fail for
environment reasons. `--runner node` drives the gates through the playwright library
(`tools/ui_gates/run_gate_node.cjs`) instead of playwright-cli.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("JS_API_ONLY", "1")

from jumpsight_core import paths  # noqa: E402

WORK = paths.WORK_DIR
PORT = 8029
GATES = {
    "real_report": "tools/ui_gates/real_report_ui_smoke.js",
    "measurement_switch": "tools/ui_gates/measurement_switch_ui_smoke.js",
    "empty_result": "tools/ui_gates/empty_result_ui_smoke.js",
    "compare": "tools/ui_gates/compare_ui_smoke.js",
    "team_confidence": "tools/ui_gates/team_confidence_smoke.js",
    "coach_summary": "tools/ui_gates/coach_summary_smoke.cjs",
    "coach_mobile": "tools/ui_gates/coach_mobile_smoke.js",
    "coach_review": "tools/ui_gates/coach_review_smoke.js",
    "mobile_targets": "tools/ui_gates/check_mobile_targets.cjs",
}
_SAFE = re.compile(r"^[A-Za-z0-9_-]+$")


def _load_jobs(limit: int) -> list[tuple[str, dict]]:
    """Completed analyses from video on disk; one per video (by size)."""
    seen, out = set(), []
    for d in sorted(WORK.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        f = d / "job.json"
        if not (f.is_file() and _SAFE.match(d.name)):
            continue
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        video = Path(j.get("video") or "")
        if not video.is_absolute():
            video = ROOT / video
        # the same content under another name (input.webm / live_sim_full.webm)
        if j.get("state") != "done" or not video.is_file() or video.stat().st_size in seen:
            continue
        if not any(e.get("state") == "done" and e.get("result") for e in j.get("events") or []):
            continue
        seen.add(video.stat().st_size)
        out.append((d.name, {**j, "video": str(video)}))
        if len(out) >= limit:
            break
    return out


def build_fixtures(limit: int = 8) -> list[dict]:
    """[{original, job, fps, summary, result, video, flags}]: the first completed jump of each analysis, through the real server routes."""
    from fastapi.testclient import TestClient

    from jumpsight_app import webapp
    from jumpsight_coach import accounts, sessions

    uid = "ui_gate_fixture_owner_123"
    jobs = _load_jobs(limit)
    fixtures = []
    with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
        root = Path(folder)
        mem = {jid: {**j, "uid": uid} for jid, j in jobs}
        for obj, key, value in (
            (accounts, "STORE", root / "accounts.json"),
            (accounts, "USERS", root / "users"),
            (sessions, "DB", root / "sessions.sqlite3"),
            (webapp, "WORK", root / "jobs"),
            (webapp, "_recover", lambda: None),
            (webapp, "JOBS", mem),
        ):
            stack.enter_context(patch.object(obj, key, value))
        client = TestClient(webapp.build_app())
        try:
            client.cookies.set("js_session", sessions.create(uid))
            for jid, j in jobs:
                s = client.get(f"/summary/{jid}")
                s.raise_for_status()
                body = s.json()
                rows = [r for r in body.get("jumps") or [] if r.get("state") == "done"]
                if not rows:
                    continue
                row = rows[0]
                d = client.get(f"/data/{jid}/{row['peak_frame']}")
                d.raise_for_status()
                fixtures.append(
                    {
                        "original": jid,
                        "job": jid,
                        "fps": body.get("fps") or 30,
                        "summary": row,
                        "result": d.json(),
                        "video": j["video"].replace("\\", "/"),
                        "flags": _flags(row, d.json()),
                    }
                )
        finally:
            client.close()
    return fixtures


def _flags(row: dict, result: dict) -> dict:
    """Properties by which the gate selects the fixture (instead of hard ids)."""
    errors = result.get("errors") if isinstance(result.get("errors"), dict) else {}
    low = [e for e in errors.get("found") or [] if e.get("confidence") == "low"]
    return {
        "numeric_turns": isinstance(row.get("turns"), (int, float)),
        "name_uncertain": bool(row.get("name_uncertain")),
        "low_signal": bool(low),
        "strong_signal": any(e.get("confidence") in ("medium", "high") for e in errors.get("found") or []),
        "low_signal_keys": [e.get("code") for e in low],
    }


def _controlled_team() -> list[dict]:
    """Coach's team with controlled confidence: one pupil per level (low / medium / high / unknown). The keys are exactly those given by jumpsight_coach.accounts.team() (`last` is a subset of the journal record)."""
    import time

    out = []
    for i, tier in enumerate(("low", "medium", "high", "None")):
        conf = None if tier == "None" else tier
        out.append(
            {
                "uid": f"controlled_uid_{i}",
                "name": f"controlled_{tier}",
                "code": f"CTL{i:03d}",
                "attempts": 3,
                "new": 1,
                "review_pending": 1,
                "reviewed": 0,
                "days_since": 0,
                "attempts_7d": 3,
                "stuck": [],
                "coach_focus": None,
                "last": {
                    "job": f"controlled_job_{i}",
                    "stem": f"controlled_job_{i}_clip_att1",
                    "jump": "Lutz",
                    "count_named": "double",
                    "count_estimated": False,
                    "count_supported": True,
                    "clean": False,
                    "errors": ["step_out"],
                    "ts": time.time() - 3600,
                    "name_confidence": conf,
                    "count_confidence": conf,
                    "errors_conf": {"step_out": conf} if conf else {},
                    "air_time_s": 0.52,
                    "execution_state": "assessed",
                    "name_uncertain": False,
                    "name_display": None,
                    "name_is_family": False,
                    "rev_usable": False,
                    "revolutions": None,
                    "checks_run": 4,
                    "errors_checked_clean": ["fall", "touch_down", "hand_down", "tilted_axis"],
                },
            }
        )
    return out


def _fill(gate: str, fixtures: list[dict], tmp: Path) -> Path:
    src = (ROOT / GATES[gate]).read_text(encoding="utf-8")
    real = [{k: f[k] for k in ("original", "summary", "result", "video", "flags")} for f in fixtures]
    src = src.replace("__REAL_REPORT_FIXTURES__", json.dumps(real, ensure_ascii=False))
    src = src.replace("__APP_JS_OVERRIDE__", "null")
    if gate == "empty_result":
        a = fixtures[0]
        pair = [
            {"job": "media_a", "fps": a["fps"], "summary": a["summary"]},
            {"job": "media_b", "fps": fixtures[1]["fps"], "summary": None},
        ]
        vids = [base64.b64encode(Path(f["video"]).read_bytes()).decode() for f in fixtures[:2]]
        src = (
            src.replace("__FIXTURES__", json.dumps(pair, ensure_ascii=False))
            .replace("__VIDEOS__", json.dumps(vids))
            .replace("__ASSERT_IMPROVED__", "true")
        )
    if gate == "team_confidence":
        src = src.replace("__BACKEND_TEAM__", json.dumps(_controlled_team(), ensure_ascii=False))
    if gate == "compare":
        # the same two fixtures that the gate will choose: the first with measured take-off and landing
        timed = [
            f
            for f in fixtures
            if isinstance(f["summary"].get("t_s"), (int, float))
            and isinstance(f["summary"].get("landing_s"), (int, float))
            and f["summary"]["landing_s"] > f["summary"]["t_s"]
        ][:2]
        vids = [base64.b64encode(Path(f["video"]).read_bytes()).decode() for f in timed]
        src = src.replace("__COMPARE_VIDEOS__", json.dumps(vids))
    src = src.replace("127.0.0.1:8000", f"127.0.0.1:{PORT}")
    left = re.findall(r"__[A-Z_]+__", src)
    if left:
        raise SystemExit(f"{gate}: not substituted {sorted(set(left))}")
    out = tmp / f"{gate}.js"
    out.write_text(src, encoding="utf-8")
    return out


def _cli(*args: str) -> subprocess.CompletedProcess:
    cmd = ["npx", "--yes", "--package", "@playwright/cli", "playwright-cli", *args]
    return subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", shell=(os.name == "nt")
    )


def run_node(gate: str, script: Path) -> tuple[bool, str]:
    """The same contract through the playwright library (cloud, Linux)."""
    out = subprocess.run(
        ["node", str(ROOT / "tools" / "ui_gates" / "run_gate_node.cjs"), str(script), "--port", str(PORT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1200,
    ).stdout
    if "### Error" in out or "### Result" not in out:
        return False, out.split("### Error", 1)[-1].strip()[:3000]
    return True, out.split("### Result", 1)[1].strip()[:600]


def run(gate: str, script: Path) -> tuple[bool, str]:
    """A fresh session for each gate: the route/initScript live for the whole session."""
    session = f"uigate-{gate}"
    _cli(f"-s={session}", "close")
    _cli(f"-s={session}", "open", "--browser=chrome", f"http://127.0.0.1:{PORT}")
    try:
        out = _cli(f"-s={session}", "run-code", "--filename", str(script)).stdout
    finally:
        _cli(f"-s={session}", "close")
    if "### Error" in out:
        body = out.split("### Error", 1)[1].split("### Ran", 1)[0]
        return False, body.strip()[:3000]
    body = out.split("### Result", 1)[-1].split("### Ran", 1)[0].strip()
    return "### Result" in out, body[:600]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("gates", nargs="*", help=f"from {', '.join(GATES)}; all by default")
    ap.add_argument(
        "--work", type=Path, default=None, help="jobs directory with finished analyses (default: paths.WORK_DIR)"
    )
    ap.add_argument("--list", action="store_true", help="only show the fixtures")
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--runner", choices=("cli", "node"), default="cli")
    a = ap.parse_args()
    unknown = set(a.gates) - set(GATES)
    if unknown:
        ap.error(f"unknown gates: {sorted(unknown)}")
    global WORK
    if a.work:
        WORK = a.work
    if not WORK.is_dir():
        ap.error(f"--work directory not found: {WORK}")
    fixtures = build_fixtures(a.limit)
    for f in fixtures:
        s = f["summary"]
        print(
            f"  {f['original']:<20} {str(s.get('name_display')):<10} turns={s.get('turns')!s:<5} "
            f"conf={s.get('name_conf')} flags={f['flags']}"
        )
    if a.list:
        return 0
    if len(fixtures) < 2:
        print("Need at least 2 finished analyses with videos in the --work directory.")
        return 2
    import urllib.request

    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/healthz", timeout=5)
    except OSError:
        print(f"UI server on {PORT} does not answer: tools/serve_ui.py --port {PORT}")
        return 2
    failed = 0
    with tempfile.TemporaryDirectory() as folder:
        for gate in a.gates or list(GATES):
            ok, text = (run_node if a.runner == "node" else run)(gate, _fill(gate, fixtures, Path(folder)))
            print(f"[{'PASS' if ok else 'FAIL'}] {gate}: {text if not ok else text[:200]}")
            failed += not ok
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
