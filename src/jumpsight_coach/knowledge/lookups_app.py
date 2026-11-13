"""Structured lookups about the product itself and the user's own data, plus sourced answers."""

from __future__ import annotations

_MY = (
    r"\bmy level\b|\bwhat level am i\b|work on next|what should i (?:work on|practi[cs]e|train|focus on)|^\s*what should i do\??\s*$|"
    r"\bmy progress\b"
)


def _personal_lookup(question: str) -> dict | None:
    """“My level”, “what next” — from the profile and today's session, not the encyclopedia."""
    import re as _re

    if not _re.search(_MY, question.lower()):
        return None
    # "My waltz jump feels weak, what should I work on?" is about a jump, not the level
    if _re.search(r"\b(?:waltz|toe[- ]?loop|axel|salchow|lutz|flip|loop)\b", question.lower()):
        return None
    lines = []
    try:
        from ..skills import profile as _sp

        sp = _sp("en")
    except Exception:  # noqa: BLE001
        sp = {}
    if sp.get("level"):
        lines.append(f"Your level: {sp.get('level_name')} (basis: {sp.get('basis')}).")
    else:
        lines.append(
            "Your level is not measured yet — it needs at least two analysed videos with a measured revolution count."
        )
    for _k in ("note", "need_more_note"):
        _n = str(sp.get(_k) or "").strip()
        if _n:
            _n = _n[0].upper() + _n[1:]
            lines.append(_n if _n.endswith((".", "!", "?")) else _n + ".")
    try:
        from ..api import today as _today

        t = _today(lang="en")
    except Exception:  # noqa: BLE001
        t = {}
    if t.get("focus_label"):
        drills = [
            b.get("name")
            for b in (t.get("blocks") or [])
            if b.get("drill_id") and b.get("block") in ("main", "warmup_specific")
        ][:3]
        lines.append(f"Today's focus: {t['focus_label']}.")
        if drills:
            lines.append("Main drills: " + "; ".join(drills) + ".")
        lines.append("The full session with steps is in Training.")
    elif t.get("message"):
        lines.append(str(t["message"]))
    return {
        "answer": "\n".join(lines),
        "grounded": True,
        "structured": "personal",
        "sources": [{"source": "your profile and analyses", "url": "", "score": 1.0}],
    }


def _personal_data_lookup(question: str) -> dict | None:
    """Personal questions: instant answers from the user's journal (coach/user_snapshot)."""
    from ..user_snapshot import personal_answer

    return personal_answer(question)


_OUT_OF_SCOPE = (
    r"\b(eat|food|meal|diet|nutrition|calorie\w*|weight loss|lose weight|supplement\w*|"
    r"protein|medication|medicine|painkiller\w*|"
    # Medication names must reach the out-of-scope answer instead of a search that has no source.
    r"ibuprofen|paracetamol|acetaminophen|aspirin|advil|tylenol|naproxen|pills?|drugs?)\b"
)


_GEAR = (
    r"\bhelmets?\b|protective gear|\bpads?\b|wrist guards?|knee pads?|equipment|what to wear|\bgear\b|"
    # Only purchase, selection and sharpening count as equipment: "which part of the blade" is technique.
    r"\b(?:buy|buying|purchase|brands?|price|sharpen\w*|fit(?:ting)?)\b[^.?!]*\b(?:skates?|blades?|boots?)\b|"
    r"\b(?:skates?|blades?|boots?)\b[^.?!]*\b(?:buy|buying|purchase|brands?|price|sharpen\w*)\b"
)


_FEAR = (
    r"\b(?:scared|afraid|fear(?:ful)?|frightened|nervous|anxious|anxiety)\b|"
    r"\bmental block\b"
)
_AIRTIME_Q = (
    r"\b(?:air|flight|hang)[- ]?time\b|\bhow long\b[^?]*\b(?:in the air|airborne)\b|"
    r"\btime in the air\b"
)
_COACH_Q = (
    r"\bdo i (?:really )?need a coach\b|\bwithout a coach\b|\b(?:alone|by myself|on my own)\b[^?]*\b(?:learn|jump)|"
    r"\b(?:learn|jump)\w*\b[^?]*\b(?:alone|by myself|on my own)\b|\bcan (?:this|the) app replace\b"
)
_LEARN_TIME_Q = r"\bhow (?:long|many (?:years|months|weeks))\b[^?]*\b(?:learn|land|get|master)\b"


