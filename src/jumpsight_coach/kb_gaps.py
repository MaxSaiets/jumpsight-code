"""Where the knowledge base is thin: goals without drills at level 3+.

The tool never writes drills "from general knowledge": a drill nobody filmed
or checked looks as convincing as a real one, and a coach would have to sign
it. It only counts the goal x level matrix of kb/drills.yaml and names the
gaps, which is an honest "this needs own filming" instead of silence.

    python -m jumpsight_coach.kb_gaps
"""

from __future__ import annotations

from collections import defaultdict

TOP_LEVEL = 3  # below this level a goal does not lead the person further


def gaps() -> dict:
    from .core import load_kb

    drills, _ = load_kb()
    ok = [d for d in drills if d.get("kind") != "do_not_recommend"]
    by: dict[str, list[int]] = defaultdict(list)
    for d in ok:
        for g in d.get("targets") or []:
            by[g].append(int(d.get("level", 1)))

    blocking, thin = [], []
    for g, lv in sorted(by.items(), key=lambda kv: len(kv[1])):
        top = max(lv)
        row = {"goal": g, "drills": len(lv), "levels": sorted(set(lv)), "top_level": top}
        if top < TOP_LEVEL:
            blocking.append(row)
        elif len(lv) < 6:
            thin.append(row)
    return {
        "blocking": blocking,
        "thin": thin,
        "not_done": (
            "drills are NOT generated from text: a drill nobody "
            "filmed cannot be verified, and it is the coach who "
            "signs it"
        ),
    }


def main() -> int:
    g = gaps()
    print("GAPS THAT BLOCK PROGRESS (no level 3+ drill):\n")
    for r in g["blocking"]:
        print(f"  {r['goal']:20s} {r['drills']:2d} drills, levels {r['levels']}")
    if g["thin"]:
        print("\nTHIN GOALS (level 3+ exists, but few drills):")
        for r in g["thin"]:
            print(f"  {r['goal']:20s} {r['drills']:2d} drills, levels {r['levels']}")
    print(f"\nnot done on purpose: {g['not_done']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
