"""Knowledge-base linter: errors and warnings.

    python -m jumpsight_coach.kb_lint

Errors: broken progression/regression/prerequisite references, power drills
without rest, program ids without drills. Warnings: more than 2-3 cues per
drill (Winkelman), a missing success gate, a gate without a number.
"""

from __future__ import annotations

import re
import sys

import yaml

from jumpsight_core.paths import KB_DIR as KB


def lint() -> tuple[list[str], list[str]]:
    errors, warns = [], []
    drills = yaml.safe_load((KB / "drills.yaml").read_text(encoding="utf-8"))
    ids = {d["id"] for d in drills}
    for d in drills:
        for fld in ("progression_id", "regression_id"):
            ref = d.get(fld)
            if ref and ref not in ids:
                errors.append(f"{d['id']}: {fld} -> {ref} does not exist")
        for pid in d.get("prerequisites", []):
            if pid not in ids:
                errors.append(f"{d['id']}: prerequisite -> {pid} does not exist")
            elif pid == d["id"]:
                errors.append(f"{d['id']}: prerequisite is the drill itself")
        if d.get("block") == "power":
            rest = str(d.get("dosage", "")) + str(d.get("rest_s", ""))
            if not re.search(r"recovery|rest|60|90|120", rest):
                errors.append(f"{d['id']}: power drill without rest")
        if len(d.get("cues", [])) > 3:
            warns.append(f"{d['id']}: {len(d['cues'])} cues (norm <=2-3, Winkelman)")
        if d.get("kind") not in ("do_not_recommend",) and not d.get("success") and not d.get("exit_criteria"):
            warns.append(f"{d['id']}: no success gate")
    progs = yaml.safe_load((KB / "programs.yaml").read_text(encoding="utf-8"))
    for pr in progs:
        for week in pr["weeks"]:
            for day in week["days"]:
                if isinstance(day, list):
                    for did in day:
                        if did not in ids:
                            errors.append(f"{pr['id']}: drill {did} does not exist")
        for g in ("gate_in", "gate_out"):
            if pr.get(g) and not re.search(r"\d", pr[g]):
                warns.append(f'{pr["id"]}.{g}: gate without a number (should be countable: "3 clean in a row")')
    return errors, warns


def main() -> None:
    errors, warns = lint()
    for e in errors:
        print(f"  ERROR {e}")
    for w in warns[:15]:
        print(f"  ~ {w}")
    if len(warns) > 15:
        print(f"  ... and {len(warns) - 15} more warnings")
    print(f"\nerrors: {len(errors)}, warnings: {len(warns)}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