def _sourced_lookup(question: str) -> dict | None:
    """Questions the base was silent on, answered with sources.

    Covers "What is a good air time for a double?", "How do I stop being scared of falling?", "Do I need a
    coach?" and "How long does it take to learn an Axel?". The texts come only from verified sources (links
    below) or from the position of the app itself; there are no figures without a source.
    """
    import re as _re

    ql = question.lower()
    if _re.search(_AIRTIME_Q, ql) and not _re.search(r"\bmy\b", ql):
        return {
            "answer": "\n".join(
                [
                    "Elite skaters stay in the air about the same time whether they do a single, double or triple Axel; "
                    "the extra turns come from spinning faster, not from flying longer (King, Arnold & Smith, 1994).",
                    "For scale: triple Axels of junior women measured 0.55–0.60 s in the air (Ikegami et al., 2004).",
                    "So for a double the deciding number is usually rotation speed: about 3.5 turns per second in elite "
                    "doubles (Bruening 2018). The answer screen shows your air time and rotation speed with their ± error, "
                    "and compares the speed with that norm.",
                ]
            ),
            "grounded": True,
            "structured": "sourced",
            "sources": [
                {
                    "source": "King, Arnold & Smith (1994), A biomechanical comparison of single, double and "
                    "triple Axels, Journal of Applied Biomechanics 10:51–60",
                    "url": "",
                    "score": 1.0,
                },
                {
                    "source": "Ikegami et al. (2004), Kinematic analysis of triple Axel jumps of women's figure "
                    "skaters, Nagoya Journal of Health, Physical Fitness & Sports 27(1):17–26",
                    "url": "https://nagoya.repo.nii.ac.jp/records/2005149",
                    "score": 1.0,
                },
                {"source": "Bruening 2018 (PLOS ONE): rotation speed norms", "url": "", "score": 1.0},
            ],
        }
    if _re.search(_FEAR, ql):
        return {
            "answer": "\n".join(
                [
                    "There is no study in this app's sources on fear of falling in skaters specifically. What research on "
                    "skaters does show:",
                    "• National champion figure skaters coped with stress mainly through rational thinking and self-talk, "
                    "a positive focus, support from their coach and family, and relaxation and visualisation before "
                    "competing (Gould, Finch & Jackson, 1993).",
                    "• Fear after an injury is worth working on with a sport psychologist; one published case of a competitive "
                    "skater used Acceptance and Commitment Therapy over six sessions (Wood & Turner, 2023).",
                    "Tell your coach about the fear: new elements are built up step by step under their control. If the fear "
                    "comes with pain or after an injury, see a doctor first.",
                ]
            ),
            "grounded": True,
            "structured": "sourced",
            "sources": [
                {
                    "source": "Gould, Finch & Jackson (1993), Coping strategies used by national champion "
                    "figure skaters, Research Quarterly for Exercise and Sport 64(4):453–468",
                    "url": "",
                    "score": 1.0,
                },
                {
                    "source": "Wood & Turner (2023), ACT for (re)injury anxiety in a competitive figure skater "
                    "(accepted manuscript, Manchester Metropolitan University)",
                    "url": "https://e-space.mmu.ac.uk/633341",
                    "score": 1.0,
                },
            ],
        }
    if _re.search(_COACH_Q, ql):
        return {
            "answer": "\n".join(
                [
                    "For learning new jumps, yes. This app measures what one camera can see — air time, rotation, "
                    "landing faults — and suggests drills, but it cannot see your take-off edge reliably, cannot catch you, "
                    "and cannot tell when a jump is unsafe for you to try.",
                    "Use it between lessons and show your coach the analyses: the Profile has a code that lets your coach "
                    "follow them and leave comments.",
                ]
            ),
            "grounded": True,
            "structured": "app_facts",
            "sources": [],
        }
    if _re.search(_LEARN_TIME_Q, ql):
        return {
            "answer": "\n".join(
                [
                    "The knowledge base has no reliable figure for how long a jump takes to learn: it depends on age, "
                    "training hours, off-ice preparation and coaching, and published numbers vary widely.",
                    "What it can say: the Axel is the hardest single jump — it takes off forwards, so it has an extra half "
                    "turn, and its ISU base value is 1.1 points against 0.4–0.6 for the other singles (ISU competitions "
                    "2016–2017). Your coach can judge when you "
                    "are ready; in the app, Progress shows whether your rotation and landings are improving over time.",
                ]
            ),
            "grounded": True,
            "structured": "app_facts",
            "sources": [],
        }
    return None


