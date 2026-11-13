"""Builds one day's session from a profile: focus, personalisation, drill pool, progression, blocks."""

from __future__ import annotations

import re
import time

from ..core import load_kb, pick_drills
from .blocks import _focus_text, _history_note, _sentences, assemble_steps
from .focus import _goals_of, _pick_focus, guard_focus, stuck_errors
from .outcomes import _last_used, _log, _outcome_streaks, _recent_drill_ids
from .rules import goal_label, science_for


def _fmt_date(ts: float, lang: str) -> str:
    # %-d (no leading zero) is a glibc strftime extension, unsupported by Windows' C runtime; %d works on both.
    t = time.localtime(ts)
    return time.strftime("%b %d, %Y", t)


def _demo_ids() -> set[str]:
    """Drills with a ready 3D character demo (jumpsight_coach.api.mascot_list, cached)."""
    try:
        from ..api import mascot_list

        return set(mascot_list())
    except Exception:  # noqa: BLE001
        return set()


def build_for_goal(goal: str, lang: str = "en", feel: str = "", want: str = "") -> dict:
    """Session by the goal the person chose themselves, without a video.

    There is no separate pipeline: the same Profile is assembled with the goal in place of a measured error,
    and the usual build() runs with all its rules (level, safety, history, progression). Only the source of
    the goal differs, and it is named in the output. No number here is measured, so none is shown.
    """
    from ..core import Profile

    class _GoalProfile(Profile):
        from_video = False  # goal chosen by the person: no clip existed

        def goals(self):
            return [goal]

    p = _GoalProfile(file="(chosen goal)", jump_name="unknown")
    out = build(p, lang=lang, feel=feel, want=want)
    out["from_goal"] = goal
    out["personalisation"] = [
        (
            "You picked this goal yourself — nothing here is measured from "
            "video, so the session has no numbers about your jump."
        )
    ] + list(out.get("personalisation") or [])
    return out


