"""English only: the server does not show Cyrillic to the person.

The interface is English only: the coach cabinet, the chat sources and the analysis-failure messages must not be sent in another language.
"""

import json
import re

import pytest

from jumpsight_core import paths  # noqa: E402
from jumpsight_core.paths import REPO_ROOT  # noqa: E402

CYR = re.compile("[\u0400-\u04ff]")


@pytest.fixture
def coach_with_student(monkeypatch, tmp_path):
    from jumpsight_coach import accounts, sessions

    monkeypatch.setattr(sessions, "DB", tmp_path / "sessions.sqlite3")
    monkeypatch.setattr(accounts, "STORE", tmp_path / "accounts.json")
    monkeypatch.setattr(accounts, "USERS", tmp_path / "users")
    monkeypatch.setattr(accounts, "_uid", lambda: "coach_en_123")
    accounts._save(
        {"teams": {"coach_en_123": {"students": ["student_en_123"], "seen": {}}}, "profiles": {}, "codes": {}}
    )
    path = accounts.USERS / "student_en_123" / "history.json"
    path.parent.mkdir(parents=True)
    # log file: from old to new; the server returns newer ones first
    path.write_text(
        json.dumps(
            [
                {
                    "job": "job_en_2",
                    "ts": 900,
                    "jump": None,
                    "outcome": "not_measured",
                    "reason": "no_jump_found",
                    "reason_detail": "no jump was found",
                },
                {"job": "job_en_1", "ts": 1000, "jump": "Lutz", "count_named": "double", "errors": []},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return accounts


def test_student_history_and_team_are_english_by_default(coach_with_student):
    from jumpsight_coach import api

    rows = api.acc_student_history("student_en_123")
    assert rows[0]["count_named"] == "double"
    assert rows[1]["reason_detail"] == "no jump was found"
    team = api.acc_team()
    assert team[0]["last"]["count_named"] == "double"
    assert not CYR.search(json.dumps(rows, ensure_ascii=False))


def test_progress_goals_default_is_english():
    import inspect

    from jumpsight_coach import api

    assert inspect.signature(api.get_progress_goals).parameters["lang"].default == "en"


def test_server_failure_messages_are_english():
    """Texts that the client shows as the cause of a failure are in English."""
    package = REPO_ROOT / "src" / "jumpsight_app" / "webapp"
    webapp = "\n".join(p.read_text(encoding="utf-8") for p in sorted(package.glob("*.py")))
    for m in re.finditer(r'(?:error|live_warning)"?\s*[:=]\s*"([^"]+)"', webapp):
        assert not CYR.search(m.group(1)), m.group(1)
    queue = (REPO_ROOT / "src" / "jumpsight_core" / "job_queue.py").read_text(encoding="utf-8")
    raised = re.findall(r'QueueFull\("([^"]+)"\)', queue)
    assert raised and not any(CYR.search(x) for x in raised)


def test_index_html_has_no_cyrillic_outside_comments_and_scripts():
    html = (paths.WEB_DIR / "index.html").read_text(encoding="utf-8")
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    html = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", html, flags=re.S)
    left = [ln.strip()[:80] for ln in html.splitlines() if CYR.search(ln)]
    assert not left, left