def _scope_lookup(question: str) -> dict | None:
    """What the app does not know: say so directly, rather than slip in an excerpt."""
    import re as _re

    if not _re.search(_OUT_OF_SCOPE + "|" + _GEAR, question.lower()):
        return None
    if _re.search(_GEAR, question.lower()):
        return {
            "answer": (
                "Equipment (skates, blades and sharpening, helmets, pads, guards) is outside what "
                "this app measures. What fits your level is a question for your coach, your rink "
                "and a skate fitter."
            ),
            "grounded": True,
            "structured": "out_of_scope",
            "sources": [],
        }
    return {
        "answer": (
            "Nutrition, weight and medication are outside what this app covers — its "
            "knowledge base is jump technique, training structure and the ISU rules. "
            "For food and supplements ask a sports dietitian; for medication, a doctor."
        ),
        "grounded": True,
        "structured": "out_of_scope",
        "sources": [],
    }


_APP_Q = (
    r"camera|film(?:ing)?\b|record(?:ing)?\b|angle|\bfps\b|frame rate|accura|reliab|"
    r"how (?:does|do) (?:the|this) app|trust|precise|how (?:sure|confident)"
)


def _app_lookup(question: str) -> dict | None:
    """About the product itself: how to film and how accurate the numbers are: only what is measured."""
    import re as _re

    ql = question.lower()
    if not _re.search(_APP_Q, ql):
        return None
    if _re.search(r"accura|reliab|trust|precise|how (?:sure|confident)", ql):
        lines = [
            "How accurate it is — measured, not promised:",
            "• Jump count: on studio motion-capture jumps with known truth, the app measured "
            "189 of 216 and its count matched the truth in 93.3% (median error 0.04 "
            "revolutions). Phone footage at a rink is harder, so the count is often shown "
            "as not certain or not measured there.",
            "• Jump name: correct on 40 of the 54 videos in our reference set, end to end.",
            "• Lutz vs flip is an edge call that one phone camera cannot see reliably, so the app "
            "never names either with high confidence and shows “Lutz or flip” when unsure.",
            "• When the uncertainty is too wide — for example the decimal revolution count with a "
            "band wider than half a turn — the number is withheld and the reason is shown.",
            "Every number on the result screen has its confidence next to it.",
        ]
    else:
        lines = [
            "What decides how much can be measured on a video:",
            "• A side view shows take-off and landing best; from other angles the app says what it could not see.",
            "• The whole jump in frame lets it measure the entry and exit too; a cut-off jump is measured only where it is visible.",
            "• More frames per second means more frames in the air, so a tighter measurement.",
            "Any phone video works: if it falls short, the result says what could not be measured and why.",
        ]
    return {
        "answer": "\n".join(lines),
        "grounded": True,
        "structured": "app_facts",
        "sources": [{"source": "JumpSight measurement records", "url": "", "score": 1.0}],
    }


_ABOUT_Q = (
    r"(?:can|will|does|could) (?:this|the|your) app|what (?:can|does|will) (?:this|the|your) app|"
    r"what (?:can|do) you do|what (?:is|'s) (?:this|the) app|how (?:can|does|do) (?:this|the) app (?:help|work)|"
    r"what can i do (?:here|with this)|"
    # «what can you do», «help», «who are you»
    r"^\s*(?:help|hi|hello|hey)\W*$|what (?:can|do) you (?:know|help)|who are you|how do you work"
)


def _about_lookup(question: str) -> dict | None:
    """«Can this app help me?» — what the app actually does, with no promises beyond what is measured."""
    import re as _re

    if not _re.search(_ABOUT_Q, question.lower()):
        return None
    lines = [
        "What this app does:",
        "• Film or upload a jump video from your phone. You get the jump name and the rotation count, "
        "each with how sure the system is, plus air time and height with their error margins.",
        "• It checks execution errors it can see on that video (falls, step-outs, axis and more) and "
        "says which ones it could not check.",
        "• It builds today's training session from your videos (or from a goal you pick) and adapts "
        "it to how the last session felt.",
        "• You can ask here about technique, ISU rules and drills; answers come from its knowledge base with sources.",
        "• A coach can follow your analyses and set your session focus if you accept their request.",
        "It does not replace a coach on the ice: it measures what one phone camera can see and tells you "
        "where that limit is.",
    ]
    return {
        "answer": "\n".join(lines),
        "grounded": True,
        "structured": "app_facts",
        "sources": [{"source": "JumpSight measurement records", "url": "", "score": 1.0}],
    }