def build(
    profile,
    lang: str = "en",
    feel: str = "",
    want: str = "",
    analysis_ts: float | None = None,
    support_goal: str | None = None,
) -> dict:
    """profile: jumpsight_coach.core.Profile from the last analysis.

    feel: how the person feels TODAY: "fresh" | "ok" | "tired" | "sore".
    want: which session the person wants: "easy" | "normal" | "hard". Both are optional; without them the behaviour is unchanged.
    analysis_ts: when the video analysis was made, from which the errors were taken (epoch, s). It lets the
    focus name the specific analysis ("Why this for you" shows the error and the date of the video that found it).
    """
    drills_kb, causes = load_kb()
    by_id = {d["id"]: d for d in drills_kb}
    goals = profile.goals()
    # The focus follows priority, not list order: kb/prescription.yaml sets safety first, then foundation,
    # then details, and each step has a written reason and source.
    # A stable gap outweighs a one-off slip: one failed attempt out of twenty must not weigh the same as an
    # error that recurs in 8 of 10 attempts.
    try:
        from ..skills import persistent_gaps

        _pers = sorted(_goals_of(persistent_gaps()))
    except Exception:  # no history yet is not a problem
        _pers = []
    focus = _pick_focus(goals, _pers)
    # A target chosen by the person is not a measurement: guard_focus protects against an error from one weak
    # analysis and does not apply to targets without a video.
    _goal_chosen = not getattr(profile, "from_video", True) and bool(goals)
    if _goal_chosen:
        focus = goals[0]
    # An error code from a single low-confidence analysis may not become the session's topic (see guard_focus).
    # If the first candidate is rejected, the next one that passes the guard is taken rather than falling
    # straight to rotation basics: otherwise a one-off late_check_out ranking higher would hide step_out
    # present in every attempt.
    _cands = [] if _goal_chosen else list(dict.fromkeys([focus] + list(goals) + list(_pers)))
    _focus_reject = None
    _chosen = None
    for _c in _cands:
        _f, _rej = guard_focus(_c, _pers, profile)
        if _rej is None:
            _chosen = _f
            break
        if _focus_reject is None:
            _focus_reject = _rej
    if _goal_chosen:
        pass  # focus = the chosen target, see above
    elif _chosen is not None:
        focus, _focus_reject = _chosen, None
    else:
        focus = "basics_rotation"
    # The coach overrides automation: a target assigned by the coach (coach_focus.json, no older than 14 days)
    # is the day's focus, and the focus source records who and when.
    _coach_focus = None
    try:
        from ..accounts import coach_focus_of as _cfo
        from ..userctx import current_uid as _cu

        _u = _cu()
        _cf = _cfo(_u) if _u else None
        if _cf and time.time() - float(_cf.get("ts") or 0) < 14 * 86400:
            _coach_focus = _cf
            focus, _focus_reject = str(_cf["goal"]), None
    except Exception:  # noqa: BLE001
        _coach_focus = None
    # Personalisation: level, training frequency, age, coach, balance, pain. Defaults are the safest: until the
    # person says they have a coach, assume they do not, so a beginner without a survey gets no drills that
    # are unsafe without a spotter.
    lvl_min, freq, age, coach, balance, pain = 1, 1, 2, 0, 1, 0
    notes: list[str] = []
    # Why this focus when there are no errors: the person must see the link to the height drills after a good
    # jump. With no video (target chosen manually) there is no clip, so no statement about checks on it.
    if not profile.error_codes and getattr(profile, "from_video", True):
        if not profile.clean:
            notes.append(
                "no error was found, but the checks did not run on this clip "
                "either — this is base work, not a verdict that the jump was "
                "clean"
            )
        else:
            _r, _t = profile.revolutions, profile.air_time_s
            if _r and _t:
                _tgt = int(_r) + 1
                notes.append(
                    f"the attempt is clean at {_r:.2f} rev — the focus today "
                    f"is what a {_tgt}.0 would need, not the basics again"
                )
    focus_source: dict | None = None
    if support_goal and support_goal != focus:
        # forecast anchor day (plan): the main focus stays the main one,
        # this day works on its cause, and is labelled that way.
        _main = focus
        focus = support_goal
        goals = [support_goal] + [g for g in goals if g != support_goal]
        focus_source = {"kind": "plan_support", "error_code": focus, "main": _main}
        notes.append(
            f"supporting day: “{goal_label(focus, lang)}” works on what holds back “{goal_label(_main, lang)}”"
        )
    elif _coach_focus is not None:
        focus_source = {
            "kind": "coach",
            "error_code": focus,
            "by": _coach_focus.get("coach_name") or "",
            "date": _fmt_date(float(_coach_focus.get("ts") or 0), lang),
        }
        _by = _coach_focus.get("coach_name") or ("coach")
        notes.append(f"focus set by {_by} on {focus_source['date']}: “{goal_label(focus, lang)}”")
    elif _goal_chosen:
        focus_source = {"kind": "chosen_goal", "error_code": focus}
    elif _focus_reject is not None:
        focus_source = dict(_focus_reject)
        focus_source["error_code"] = focus
        notes.append(
            # one sentence about the signal, one about 'today'
            f"A possible “{goal_label(_focus_reject['rejected_code'], lang)}” issue showed up"
            + (
                f" ({_focus_reject['analyses_with_code']} of {_focus_reject['min_analyses']} videos needed)"
                if _focus_reject["analyses_with_code"]
                else ""
            )
            + f". The session targets it once {_focus_reject['min_analyses']} videos show it clearly; "
            f"today is base work."
        )
    elif focus in _pers:
        focus_source = {"kind": "persistent", "error_code": focus}
        _fl = goal_label(focus, lang)
        notes.append(
            f"“{_fl}” recurs in assessed attempts with medium/high evidence "
            f"from different video files — it is today's working focus"
        )
    elif focus in _goals_of(profile.error_codes):
        _date = _fmt_date(analysis_ts, lang) if analysis_ts else None
        focus_source = {"kind": "latest_analysis", "error_code": focus, "date": _date}
        _fl = goal_label(focus, lang)
        notes.append(
            f"“{_fl}” was found in your video analysis from {_date}"
            if _date
            else f"“{_fl}” was found in your latest video analysis"
        )
    have_survey = False
    try:
        from ..skills import load as load_profile_raw
        from ..skills import profile as skill_profile

        sp = skill_profile()
        if sp.get("level"):
            lvl_min = max(1, min(3, sp["level"] - 1))
        elif getattr(profile, "from_video", True) and (getattr(profile, "nominal_count", None) or 0) >= 2:
            # Floor from the rotation count. The level from history requires two reliable videos; until then it
            # stays at level 1, so a skater whose analysis counted a double Lutz would get half-turn and off-ice
            # waltz-jump drills. The count '2' is the floor of the step, not a level estimate, and is labelled so.
            lvl_min = 2
            notes.append(
                f"Your video showed a {profile.nominal_count}-revolution jump, so "
                f"on-ice single-jump basics are skipped (your level is confirmed "
                f"once two videos agree)."
            )
        ans = load_profile_raw().get("survey") or {}
        if ans:
            have_survey = True

            # value = index of the option (0-based), not a score
            def _i(k, d):
                try:
                    return int(ans.get(k, d))
                except (TypeError, ValueError):
                    return d

            freq = _i("freq", 0)
            coach = _i("coach", 0)
            balance = _i("balance", 0)
            pain = _i("pain", 0)
            age = _i("age", 2)
    except Exception as ex:  # invariant 4: no silent failures
        notes.append(f"profile could not be read ({str(ex)[:40]}) — running the session on the safest settings")
    if not have_survey:
        # One line for the three survey-dependent limits (survey, safety, balance): they all say the same thing,
        # 'you have not told us about yourself'.
        notes.append(
            "“About you” is not filled in, so the session stays on safe settings "
            "(no drills that need a spotter). Fill it in under Profile to unlock more."
        )

    # Physical tests (separate screen): measured strength, flexibility, endurance and balance change sessions
    # directly. Without tests nothing is invented; only survey answers apply.
    fit = {"notes": [], "has_data": False}
    fitness_state = "available"
    from ..fitness import FitnessStateUnavailable
    from ..fitness import gates as fit_gates

    try:
        fit = fit_gates(lang)
    except FitnessStateUnavailable:
        fitness_state = "unavailable"
        notes.append(
            "Fitness test results are unavailable. This session does not use them; retry loading on the fitness tests screen."
        )
    if fit.get("has_data"):
        notes.extend(fit["notes"])
        if fit.get("limit_balance"):
            balance = min(balance, 1)
        if fit.get("limit_flex"):
            # Limit the step, not the whole supporting topic.
            # KB/filter errors are not a missing profile and are not swallowed.
            drills_kb = [
                d for d in drills_kb if "spin_flexibility" not in d.get("targets", []) or int(d.get("level", 1)) <= 2
            ]

    # What the fitness tests measured is what is trained. The jump analysis never produces spin_flexibility or
    # balance_control targets, which would leave 16 drills of the base unreachable; the fitness test measures
    # these qualities directly, so a measurement, a drill and a direct link exist. The day's focus stays with
    # the measured jump: the additional targets only widen the pool as supporting work.
    extra_goals: list[str] = []
    if fit.get("limit_balance"):
        extra_goals.append("balance_control")
    if "flexibility" in fit.get("measured_groups", []):
        # A rated flexibility adds a target; no other test group measures it. Adding it only when flexibility
        # was limited left people with good flexibility without the Bellman ladder (measured: 0 of 12).
        # Weak flexibility -> preparatory work (level 2 ceiling above), good -> the positions themselves.
        extra_goals.append("spin_flexibility")
        if not fit.get("limit_flex"):
            extra_goals.append("spin_position")
        notes.append(
            "the fitness tests measured flexibility as your limiter, so the lead-in work for it is in today's session"
            if fit.get("limit_flex")
            else "flexibility measured fine, so spin positions are open — they "
            "are in today's session as supporting work"
        )

    # Safety: without a coach, drills that require a spotter (safety harness) are not shown at all; their
    # point is exactly that the coach provides the correction.
    if coach == 0:
        drills_kb = [d for d in drills_kb if not d.get("requires_supervision")]
        if have_survey:
            notes.append("drills that need a coach to spot you are hidden — you train without a coach")
    # Balance under 5 s: complex single-leg drills are premature.
    if balance <= 1:
        drills_kb = [d for d in drills_kb if d.get("level", 1) <= 2]
        # Without a survey the balance limit is an assumption, not a measurement: the default balance=1 limits
        # the steps deliberately (safety) but must not be worded as a fact about a person nobody asked.
        if have_survey:
            notes.append("one-leg balance is still short — taking easier steps")

    recent = _recent_drill_ids()

    # The mastery counter is computed before the pool is chosen, so that it can raise the complexity ceiling.
    by_id_all = {d["id"]: d for d in drills_kb}
    ok_count, fail_run = _outcome_streaks(_log())

    # The intersection of level_min and the filters can give an empty pool, so the bar is lowered until drills
    # are found, and the session says so.
    lvl_max = lvl_min + 1  # complexity ceiling

    # Self-rating of a specific drill opens only its continuation in the KB.
    # The general ceiling is stored separately: success in balance is not evidence of
    # readiness for all other drills of the same level.
    general_max = lvl_max
    successful_ids = {i for i, c in ok_count.items() if c >= 3 and i in by_id_all}
    progression_ids = successful_ids | {
        by_id_all[i].get("progression_id") for i in successful_ids if by_id_all[i].get("progression_id") in by_id_all
    }
    _mastered_lvl = max(
        [int(by_id_all[i].get("level", 1)) for i, c in ok_count.items() if c >= 3 and i in by_id_all] or [0]
    )
    if _mastered_lvl + 1 > lvl_max:
        lvl_max = _mastered_lvl + 1
    # ── Perceived effort is data too ─────────────────────────────────────────────
    # The UI records easy/right/much in a separate field; numeric RPEs in the note stay compatible, and the
    # verbal answer is not converted into an invented numeric measurement. The same challenge-point rule as
    # for successes applies: the task must be slightly harder than what is mastered, not at the edge of failure.
    #   two times in a row much (or RPE >= 8) -> ceiling down
    #   two times in a row easy (or RPE <= 3) -> ceiling up
    # This is a coaching heuristic, not a measurement (evidence level B); the reason is written in the output
    # so that it is visible and can be contested.
    _efforts = []
    for _s in _log()[-2:]:
        effort = _s.get("effort")
        if effort in ("easy", "right", "much"):
            _efforts.append(effort)
            continue
        _m = re.search(r"RPE\s+(\d+)\s*/\s*10", str(_s.get("note") or ""))
        if _m:
            score = int(_m.group(1))
            _efforts.append("much" if score >= 8 else "easy" if score <= 3 else "right")
    if len(_efforts) == 2 and all(v == "much" for v in _efforts) and lvl_max > lvl_min:
        lvl_max -= 1
        general_max = max(lvl_min, general_max - 1)
        notes.append("two sessions in a row felt too hard — stepping back so you are not training at the limit")
    elif len(_efforts) == 2 and all(v == "easy" for v in _efforts):
        lvl_max += 1
        general_max += 1
        notes.append("two sessions in a row felt easy — opening up harder work")

    # ── Feeling and the desired difficulty for today ─────────────────────────────
    # The survey asks about stable things (age, coach, level), while the state changes daily (sleep, soreness),
    # so it is asked before building and takes effect immediately.
    # The wish is not followed blindly: 'I want hard' is respected, but after 'tired' or two sessions that were
    # too hard a harder session is not given, and the system says so instead of quietly doing otherwise.
    _hard_blocked = (feel in ("tired", "sore")) or (len(_efforts) == 2 and all(v == "much" for v in _efforts))
    if feel == "sore":
        lvl_max = lvl_min
        general_max = lvl_min
        notes.append("sore from last time — easy steps only today")
    elif feel == "tired":
        lvl_max = max(lvl_min, lvl_max - 1)
        general_max = max(lvl_min, general_max - 1)
        notes.append("tired today — taking one step easier")
    if want == "easy":
        lvl_max = lvl_min
        general_max = lvl_min
        notes.append("you asked for an easy session")
    elif want == "hard":
        if _hard_blocked:
            notes.append(
                "you asked for a hard session, but today's state or two hard "
                "sessions in a row do not allow it — harder work comes once "
                "you have recovered"
            )
        else:
            lvl_max += 1
            general_max += 1
            notes.append("you asked for a hard session")

    eligible_ids = {
        d["id"]
        for d in drills_kb
        if int(d.get("level", 1)) <= lvl_max
        and (int(d.get("level", 1)) <= general_max or d["id"] in progression_ids)
        and d.get("kind") != "do_not_recommend"
        and not d.get("do_not_recommend")
    }
    if any(d["id"] in eligible_ids and int(d.get("level", 1)) > general_max for d in drills_kb):
        notes.append(
            "three self-reported successful attempts — the linked "
            "progression step is available; this is not a coach assessment"
        )
    # Filter before pool selection: an unsuitable drill must not displace an available
    # drill and later disappear from the final plan without a replacement.
    drills_kb = [d for d in drills_kb if d["id"] in eligible_ids]

    # ── How to treat an error, not just how to name it ───────────────────────────
    # kb/causes.yaml holds causes for each error, and each cause has fix_targets: targets whose work removes
    # it, each with a source and an evidence level. Taking only the target itself into the pool left these
    # links unused: 'fall' has 3 drills of levels [1,2], so after 30 successful sessions the step could not
    # rise, while 'landing_stability', which the base names as the remedy for falling, has 11 drills up to
    # level 3. Nothing is invented: everything added is already written, with a source and evidence level.
    _fix: list[str] = []
    for _c in (causes.get(focus) or {}).get("causes") or []:
        for _ft in _c.get("fix_targets") or []:
            if _ft not in goals and _ft not in extra_goals and _ft not in _fix:
                _fix.append(_ft)
    # Related drills are mixed in only when the target's own are lacking: always adding fix_targets made the
    # pools of different errors too similar (7 different sessions out of 8 instead of 8). A session must match
    # exactly the error that was measured.
    pool_goals = list(dict.fromkeys(list(goals) + extra_goals))
    pool = pick_drills(pool_goals, drills_kb, k=10, level_min=lvl_min, level_max=lvl_max)

    # ── A failure must influence the choice, not only the replacement ────────────
    # Measured (tools/test_fail_stepback.py): after 2 failures and after 2 successes the plan was identical,
    # because the 'failure -> step back' rule (below, fail_run>=2) only worked on drills already in today's
    # pool, while the freshness rule removes exactly the drills that just gave data. So the supporting drill
    # of the failed ones is added to the pool explicitly and goes first: the person gets a simpler rung, not
    # the same loop.
    _failed2 = {i for i, c in fail_run.items() if c >= 2}
    if _failed2:
        _lead_in = [
            x
            for x in drills_kb
            if x.get("progression_id") in _failed2
            and not x.get("do_not_recommend")
            and x["id"] not in {d["id"] for d in pool}
        ]
        if _lead_in:
            pool = _lead_in + pool
            notes.append(
                "after two unsuccessful performances of a drill in a row, "
                "today starts with its lead-in, one step easier"
            )
    # Eight is the minimum pool size from which at least a week without repeats in the main block comes out
    # (late_check_out has exactly 6 drills, which gave only 4 different days in the 14-day plan). The
    # difference between targets holds because a target's own drills always stand first in the pool, and
    # related ones only supplement the tail.
    _NEED = 8
    if _fix and len(pool) < _NEED:
        _wide = pick_drills(pool_goals + _fix, drills_kb, k=10, level_min=lvl_min, level_max=lvl_max)
        _have = {d["id"] for d in pool}
        pool = pool + [d for d in _wide if d["id"] not in _have]
        _related_labels = ", ".join(goal_label(code, lang) for code in _fix[:3])
        notes.append("the session includes drills for related goals: " + _related_labels)
    while not pool and lvl_min > 1:
        lvl_min -= 1
        pool = pick_drills(pool_goals, drills_kb, k=10, level_min=lvl_min, level_max=lvl_min + 1)
        notes.append(f"no drills for this goal at your level — taking easier ones (from level {lvl_min})")
    if not pool:  # target without any coverage
        pool = pick_drills(["basics_rotation"], drills_kb, k=6, level_min=1, level_max=lvl_max)
        notes.append("no drills for this goal in the base yet — giving rotation basics")
    # Order: the longest unused drill first, so the day does not repeat yesterday's even when there are few
    # drills for the target; then a drill with a demo.
    used = _last_used()

    # Equivalent drills must rotate over weeks. Measured: 16 of 51 drills were never shown, even with history,
    # because pick_drills optimizes target coverage and stops as soon as every target is closed: for a target
    # with 15 drills the person receives the same 3-4. The remaining suitable drills are therefore added to
    # the tail of the pool with a lower rank: the day still builds around coverage, and when the main ones
    # were recently used, equivalents come into rotation. Order:
    #   (1) recency: the longest unused first;
    #   (2) coverage rank: the day's spine ahead of the spares;
    #   (3) demo availability: the person must see how it is done.
    _rank = {d["id"]: i for i, d in enumerate(pool)}
    _have = set(_rank)
    _gset = set(pool_goals)
    for d in drills_kb:
        if d["id"] in _have or d.get("kind") == "do_not_recommend":
            continue
        if not (set(d.get("targets") or []) & _gset):
            continue
        if not (lvl_min <= int(d.get("level", 1)) <= lvl_max):
            continue
        _rank[d["id"]] = 100  # spares: after the day's spine
        pool.append(d)
    # Preference goes to drills with a ready 3D demo (original lessons are never shown). The rank is unique
    # per drill, so the demo key applies within the spine of the day, and spares come after it.
    _demo = _demo_ids()
    pool.sort(
        key=lambda d: (
            used.get(d["id"], -1),
            0 if _rank[d["id"]] < 100 else 1,
            0 if d["id"] in _demo else 1,
            _rank[d["id"]],
        )
    )

    # Progression by mastery. Repetition is not a bug: learning movements requires repetitions, and changing
    # drills daily is methodically harmful. But a drill marked done 3 sessions in a row is changed to the next
    # rung (mastery gate, GymnasticBodies/LTAD). ok_count/fail_run are computed above because they are also
    # needed before pool selection.
    in_pool = {x["id"] for x in pool}
    upgraded, eased, stuck, topped = [], [], [], []
    outgrown: list[str] = []
    for i, d in enumerate(pool):
        # Follow the chain to the end, not one step per session. Measured over 40 sessions in a row: a
        # replacement placed in pool[i] after the loop passed that index was never checked for mastery, and
        # since pick_drills does not return hv_one_and_half on its own, it got stuck (shown 37 times of 40)
        # while the last rung (hv_double_two_foot) was never reached. The rung moves on as long as each next
        # one is mastered.
        cur, hops = d, 0
        while hops < 6:
            nxt = by_id_all.get(cur.get("progression_id") or "")
            if nxt is None or nxt["id"] not in eligible_ids or ok_count.get(cur["id"], 0) < 3:
                break
            if nxt["id"] in in_pool:
                break  # the next one is already in the day
            in_pool.discard(cur["id"])
            in_pool.add(nxt["id"])
            cur, hops = nxt, hops + 1
        if hops:
            pool[i] = cur
            upgraded.append((d["name"], cur["name"]))
            continue
        if ok_count.get(d["id"], 0) >= 3 and not d.get("progression_id"):
            # End of the chain: the drill is mastered and there is no harder one in the base. Silent repetition
            # reads as 'the system does not notice I have mastered this', so it is said directly: this is the
            # limit of the base, not the limit of the person.
            topped.append(d["name"])
        nxt = by_id_all.get(d.get("progression_id") or "")
        _mastered = nxt is not None and nxt["id"] in eligible_ids and ok_count.get(d["id"], 0) >= 3
        if _mastered:
            # The next rung already being in the day means this one is worked out: it is removed from the day,
            # since its work is done by the next one. Measured over 60 sessions with everything marked done,
            # keeping the mastered drill showed lib_half_rotation_turns 60 times of 60.
            outgrown.append(d["id"])
        elif fail_run.get(d["id"], 0) >= 2:
            # Too hard (challenge point): a drill that is not succeeding twice in a row means the level is too
            # high. level_min is not filled in the base (all 51 drills = 1), so 'easier' is taken by the only
            # real link, a step back along progression_id: the drill that leads to this one is its prerequisite.
            prev_any = [x for x in drills_kb if x.get("progression_id") == d["id"] and not x.get("do_not_recommend")]
            prev = [x for x in prev_any if x["id"] not in in_pool]
            if prev:
                pool[i] = prev[0]
                in_pool.add(prev[0]["id"])
                eased.append((d["name"], prev[0]["name"]))
            elif prev_any:
                # Measured (tools/test_fail_stepback.py): when the target is not excluded by the freshness rule,
                # this pass and the early pool injection (_failed2 above) both take the same prerequisite drill.
                # The injection already put it in pool/in_pool, so prev is empty here; without this branch the
                # system would wrongly say 'no prerequisite in the base' (stuck). The duplicate target in the
                # pool is removed silently: its work is done by the prerequisite drill added earlier.
                outgrown.append(d["id"])
            else:
                stuck.append(d["name"])
    if outgrown:
        pool = [d for d in pool if d["id"] not in outgrown]
        in_pool -= set(outgrown)
    # These three notes are assembled from drill names, which an exact-match dictionary cannot cover. They
    # appear only with history.
    for old_n, new_n in upgraded[:2]:
        notes.append(f"“{old_n}” worked 3 sessions in a row — moving up a step: “{new_n}”")
    for old_n, new_n in eased[:2]:
        notes.append(f"“{old_n}” did not work twice in a row — taking the easier lead-in: “{new_n}”")
    for n in topped[:2]:
        notes.append(
            f"“{n}” is the last step in the base for this goal — you have "
            f"outgrown it, and there is nothing harder here yet. Keep it as "
            f"maintenance and ask a coach for the next step"
        )
    if stuck:
        # There is no prerequisite in the base: say so instead of staying silent or inventing a drill.
        notes.append(
            f"not working twice in a row ({', '.join(stuck[:2])}), and the "
            f"base has no easier lead-in — halve the dosage and show the "
            f"attempt to a coach: video alone cannot diagnose further"
        )

    # Escalation by analysis history, not by one session. If the same error persists over four analyses in a
    # row, another drill is the wrong answer: off-ice drills do not transfer to the ice automatically, and the
    # cause is probably what a phone video does not show (the edge, pressure on the blade, entry into the arc).
    _stuck_hist = stuck_errors()
    if _stuck_hist:
        notes.append(
            f"this error has persisted for 4 analyses in a row "
            f"({', '.join(goal_label(c, lang) for c in _stuck_hist[:2])}) — "
            f"working alone has not moved it. A coach's eye is needed next: "
            f"off-ice drills do not carry over to the ice automatically, and the cause "
            f"may be in something a phone video does not show"
        )

    steps = assemble_steps(pool, eligible_ids, focus, causes, by_id, notes, freq, age, pain, fit)

    day_n = len(_log()) + 1
    dur = "30-40" if freq <= 1 else "20-30" if freq <= 2 else "15-25"
    # ── What the person wrote last time ──────────────────────────────────────────
    # Free text 'what was hard' is not parsed by rules: extracting decisions from it would mean inventing
    # them. It is returned in the next session as context, with a plain statement that it does not influence
    # the choice of drills.
    # A session closed with no drill marked leaves the journal with zero results, so the next session comes
    # out the same. That is correct (determinism), but the person must see why nothing moved and what marks
    # are needed for progress.
    _real = [s for s in _log() if not s.get("simulated")]
    if _real and not (_real[-1].get("blocks") or []):
        notes.append(
            "the previous session was closed without marking any "
            "drill — there is nothing to move the level with; mark "
            "got-it / not-yet on each drill and the next session "
            "will change"
        )

    _last_note = ""
    for _s in reversed(_log()):
        _n = str(_s.get("note") or "").strip()
        if _n and not _s.get("simulated"):
            _last_note = _n
            break

    return {
        "day": day_n,
        "focus": focus,
        "level_min": lvl_min,
        "last_note": _last_note,
        "last_note_role": (
            (
                "your own words after the previous session. They do NOT change "
                "the drill selection — that is driven by the got-it / not-yet "
                "marks and the difficulty score"
            )
            if _last_note
            else ""
        ),
        "focus_text": _focus_text(focus, causes, lang),
        # the focus name itself, for the 'Next step' card under the analysis; the 'typical cause' there would
        # read as a diagnosis of this jump, so it is labelled as reference.
        "focus_label": goal_label(focus, lang),
        "focus_goal": focus,  # id of the target for the session journal (progress by target)
        "focus_source": focus_source,
        "duration_min": dur,
        "blocks": steps,
        "personalisation": _sentences(notes, lang),
        "fitness_state": fitness_state,
        # Lines with substituted numbers are not covered by the dictionary: in kb/i18n_kb.json the translation
        # works only on a full match, and every level and frequency gives a new line.
        # Without a survey the line is honest about being assumed: the defaults lvl_min=1/freq=1 must not be
        # shown as a measured level and frequency (invariant 1).
        "based_on": (
            f"level {lvl_min + 1}, sessions per week: {['1-2', '3-4', '5-6', 'daily'][min(freq, 3)]}"
            if have_survey
            else "survey not filled in — level and frequency are assumed (most cautious); fill in “About you”"
        ),
        "history_note": _history_note(steps, recent, lang),
        "science": science_for(goals, fit),
    }
