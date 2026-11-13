"""Assembly of the session blocks (warm-up, main, volume, cool-down, check) and session text helpers."""

from __future__ import annotations

import time

from .outcomes import _log
from .rules import goal_label


def assemble_steps(pool, eligible_ids, focus, causes, by_id, notes, freq, age, pain, fit) -> list[dict]:
    """Turn the day's drill pool into ordered session blocks.

    `notes` is extended in place with the explanations that this step produces.
    """

    def _block_of(d: dict) -> str:
        if d.get("block"):
            return d["block"]
        if set(d.get("targets", [])) & {"low_height", "rotation_power"}:
            return "power"
        # When flexibility is the target of the day, Bellman's positions are the main work (after the warm-up),
        # not the cool-down: otherwise the session would be a single drill in the cool-down.
        if focus in ("spin_flexibility", "spin_position") and focus in d.get("targets", []):
            return "skill"
        if "spin_flexibility" in d.get("targets", []):
            return "cooldown"
        return "skill"

    # No replacement or fallback bypasses today's ceiling and safety.
    pool = [d for d in pool if d["id"] in eligible_ids]
    skill = [d for d in pool if _block_of(d) == "skill"]
    power = [d for d in pool if _block_of(d) == "power"]
    cool = [d for d in pool if _block_of(d) == "cooldown"]

    def item(d: dict, block: str, note: str = "") -> dict:
        # What not to do comes from the reasons of the error, not from invention. The mistakes_to_avoid field
        # is filled in only for 6 of 49 drills (12%), and text from an LLM cannot fill it: a project invariant
        # forbids presenting as knowledge something that is not in the source. kb/causes.yaml holds the causes of
        # each error with an evidence level and a reference (part of it level A: Yamaguchi 2025, King 2005,
        # Bruening 2018). So when the drill has no list of its own, the causes of the error that the drill works
        # on are shown, not presented as specific to the drill. Each line carries its own evidence and source.
        mistakes = [m.get("mistake") for m in d.get("mistakes_to_avoid", []) if m.get("mistake")]
        watch = []
        if not mistakes:
            for t in d.get("targets") or []:
                for c in ((causes.get(t) or {}).get("causes") or [])[:2]:
                    txt = c.get("text")
                    if txt and txt not in [w["text"] for w in watch]:
                        watch.append({"text": txt, "evidence": c.get("evidence", "B"), "source": c.get("source", "")})
                if len(watch) >= 2:
                    break
        return {
            "block": block,
            "drill_id": d["id"],
            "name": d["name"],
            # a floor drill must not read as 'singles on the ice again' after a double Lutz
            "where": "off_ice" if d.get("kind") == "off_ice" else "on_ice",
            "steps": d.get("steps") or [],
            "cues": d.get("cues", [])[:2],
            "dosage": d.get("dosage", ""),
            "success": d.get("success") or d.get("exit_criteria") or "completed without bail-outs",
            "mistakes": mistakes,
            # a separate field, not an addition to mistakes: it is a cause of the error
            # in general, not an error IN THIS drill, and the two must not be confused.
            "watch_for": watch[:2],
            # the source lesson file name is never exposed
            "has_demo": bool(d.get("video")),
            "url": d.get("url", ""),
            "evidence": d.get("evidence", "B"),
            "note": note,
        }

    steps: list[dict] = []
    steps.append(
        {
            "block": "warmup",
            "drill_id": None,
            "name": "General warm-up",
            "steps": ["easy jog or hops on the spot, 2-3 min", "circle the arms, hips and ankles"],
            "cues": [],
            "dosage": "3-5 min",
            "success": "warm through, breathing even",
            "mistakes": ["static stretching BEFORE work — it belongs at the end"],
            "video": "",
            "url": "",
            "evidence": "A",
            "note": "",
        }
    )
    if skill:
        # specific warm-up: the simplest drill of the day at half strength;
        # the main work: the others, so the same thing is not done twice in a row
        warm = min(skill, key=lambda d: d.get("level", 1))
        rest_skill = [d for d in skill if d["id"] != warm["id"]]
        # With one skill drill per target (low_height, rotation_power, where most drills go into the power
        # block) a fallback to the same drill would show it twice in a row, in the specific warm-up and in the
        # main block (2 of 8 targets). One drill is the day's work; the specific warm-up is then made from it
        # too, and this is said plainly in one line.
        if rest_skill:
            steps.append(item(warm, "warmup_specific", "at half effort — this is preparation, not the work"))
        else:
            rest_skill = [warm]
            notes.append(
                "there is one drill for this goal in the base — do the first "
                "set at half effort as a warm-up, then at full effort"
            )
        # Volume by frequency (NCCP): rare sessions -> fuller sessions; daily -> lighter, because the load is
        # spread across the week. Low endurance (measured by a test) cuts the volume by one more step.
        n_main = 3 if freq <= 1 else 2 if freq <= 2 else 1
        if fit.get("limit_volume"):
            n_main = max(1, n_main - 1)
        for d in rest_skill[:n_main]:
            steps.append(item(d, "main", "while you are fresh — the main work of the day"))
    # Age: in a growth spurt (13-17) jump volume is not increased (Moran meta-analysis: blunted gains, higher
    # overload risk). `age` is a number (the option index from the survey), so it is compared with an int.
    if age == 1 and power:
        notes.append("age 13-17: growth spurt — hold the volume, do not add to it")
        power = power[:1]
    # weak leg strength (measured): explosive drills are removed from the day, the base comes first:
    # explosive work on weak legs does not train, it exhausts
    if fit.get("limit_power"):
        power = []
    # Recovery between impact days: impact (jump, plyometric) work two days in a row gives accumulated fatigue,
    # not gain, because adaptation happens in recovery. The standard pause between heavy plyometric sessions
    # is about two days. The time of the last session is used, not the day number: a person may open the app
    # twice in one day or skip three.
    _log_all = _log()
    if power and _log_all:
        _last = _log_all[-1]
        _gap_h = (time.time() - float(_last.get("ts", 0))) / 3600.0
        # Impact is determined from the drill itself, not from a journal field: the journal stores only
        # drill_id, so existing records stay valid.
        _POWER = {"low_height", "rotation_power"}
        _had_power = any(
            _POWER & set((by_id.get(b.get("drill_id")) or {}).get("targets", []))
            for b in _last.get("blocks", [])
            if b.get("drill_id")
        )
        if _gap_h < 20 and _had_power:
            power = []
            notes.append(
                f"the last session was {_gap_h:.0f} h ago and included impact "
                f"work — none of it today. Gains come from recovery, not from "
                f"a second hard day in a row"
            )
    for d in power[:1]:
        steps.append(item(d, "volume", "full recovery between sets"))
    if cool:
        steps.append(item(cool[0], "cooldown", ""))
    else:
        steps.append(
            {
                "block": "cooldown",
                "drill_id": None,
                "name": "Cool-down",
                "steps": ["static stretching, 2-3 min", "calm breathing"],
                "cues": [],
                "dosage": "2-3 min",
                "success": "heart rate settled",
                "mistakes": [],
                "video": "",
                "url": "",
                "evidence": "A",
                "note": "",
            }
        )
    steps.append(
        {
            "block": "control",
            "drill_id": None,
            "name": "Check: film 3 attempts",
            "steps": [
                "film 3 attempts of the target jump",
                "upload them — the system compares against your previous attempts",
            ],
            "cues": [],
            "dosage": "3 attempts",
            "success": (
                "record 3 attempts for comparison; no change or an inconclusive analysis is also a valid result"
            ),
            "mistakes": [],
            "video": "",
            "url": "",
            "evidence": "A",
            "note": "this is the check for the day",
        }
    )

    # Pain: the system does not treat and does not diagnose. The session is replaced, not annotated, because
    # jumps and 'take 3 attempts' below a 'do not train' block would contradict it.
    if pain >= 2:
        # The most important message in the system ('it hurts, do not train') must be clear to every reader.
        steps = [
            {
                "block": "warning",
                "drill_id": None,
                "name": "No training today",
                "steps": (
                    [
                        "you reported that something hurts right now",
                        "this system does not diagnose or treat injuries",
                        "see a doctor or your coach",
                    ]
                ),
                "cues": [],
                "dosage": "",
                "success": "",
                "mistakes": [],
                "video": "",
                "url": "",
                "evidence": "A",
                "note": ("a session will be built once the pain is gone"),
            },
            {
                "block": "cooldown",
                "drill_id": None,
                "name": ("Allowed: gentle mobility"),
                "steps": (["easy joint circles with no load", "any movement that hurts — stop"]),
                "cues": [],
                "dosage": "5-10 min",
                "success": "",
                "mistakes": ["pushing through pain"],
                "video": "",
                "url": "",
                "evidence": "A",
                "note": "",
            },
        ]
        notes.append("pain reported — no jump work today")
    return steps


