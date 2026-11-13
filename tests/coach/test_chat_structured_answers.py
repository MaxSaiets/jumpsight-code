"""Deterministic answers of the chat to typical questions (chat bench).

'My knee hurts' must not get a jump drill, 'my level' must not get a bibliography excerpt, and ISU marks, warm-up and frequency questions need answers. Here these questions reach their own branches.
"""

import re
from pathlib import Path

import pytest

from jumpsight_coach import knowledge as k


@pytest.mark.parametrize("q", ["My knee hurts after landing, what should I do?", "I think I injured my ankle"])
def test_pain_goes_to_safety_not_to_a_drill(q):
    r = k._safety_lookup(q)
    assert r and r["structured"] == "safety"
    assert "Drill" not in r["answer"]


def test_safety_comes_before_landing_advice_in_the_chain():
    src = Path(k.answer.__file__).read_text(encoding="utf-8")
    assert src.index("_safety_lookup, _isu_marks_lookup, _personal_lookup") < src.index("isu = _isu_lookup(")


@pytest.mark.parametrize("q", ["What does 'q' mean on a score sheet?", "Why did my jump get downgraded?"])
def test_isu_marks(q):
    r = k._isu_marks_lookup(q)
    assert r and "<<" in r["answer"] and "q —" in r["answer"]


def test_not_every_question_is_a_mark_question():
    assert k._isu_marks_lookup("Why do I keep under-rotating my jumps?") is None


@pytest.mark.parametrize(
    "q,expect",
    [
        ("What warm-up should I do before jumping?", "warm-up"),
        ("Is it safe to practice jumps off-ice every day?", "48-72"),
    ],
)
def test_methodology(q, expect):
    r = k._methodology_lookup(q)
    assert r and expect in r["answer"] and not re.search(r"[\u0400-\u04ff]", r["answer"])


def test_office_drills_are_off_ice_only():
    r = k._office_lookup("What off-ice exercises help rotation speed?")
    assert r and r["structured"] == "kb_office"
    names = {d["name"] for d in k._kb_yaml("drills.yaml") if d.get("kind") != "off_ice"}
    assert not any(n in r["answer"] for n in names)


@pytest.mark.parametrize(
    "q,name",
    [
        ("What is a toe loop?", "Toe loop — a toe jump"),
        ("Can you explain the salchow take-off?", "Salchow — an edge jump"),
        ("what is an axel", "Axel — an edge jump"),
    ],
)
def test_jump_definitions(q, name):
    r = k._jump_def_lookup(q)
    assert r and r["answer"].startswith(name)


# ── second set (chatbench2) ────────────────────────────────
@pytest.mark.parametrize(
    "q,fn,kind",
    [
        ("What should I eat before training?", "_scope_lookup", "out_of_scope"),
        ("How accurate is the rotation count?", "_app_lookup", "app_facts"),
        ("What camera angle is best for analysis?", "_app_lookup", "app_facts"),
        ("What is GOE?", "_glossary_lookup", "glossary"),
        ("What is a combination jump?", "_glossary_lookup", "glossary"),
        ("Should I stretch before skating?", "_science_lookup", "kb_science"),
        ("Can kids do plyometrics?", "_science_lookup", "kb_science"),
        ("How can I spin faster?", "_science_lookup", "kb_science"),
        ("How do I build confidence for a new jump?", "_science_lookup", "kb_science"),
        ("How long until I can land a double?", "_methodology_lookup", "kb_methodology"),
        ("What's a good off-ice workout for skaters?", "_office_lookup", "kb_office"),
        ("How do I land a single axel?", "_jump_def_lookup", "jump_definition"),
    ],
)
def test_second_battery_routes(q, fn, kind):
    r = getattr(k, fn)(q)
    assert r and r["structured"] == kind
    assert not re.search(r"[\u0400-\u04ff]", r["answer"])


def test_accuracy_answer_uses_only_measured_figures():
    a = k._app_lookup("How accurate is it?")["answer"]
    assert "93.3%" in a and "189 of 216" in a and "40 of the 54" in a


def test_science_facts_are_english():
    facts = k._kb_yaml("science.yaml")["facts"]
    assert facts and all(f["text"] and not re.search(r"[\u0400-\u04ff]", f["text"]) for f in facts)


def test_off_ice_safety_question_is_not_a_drill_list():
    q = "Is it safe to practice jumps off-ice every day?"
    assert k._office_lookup(q) is None
    assert k._methodology_lookup(q)["structured"] == "kb_methodology"


# ── fourth set of questions (slow LLM fallback, 60-90 s) ────────
def test_two_jumps_are_compared_not_defined_once():
    r = k._compare_lookup("What is the difference between an Axel and a Lutz?")
    assert r and r["structured"] == "jump_compare"
    assert "Axel" in r["answer"] and "Lutz" in r["answer"]
    assert k._compare_lookup("What is an Axel?") is None


