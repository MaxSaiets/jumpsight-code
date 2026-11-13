"""The contract of ending a session: a repeat request and the quality of performance."""

from __future__ import annotations

import json

import pytest


def test_completion_is_idempotent_and_keeps_explicit_effort(monkeypatch, tmp_path):
    from jumpsight_coach import session

    monkeypatch.setattr(session, "LOG", tmp_path / "session_log.json")
    first = session.complete(
        ["hv_consec_half_rotations"],
        "balance",
        outcomes={"hv_consec_half_rotations": "partial"},
        effort="much",
        session_id="demo-session-1",
    )
    second = session.complete(
        ["hv_consec_half_rotations"],
        "balance",
        outcomes={"hv_consec_half_rotations": "partial"},
        effort="much",
        session_id="demo-session-1",
    )
    rows = json.loads(session.LOG.read_text(encoding="utf-8"))
    assert first["sessions"] == second["sessions"] == len(rows) == 1
    assert rows[0]["effort"] == "much"
    assert rows[0]["blocks"] == [{"drill_id": "hv_consec_half_rotations", "outcome": "partial"}]


def test_completion_rejects_unknown_outcomes(monkeypatch, tmp_path):
    from jumpsight_coach import session

    monkeypatch.setattr(session, "LOG", tmp_path / "session_log.json")
    with pytest.raises(ValueError, match="invalid drill outcome"):
        session.complete(["drill_a"], "balance", outcomes={"drill_a": "perfect"})
    assert not session.LOG.exists()


def test_goal_session_forwards_readiness(monkeypatch):
    from jumpsight_coach import session

    captured = {}

    def fake_build(profile, lang="en", feel="", want=""):
        captured.update(lang=lang, feel=feel, want=want, goals=profile.goals())
        return {"personalisation": []}

    monkeypatch.setattr(session, "build", fake_build)
    session.build_for_goal("balance", "en", feel="tired", want="easy")
    assert captured == {"lang": "en", "feel": "tired", "want": "easy", "goals": ["balance"]}


def test_completion_without_quality_does_not_unlock_harder_drills(monkeypatch, tmp_path):
    from jumpsight_coach import fitness, goal, session, skills

    monkeypatch.setattr(session, "LOG", tmp_path / "session_log.json")
    monkeypatch.setattr(skills, "PROFILE", tmp_path / "skills.json")
    monkeypatch.setattr(fitness, "PROFILE", tmp_path / "fitness.json")
    monkeypatch.setattr(goal, "STORE", tmp_path / "goal.json")
    monkeypatch.setattr(skills, "persistent_gaps", list)
    drill_id = "hv_consec_half_rotations"
    for index in range(3):
        session.complete([drill_id], "basics_rotation", session_id=f"unrated-{index}")
    unrated = session.build_for_goal("basics_rotation")
    assert not any("self-reported" in note for note in unrated["personalisation"])

    session.LOG.write_text("[]", encoding="utf-8")
    for index in range(3):
        session.complete([drill_id], "basics_rotation", outcomes={drill_id: "ok"}, session_id=f"clean-{index}")
    clean = session.build_for_goal("basics_rotation")
    # The successor of this drill is at level 2. The series confirms exactly it,
    # but does not open unrelated drills of level 3.
    assert session._outcome_streaks(session._log())[0][drill_id] == 3
    from jumpsight_coach.core import load_kb

    levels = {d["id"]: d.get("level", 1) for d in load_kb()[0]}
    assert all(levels[b["drill_id"]] <= 2 for b in clean["blocks"] if b.get("drill_id"))


def test_two_difficult_sessions_adjust_the_next_goal_plan(monkeypatch, tmp_path):
    from jumpsight_coach import fitness, goal, session, skills

    monkeypatch.setattr(session, "LOG", tmp_path / "session_log.json")
    monkeypatch.setattr(skills, "PROFILE", tmp_path / "skills.json")
    monkeypatch.setattr(fitness, "PROFILE", tmp_path / "fitness.json")
    monkeypatch.setattr(goal, "STORE", tmp_path / "goal.json")
    monkeypatch.setattr(skills, "persistent_gaps", list)
    session.complete([], "basics_rotation", effort="much", session_id="hard-1")
    session.complete([], "basics_rotation", effort="much", session_id="hard-2")
    plan = session.build_for_goal("basics_rotation")
    assert any("too hard" in note for note in plan["personalisation"])