def _sentences(notes: list[str], lang: str) -> list[str]:
    """Explanations of the session as sentences: capitalised."""
    out = []
    for n in notes:
        s = str(n or "").strip()
        if s and s[0].islower():
            s = s[0].upper() + s[1:]
        out.append(s)
    return out


def _history_note(steps: list[dict], recent: list[str], lang: str = "en") -> str:
    """Honest text: counts the ACTUAL update, not the intention.

    Saying 'N not repeated' whenever history exists would be wrong when the day is an exact copy of yesterday's.
    """
    if not recent:
        return "first session"
    today = [b["drill_id"] for b in steps if b.get("drill_id")]
    if not today:
        return "session with no drills from the base"
    fresh = [i for i in today if i not in recent]
    if not fresh:
        return (
            f"the same {len(today)} drills — repetition supports learning; "
            f"a linked next step may open after 3 successful self-reported "
            f"performances, if today's limits allow it"
        )
    # the person needs plain words (is this the same as yesterday), not 'new drills vs past sessions: 5 of 5'
    if len(fresh) == len(today):
        return "all drills are new"
    if not fresh:
        return "same drills as last time"
    return f"{len(fresh)} of {len(today)} drills are new"


def _focus_text(code: str, causes: dict, lang: str) -> str:
    """Honest focus label: WHAT we train, and separately the typical cause from the knowledge base AS A REFERENCE. The cause stays visible, labelled as typical, not as fact."""
    label = goal_label(code, lang)
    blk = (causes.get(code) or {}).get("causes") or []
    cause = blk[0]["text"] if blk else None
    if not cause or cause == label:
        return label
    sep = " — common cause: "
    return f"{label}{sep}{cause}"