def test_toe_loop_vs_loop_is_two_jumps():
    r = k._compare_lookup("toe loop vs loop")
    assert r and "Toe loop" in r["answer"] and "Loop (edge jump)" in r["answer"]


def test_why_not_sure_explains_the_limits():
    r = k._unsure_lookup("Why does the app say not sure?")
    assert r and "Lutz and flip" in r["answer"] and "not a verdict on your skating" in r["answer"]
    assert k._unsure_lookup("Why do I fall?") is None


def test_helmet_is_out_of_scope_not_a_slow_guess():
    r = k._scope_lookup("Should I wear a helmet?")
    assert r and r["structured"] == "out_of_scope" and "coach" in r["answer"]


def test_practice_at_home_gives_office_drills():
    r = k._office_lookup("Can I practice jumps at home?")
    assert r and r["structured"] == "kb_office"


def test_a_concrete_problem_is_not_hijacked_by_my_level():
    assert k._personal_lookup("My landing foot wobbles, what should I do?") is None
    assert k._personal_lookup("What should I do?") is not None


def test_no_backspace_characters_in_regexes():
    package = Path(k.__file__).parent
    assert all("\x08" not in path.read_text(encoding="utf-8") for path in package.glob("*.py"))


def test_waltz_jump_is_defined():
    r = k._jump_def_lookup("what is a waltz jump")
    assert r and "half-revolution" in r["answer"] and "all six" not in r["answer"]


def test_hours_per_week_answers_first():
    r = k._methodology_lookup("How many hours should I practice per week as an adult beginner?")
    assert r and r["answer"].startswith("In short:") and "2-4 sessions a week" in r["answer"]


def test_wobbly_landing_gets_the_fix_branch():
    r = k._error_fix_lookup("My landing foot wobbles, what should I do?")
    assert r and "landing" in r["answer"].lower()


@pytest.mark.parametrize("q", ["Can this app help me?", "What can you do?", "What does this app do?"])
def test_about_the_app_is_instant(q):
    r = k._about_lookup(q)
    assert r and "rotation count" in r["answer"] and "does not replace a coach" in r["answer"]


def test_not_every_app_question_is_about():
    assert k._about_lookup("How accurate is this app?") is None


def test_which_is_harder_uses_isu_base_values():
    # data/ is not in git: the table exists on the laptop and in the Modal image, not in the cloud session
    if not k._ISU_REF.is_file():
        pytest.skip("data/isu/jump_reference.json is missing on disk (tools/build_isu_reference.py)")
    r = k._compare_lookup("Is a double Axel harder than a triple Salchow?")
    assert r and r["structured"] == "isu_compare"
    assert "3.3" in r["answer"] and "2016" in r["answer"]


def test_why_not_sure_is_not_hijacked_by_about_the_app():
    r = k.ask("Why does the app say not sure?", lang="en")
    assert r.get("structured") == "app_facts" and "“Not sure” means" in r["answer"]


# ── questions that need a sourced answer ──────────────────────────


@pytest.mark.parametrize(
    "q",
    ["Can I take ibuprofen for my sore knee before practice?", "Is it ok to take painkillers before a competition?"],
)
def test_medication_is_out_of_scope(q):
    r = k._scope_lookup(q)
    assert r and r["structured"] == "out_of_scope" and "doctor" in r["answer"]


@pytest.mark.parametrize(
    "q", ["Which skates and blades should I buy as a beginner?", "How often should I sharpen my blades?"]
)
def test_buying_skates_is_out_of_scope(q):
    r = k._scope_lookup(q)
    assert r and r["structured"] == "out_of_scope" and "skate" in r["answer"]


@pytest.mark.parametrize(
    "q", ["Which part of the blade do I pick with on a toe loop?", "Does touching the ice with the blade cost points?"]
)
def test_blade_technique_is_not_equipment(q):
    assert k._scope_lookup(q) is None


def test_single_jump_value_comes_from_isu_table(tmp_path, monkeypatch):
    ref = tmp_path / "jump_reference.json"
    ref.write_text('{"jumps": {"2Lz": {"name": "double Lutz", "revolutions": 2, "base_value": 2.1}}}', encoding="utf-8")
    monkeypatch.setattr(k, "_ISU_REF", ref)
    r = k._worth_lookup("How much is a double Lutz worth in ISU points?")
    assert r and r["structured"] == "isu_value" and "2.1 points" in r["answer"] and "2016" in r["answer"]
    assert k._worth_lookup("How many points is a double Lutz?")
    # two jumps is 'what is harder', not this branch; without a revolution number we do not guess
    assert k._worth_lookup("Is a double Lutz worth more than a triple toe loop?") is None
    assert k._worth_lookup("How much is a Lutz worth?") is None


