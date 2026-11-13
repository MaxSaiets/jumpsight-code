# jumpsight_app: web application

Composes the analysis engine (private, behind `engine_bridge/`) and the coach into one FastAPI application. It is the only package allowed to depend on all the others (enforced by `tests/test_architecture.py`).

## Use

```
uvicorn jumpsight_app.web:app --host 127.0.0.1 --port 8000
```

## Layout

| Area | Module | What it does |
|---|---|---|
| ASGI entry | `web.py` | Static client, security headers, health and warm state, mounts the coach under `/coach` |
| Coach host | `coach_host.py` | Registers this app's jobs and avatar generator as implementations of `jumpsight_coach.integration` |
| Upload, jobs, status | `webapp/` | `factory` builds the app; `uploads`, `jobs`, `dispatch`, `pipeline`, `status`, `summary`, `preview`, `early`, `live_local` |
| Engine bridge | `engine_bridge/` | Interface to the private engine. In the public edition `available()` is False and jobs end with `ENGINE_UNAVAILABLE` |
| Live recording | `live_queue.py`, `upload_parts.py`, `webapp/live_local.py` | Resumable chunked upload while the user films (the live analysis worker is private) |
| 3D view | `avatar_generator.py` | Interface only: the 3D skeleton of the user's jump is built from the private engine's pose data |

## Extension

- Hosting the coach elsewhere: implement the ports in `jumpsight_coach/integration.py` the way `coach_host.py` does.
