"""Today's session: one day, step by step, taking past sessions into account.

A session is one focus with one set of drills, and the next one is built from what happened today
(a fixed 14-day program cannot be followed or checked).

What it does:
  - takes the goal from the last analysis (one error = one focus per day, guidance hypothesis);
  - looks at history: which program day has been completed, which drills were used last time (do not
    repeat the same ones three times in a row);
  - builds ONE 20-30 min session following NCCP anatomy:
    warm-up -> specific warm-up -> main -> volume -> cool-down;
  - each step has instructions, dosage, video and a success criterion that the user marks themselves;
  - at the end, a control attempt on video, which the system checks.
Progress is stored in the session journal (STATE_DIR/session_log.json): what was marked done and what did not
work. The next day takes this into account.

Modules: outcomes (journal), rules (prescription and labels), focus (focus selection), blocks (step assembly
and text), builder (build), planner (plan). This package re-exports every name that other modules and tests
use, and mirrors assignments on the package into the modules that read them.
"""

from __future__ import annotations

from jumpsight_core.facade import install_facade

from ..core import CODE_ALIASES, load_kb, pick_drills
from . import blocks, builder, focus, outcomes, planner, rules
from .blocks import (
    _focus_text,
    _history_note,
    _sentences,
    assemble_steps,
)
from .builder import (
    _demo_ids,
    _fmt_date,
    build,
    build_for_goal,
)
from .focus import (
    _SKILL_MIN_ATTEMPTS,
    _SUPPORT_FALLBACK,
    MIN_ANALYSES_FOR_FOCUS,
    _analyses_with_code,
    _confident_errors,
    _error_confidence,
    _goal_of,
    _goals_of,
    _measured_attempts,
    _pick_focus,
    guard_focus,
    stuck_errors,
    support_goals,
)
from .outcomes import (
    _SIM,
    LOG,
    _last_used,
    _log,
    _lp,
    _outcome_streaks,
    _recent_drill_ids,
    _save,
    complete,
    history,
)
from .planner import (
    plan,
)
from .rules import (
    _PRESC,
    GOAL_LABELS,
    focus_reason,
    goal_label,
    prescription,
    science_for,
)

install_facade(__name__, (outcomes, rules, focus, blocks, builder, planner))

__all__ = [
    "CODE_ALIASES",
    "_SKILL_MIN_ATTEMPTS",
    "load_kb",
    "pick_drills",
    "GOAL_LABELS",
    "LOG",
    "MIN_ANALYSES_FOR_FOCUS",
    "_PRESC",
    "_SIM",
    "_SUPPORT_FALLBACK",
    "_analyses_with_code",
    "_confident_errors",
    "_demo_ids",
    "_error_confidence",
    "_fmt_date",
    "_focus_text",
    "_goal_of",
    "_goals_of",
    "_history_note",
    "_last_used",
    "_log",
    "_lp",
    "_measured_attempts",
    "_outcome_streaks",
    "_pick_focus",
    "_recent_drill_ids",
    "_save",
    "_sentences",
    "assemble_steps",
    "build",
    "build_for_goal",
    "complete",
    "focus_reason",
    "goal_label",
    "guard_focus",
    "history",
    "plan",
    "prescription",
    "science_for",
    "stuck_errors",
    "support_goals",
]