_UNSURE = (
    r"not sure|not certain|unsure|uncertain|low confidence|not determined|not measured|"
    r"not resolved|can'?t tell|cannot tell|doesn'?t know"
)


def _unsure_lookup(question: str) -> dict | None:
    """«Why does the app say "not sure"» — the real, measured causes, with nothing invented."""
    import re as _re

    ql = question.lower()
    if not _re.search(_UNSURE, ql) or not _re.search(r"\b(?:app|system|result|it|analysis|coach)\b", ql):
        return None
    lines = [
        "“Not sure” means the video did not give enough evidence for a firm answer. The usual reasons:",
        "• Lutz and flip differ only by the take-off edge, which one phone camera cannot see reliably — so they are shown as a pair.",
        "• The decimal rotation count is withheld when its uncertainty band is wider than half a turn; the flight time sets that band.",
        "• Frames where the skater could not be tracked are counted and shown, never guessed.",
        "It is a limit of this video, not a verdict on your skating. The result screen says which measurement fell short and why.",
    ]
    return {
        "answer": "\n".join(lines),
        "grounded": True,
        "structured": "app_facts",
        "sources": [{"source": "JumpSight measurement records", "url": "", "score": 1.0}],
    }


_MY_JUMP = r"\b(?:is|was|did) my\b|\bmy (?:last|latest) (?:jump|video|attempt|analysis)"
_COUNT_EN = {"single": "single", "double": "double", "triple": "triple", "quad": "quad"}


def _my_jump_lookup(question: str) -> dict | None:
    """«Is my Axel under-rotated» — answered from the person's own analysis journal, not from an encyclopedia."""
    import re as _re

    ql = question.lower()
    if not _re.search(_MY_JUMP, ql):
        return None
    try:
        from ..jobs import history

        rows = history()
    except Exception:  # noqa: BLE001
        rows = []
    want = next((j for j in ("axel", "salchow", "toe loop", "loop", "flip", "lutz") if j in ql), None)
    if want:
        rows = [r for r in rows if want in str(r.get("jump") or "").lower()]
    if not rows and not want and not _re.search(r"\bunder[- ]?rotat|\bdowngrad|\bhow many (?:turns|rotations)", ql):
        # With no analysed video, «Why is my rotation slow?» falls back to the knowledge base (causes and drills)
        # instead of returning only «No analysed video yet».
        return None
    if not rows:
        _nm = {
            "axel": "an Axel",
            "salchow": "a Salchow",
            "toe loop": "a toe loop",
            "loop": "a loop",
            "flip": "a flip",
            "lutz": "a Lutz",
        }
        what = _nm.get(want, "a jump")
        return {
            "answer": (
                f"There is no analysed video of {what} in your profile yet. Upload one: "
                "the result shows the jump count in the air, with its confidence."
            ),
            "grounded": True,
            "structured": "my_jump",
            "sources": [],
        }
    import datetime as _dt

    lines = ["From your analysed videos (latest first):"]
    for r in rows[:3]:
        d = _dt.datetime.fromtimestamp(float(r.get("ts") or 0)).strftime("%b %d")
        name = r.get("name_display") or r.get("jump") or "jump"
        cnt = _COUNT_EN.get(str(r.get("count_named") or ""))
        rev = r.get("revolutions")
        part = f"{d} · {name}"
        part += f" · {cnt}" if cnt else " · count not measured"
        if isinstance(rev, (int, float)):
            part += f" · {rev:.2f} rev in the air"
        if r.get("count_confidence") == "low":
            part += " (count not certain)"
        lines.append("• " + part)
    lines.append(
        "The app measures the rotation in the air. Whether a panel calls it q, < or << "
        "depends on the landing on the ice, which a phone video does not show reliably."
    )
    return {
        "answer": "\n".join(lines),
        "grounded": True,
        "structured": "my_jump",
        "sources": [{"source": "your profile and analyses", "url": "", "score": 1.0}],
    }
