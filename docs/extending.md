# Extending the code

The packages depend on each other only in one direction, and `tests/test_architecture.py` keeps it that way:

```
jumpsight_core  <-  jumpsight_coach  <-  jumpsight_app
```

The private analysis engine is reached only through `jumpsight_app/engine_bridge/`.

## Ground rules

1. A number in the output is measured, or it is absent with a reason. No fallback may invent a value.
2. `ruff check .`, `ruff format --check .` and `pytest` pass before a commit.

## Where things go

| Change | Where |
|---|---|
| A new type of chat answer | a `_..._lookup` function in `src/jumpsight_coach/knowledge/lookups_*.py`, registered in the order list in `knowledge/answer.py`. It must cite a source. |
| A new drill or cause | `src/jumpsight_coach/kb/*.yaml`, then `python -m jumpsight_coach.kb_lint`. |
| Hosting the coach in another app | implement the ports in `src/jumpsight_coach/integration.py`; `src/jumpsight_app/coach_host.py` is the reference. |
| A new upload or job endpoint | `src/jumpsight_app/webapp/` (`uploads.py`, `jobs.py`, `status.py`), with an owner check. |
| A new client screen | a `web/app-<screen>.js` file that reads and registers on `window.JS.app`, added to `web/index.html` and `web/sw.js`. |