def test_duplicate_drills_count_once_per_session(monkeypatch, tmp_path):
    from jumpsight_coach import session

    monkeypatch.setattr(session, "LOG", tmp_path / "log.json")
    did = "hv_consec_half_rotations"
    session.complete([did, did, did], "basics_rotation", outcomes={did: "ok"}, session_id="one")
    assert session._log()[0]["blocks"] == [{"drill_id": did, "outcome": "ok"}]


def test_unknown_drill_is_rejected_without_saving(monkeypatch, tmp_path):
    from jumpsight_coach import session

    monkeypatch.setattr(session, "LOG", tmp_path / "log.json")
    with pytest.raises(ValueError, match="unknown drill"):
        session.complete(["unknown_drill"], "basics_rotation")
    assert not session.LOG.exists()


def test_conflicting_session_retry_is_rejected(monkeypatch, tmp_path):
    from jumpsight_coach import session

    monkeypatch.setattr(session, "LOG", tmp_path / "log.json")
    did = "hv_consec_half_rotations"
    session.complete([did], "basics_rotation", outcomes={did: "partial"}, session_id="one")
    with pytest.raises(ValueError, match="session id conflict"):
        session.complete([did], "basics_rotation", outcomes={did: "ok"}, session_id="one")
    assert session._log()[0]["blocks"][0]["outcome"] == "partial"


def test_legacy_duplicate_blocks_do_not_unlock_mastery(monkeypatch, tmp_path):
    from jumpsight_coach import fitness, goal, session, skills

    monkeypatch.setattr(session, "LOG", tmp_path / "log.json")
    monkeypatch.setattr(skills, "PROFILE", tmp_path / "skills.json")
    monkeypatch.setattr(fitness, "PROFILE", tmp_path / "fitness.json")
    monkeypatch.setattr(goal, "STORE", tmp_path / "goal.json")
    monkeypatch.setattr(skills, "persistent_gaps", list)
    did = "hv_consec_half_rotations"
    session.LOG.write_text(json.dumps([{"blocks": [{"drill_id": did, "outcome": "ok"}] * 3}]), encoding="utf-8")
    plan = session.build_for_goal("basics_rotation")
    assert not any("self-reported" in note for note in plan["personalisation"])


@pytest.mark.parametrize(
    "feel,want,forbidden", [("sore", "hard", False), ("fresh", "easy", False), ("fresh", "hard", True)]
)
def test_mastery_does_not_override_easy_day(monkeypatch, tmp_path, feel, want, forbidden):
    from jumpsight_coach import fitness, goal, session, skills
    from jumpsight_coach.core import load_kb

    monkeypatch.setattr(session, "LOG", tmp_path / "log.json")
    monkeypatch.setattr(fitness, "PROFILE", tmp_path / "fitness.json")
    monkeypatch.setattr(goal, "STORE", tmp_path / "goal.json")
    monkeypatch.setattr(skills, "profile", lambda *a, **k: {"level": 1})
    monkeypatch.setattr(skills, "load", lambda: {"survey": {"balance": 2, "coach": 2}})
    monkeypatch.setattr(skills, "persistent_gaps", list)
    did = "hv_back_hops_landing"
    by_id = {d["id"]: d for d in load_kb()[0]}
    base = {**by_id[did], "progression_id": "hv_double_two_foot"}
    harder = by_id["hv_double_two_foot"]
    if forbidden:
        harder = {**harder, "level": 1, "kind": "do_not_recommend"}
    monkeypatch.setattr(session, "load_kb", lambda: ([base, harder], {}))
    for index in range(3):
        session.complete([did], "landing_stability", outcomes={did: "ok"}, session_id=f"clean-{index}")
    plan = session.build_for_goal("landing_stability", feel=feel, want=want)
    levels = {d["id"]: d.get("level", 1) for d in load_kb()[0]}
    assert all(levels[b["drill_id"]] <= 1 for b in plan["blocks"] if b.get("drill_id")), plan["blocks"]
