"""Self-rating of a drill opens its continuation, not unrelated skills."""

import json

import pytest


@pytest.fixture
def scoped_plan(monkeypatch, tmp_path):
    from jumpsight_coach import fitness, goal, session, skills
    from jumpsight_coach.core import load_kb

    monkeypatch.setattr(session, "LOG", tmp_path / "log.json")
    monkeypatch.setattr(fitness, "PROFILE", tmp_path / "fitness.json")
    monkeypatch.setattr(goal, "STORE", tmp_path / "goal.json")
    monkeypatch.setattr(skills, "profile", lambda *a, **k: {"level": 1})
    monkeypatch.setattr(skills, "load", lambda: {"survey": {"balance": 2, "coach": 2}})
    monkeypatch.setattr(skills, "persistent_gaps", list)
    template = next(d for d in load_kb()[0] if d["id"] == "hv_back_hops_landing")
    drills = [
        {**template, "id": "base", "level": 2, "progression_id": "next"},
        {**template, "id": "next", "level": 3, "progression_id": ""},
        {**template, "id": "unrelated", "level": 3, "progression_id": ""},
        {**template, "id": "easy", "level": 1, "progression_id": ""},
    ]
    monkeypatch.setattr(session, "load_kb", lambda: (drills, {}))
    monkeypatch.setattr(session, "_last_used", lambda: {"easy": 100})
    monkeypatch.setattr(
        session,
        "pick_drills",
        lambda goals, kb, **kw: [d for d in kb if kw.get("level_min", 1) <= d["level"] <= kw.get("level_max", 99)],
    )

    def make(*, quality="ok", feel="fresh", want="", effort=None):
        rows = [
            {"session_id": str(i), "blocks": [{"drill_id": "base", "outcome": quality}], "effort": effort}
            for i in range(3)
        ]
        session.LOG.write_text(json.dumps(rows), encoding="utf-8")
        return session.build_for_goal("landing_stability", feel=feel, want=want)

    return make


def drill_ids(plan):
    return {b["drill_id"] for b in plan["blocks"] if b.get("drill_id")}


def test_success_opens_linked_step_without_opening_unrelated_skill(scoped_plan):
    ids = drill_ids(scoped_plan())
    assert "next" in ids
    assert "unrelated" not in ids


@pytest.mark.parametrize("quality", ["partial", "fail", "done"])
def test_no_success_evidence_keeps_both_harder_steps_closed(scoped_plan, quality):
    assert not ({"next", "unrelated"} & drill_ids(scoped_plan(quality=quality)))


@pytest.mark.parametrize(
    "feel,want,effort",
    [
        ("sore", "hard", None),
        ("fresh", "easy", None),
        ("tired", "hard", None),
        ("fresh", "hard", "much"),
    ],
)
def test_daily_limits_still_close_linked_harder_step(scoped_plan, feel, want, effort):
    assert "next" not in drill_ids(scoped_plan(feel=feel, want=want, effort=effort))


def test_explicit_hard_day_retains_existing_general_challenge(scoped_plan):
    assert "unrelated" in drill_ids(scoped_plan(want="hard"))


def test_progression_reason_identifies_self_report(scoped_plan):
    notes = " ".join(scoped_plan()["personalisation"])
    assert "self-reported" in notes
