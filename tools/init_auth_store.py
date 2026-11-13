"""Explicit creation of only the auth tables in a prepared DB."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jumpsight_coach.auth_store import DatabaseAuthStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initialize", action="store_true", required=True)
    parser.parse_args()
    url = os.environ.get("JS_AUTH_DATABASE_URL")
    if not url:
        raise SystemExit("JS_AUTH_DATABASE_URL required; do not pass the URL on the command line")
    db = DatabaseAuthStore(url)
    try:
        db.initialize()
    except Exception:
        raise SystemExit("Could not create the auth schema; check database access") from None
    finally:
        db.engine.dispose()
    print("Auth schema initialized; existing sessions were not migrated")


if __name__ == "__main__":
    main()
