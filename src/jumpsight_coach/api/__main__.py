"""Run the coach API on its own: python -m jumpsight_coach.api."""

import uvicorn

from . import app

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8100)