def test_excerpt_has_no_broken_edges_or_wiki_markup():
    raw = (
        "studied jump in figure skating. It is the only jump that begins with a forward takeoff, "
        "which makes it the easiest jump to identify. === Firsts === == Execution == The ISU defines "
        "the Axel as a jump with a forward take-off and an extra half revolution, and it is required in"
    )
    t = k._tidy_excerpt(raw)
    assert t.startswith("It is the only jump") and "==" not in t and "Firsts" not in t
    assert t.endswith("…")
    # an excerpt is a substring of the source: no text is added
    assert t.rstrip("…").split(" The ISU")[0] in raw


@pytest.mark.parametrize(
    "q",
    [
        "How much air time do I need for a double Axel?",
        "How much height for a triple toe loop?",
        "How do I score a clean double flip?",
    ],
)
def test_worth_does_not_hijack_how_much_technique(q):
    # a bare 'how much' returned the point value for a question about flight
    assert k._worth_lookup(q) is None


def test_how_to_tell_under_rotation_explains_the_marks():
    # it answered with the causes of under-rotation instead of what it is
    r = k._isu_marks_lookup("How do I know if my jump is under-rotated?")
    assert r and r["structured"] == "isu_marks" and "<<" in r["answer"]
    assert k._isu_marks_lookup("Is my axel under-rotated?") is None  # this is the person's own journal


@pytest.mark.parametrize("q", ["How do I stop being scared of falling?", "I am nervous before competitions, any tips?"])
def test_fear_gets_sourced_answer_not_a_random_excerpt(q):
    # instead of a limit, research on skaters' coping, with sources
    r = k._sourced_lookup(q)
    assert r and r["structured"] == "sourced" and "coach" in r["answer"] and "Gould" in r["answer"]


def test_named_jump_is_not_a_level_question():
    # «My waltz jump feels weak…» is about a jump, not «Your level is not measured yet»
    assert k._personal_lookup("My waltz jump feels weak, what should I work on?") is None


@pytest.mark.parametrize(
    "q",
    ["What is the easiest jump to learn?", "Which jump comes after the Salchow?", "In what order are jumps learned?"],
)
def test_jump_order_uses_isu_scale_and_says_no_fixed_order(q):
    # «easiest jump» returned an excerpt «Axel … most difficult jump»
    if not k._ISU_REF.is_file():
        pytest.skip("data/isu/jump_reference.json is missing on disk")
    r = k._order_lookup(q)
    assert r and r["structured"] == "jump_order"
    assert "waltz" in r["answer"] and "no single prescribed learning order" in r["answer"]


def test_jump_order_leaves_combinations_alone():
    assert k._order_lookup("What is the first jump in a combination?") is None


@pytest.mark.parametrize(
    "q,route",
    [
        ("What is a toe pick for?", "_glossary_lookup"),
        ("What does under-rotated mean?", "_isu_marks_lookup"),
        ("How do I land on one foot?", "_error_fix_lookup"),
    ],
)
def test_beginner_questions_get_instant_answers(q, route):
    assert getattr(k, route)(q)


@pytest.mark.parametrize(
    "q,kind",
    [
        ("What is a good air time for a double?", "sourced"),
        ("How do I stop being scared of falling?", "sourced"),
        ("Do I need a coach?", "app_facts"),
        ("How long does it take to learn an Axel?", "app_facts"),
    ],
)
def test_former_no_answer_questions_have_grounded_answers(q, kind):
    # not «The sources do not answer this» or an off-topic excerpt
    r = k._sourced_lookup(q)
    assert r and r["structured"] == kind and r["grounded"]
    if kind == "sourced":
        assert r["sources"] and all(s["source"] for s in r["sources"])


def test_own_air_time_is_left_to_the_journal():
    assert k._sourced_lookup("What was my air time?") is None


def test_lexical_fallback_finds_the_passage_while_e5_warms(monkeypatch):
    # until the e5 warm-up ends, BM25 over the same corpus
    rows = [
        {"text": "The Salchow was invented by Ulrich Salchow in 1909.", "source": "S", "url": ""},
        {"text": "The loop jump takes off from a back outside edge.", "source": "S", "url": ""},
    ]
    k._LEX.clear()
    monkeypatch.setattr(k, "_load", lambda: (rows, None))
    hits = k._lexical_hits("Who invented the Salchow?", 5)
    assert hits and any("Ulrich Salchow" in h["text"] for h in hits)
    assert all(h["retrieval"] == "lexical" for h in hits)
    assert k._lexical_hits("zzzq qqqz") is None
    k._LEX.clear()
