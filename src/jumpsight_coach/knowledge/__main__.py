"""Command line: build the corpus or ask one question."""

import sys

import jumpsight_coach.knowledge as knowledge

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        knowledge.build()
    elif len(sys.argv) > 2 and sys.argv[1] == "ask":
        r = knowledge.ask(" ".join(sys.argv[2:]))
        print(r["answer"][:600])
        for s in r["sources"][:4]:
            print(f"  [{s['score']}] {s['source']} {s['url'][:60]}")
    else:
        print(knowledge.__doc__)
