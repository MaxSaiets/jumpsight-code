"""Local server for the UI only.

`jumpsight_app.web:app` builds the application on import and warms the analysis
models unless told otherwise (tens of seconds, a risk of stalls on a laptop).
Here `JS_API_ONLY=1`, so only the API and the static client come up: every
screen, text, state and transition can be exercised without a cloud or GPU.

    python tools/serve_ui.py [--port 8010]

Video analysis does not run here (no worker); that is deliberate. To run the
full application use `python -m uvicorn jumpsight_app.web:app` instead.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("JS_API_ONLY", "1")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8010)
    a = ap.parse_args()
    import uvicorn

    os.chdir(ROOT)
    uvicorn.run("jumpsight_app.web:app", host=a.host, port=a.port, log_level="warning")
