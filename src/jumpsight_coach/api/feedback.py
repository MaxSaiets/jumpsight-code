"""Verdict feedback: the person's confirmation or correction of a verdict."""

from __future__ import annotations

import json
import time

from fastapi import APIRouter
from pydantic import BaseModel

from jumpsight_core.paths import STATE_DIR

from .. import accounts as _acc

router = APIRouter()


class VerdictFeedbackIn(BaseModel):
    stem: str
    # None is allowed only for source="pre_reveal": the server then computes agreement by comparing
    # the person's estimate with what the system has already written to the journal.
    correct: bool | None = None
    jump: str | None = None  # correct name, if the system erred
    turns: int | None = None  # correct revolution count
    note: str | None = None
    # Where the mark comes from. "pre_reveal": the person named the jump and the revolutions before
    # the numbers were shown, which avoids anchoring on an answer already seen. For training the
    # classifier the reliable part is the name (the athlete knows which element they performed);
    # the count is a feeling, and a discrepancy with the measurement is a training event, not a
    # labeling error.
    source: str | None = None


@router.post("/verdict_feedback")
def verdict_feedback(inp: VerdictFeedbackIn) -> dict:
    """Confirmation or correction of the verdict by a person.

    The model lacks labelled data from the target domain, phone video. Headline labels from YouTube are not
    suitable (measured: the most frequent error, flip->lutz, is exactly the one the authors also confuse), so
    the wild corpus is not used for training. The answer of a person who saw their own jump is a verified
    label: each confirmation or correction here becomes a training sample in the domain where the product works.

    We write it next to the journal, in a separate file: the journal holds system measurements, while this is human testimony, and the two must not be mixed.
    """
    from ..userctx import user_path as _up

    # An analysis example, i.e. a stranger's jump: a visitor's answer about it is not
    # human testimony about THEIR OWN jump and must not enter the labels.
    try:
        _demo = json.loads((STATE_DIR / "demo_stems.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _demo = []
    if inp.stem in _demo:
        return {"ok": False, "error": "demo_sample"}
    fb_path = _up(STATE_DIR / "verdict_feedback.json")
    JUMPS = {"axel", "salchow", "toe_loop", "loop", "flip", "lutz"}
    jump = (inp.jump or "").strip().lower().replace(" ", "_") or None
    if jump and jump not in JUMPS:
        return {"ok": False, "error": f"unknown jump: {inp.jump}"}
    # what the system said is taken from the journal, to have a "measurement/truth" pair
    said = None
    from ..jobs import history as _hist

    # THE COACH ON A STUDENT'S ANALYSIS: "what the system said" comes from the student's journal,
    # and the label is marked source="coach" (expert).
    from ..userctx import current_uid as _cu

    _student = _acc.coach_of_stem_owner(inp.stem, _cu())
    if _student:
        try:
            _rows_src = json.loads((_acc.USERS / _student / "history.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _rows_src = []
    else:
        _rows_src = _hist()
    for h in _rows_src:
        # Labels may be keyed by job id as well as by stem, so the journal is matched on both keys
        # to give every label a "measurement/truth" pair.
        if h.get("stem") == inp.stem or (h.get("job") and h.get("job") == inp.stem):
            said = {
                "jump": h.get("jump"),
                "count_named": h.get("count_named"),
                "revolutions": h.get("revolutions"),
                # estimate or measurement, so that the pair "said/true" can be
                # counted separately for each source of the count
                "count_estimated": bool(h.get("count_estimated")),
                "count_estimate_kind": h.get("count_estimate_kind"),
                "confidence": h.get("confidence"),
            }
            break
    correct = inp.correct
    if correct is None:
        # Agreement is computed by the server (one source of truth): the name matched and, if a count
        # was named, the count matched too. With nothing to compare against (the analysis is not yet
        # in the journal) it stays None.
        if said is None:
            correct = None
        else:
            said_jump = str(said.get("jump") or "").strip().lower().replace(" ", "_")
            ok_jump = jump is not None and said_jump == jump
            ok_turns = True
            if inp.turns is not None:
                _named = {"single": 1, "double": 2, "triple": 3, "quad": 4}
                said_turns = _named.get(str(said.get("count_named") or "").strip().lower())
                ok_turns = (said_turns is None) or (said_turns == inp.turns)
            correct = bool(ok_jump and ok_turns)
    from ..statefile import update_json

    def _mut(cur):
        rows = [r for r in (cur or []) if r.get("stem") != inp.stem]  # one per analysis
        rows.append(
            {
                "ts": time.time(),
                "stem": inp.stem,
                "correct": correct,
                "jump": jump,
                "turns": inp.turns,
                "note": inp.note,
                "source": ("coach" if _student else (inp.source or "post_reveal")),
                # owner of the video (internal uid): the closed export test
                # groups by it, not by the coach
                "video_owner": _student,
                "system_said": said,
            }
        )
        return rows

    # preserve_broken: the broken page is renamed beside it, not overwritten
    rows = update_json(fb_path, _mut, [], preserve_broken=True)
    return {"ok": True, "saved": len(rows)}


@router.get("/verdict_feedback")
def verdict_feedback_list() -> list:
    from ..userctx import user_path as _up

    fb_path = _up(STATE_DIR / "verdict_feedback.json")
    if not fb_path.exists():
        return []
    try:
        return json.loads(fb_path.read_text(encoding="utf-8"))
    except Exception:
        return []
