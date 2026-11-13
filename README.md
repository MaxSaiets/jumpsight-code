# JumpSight

> **Public edition.** This repository contains the real source of the JumpSight
> web application, the coaching service and the mobile client, with their tests
> and CI. The analysis engine (finding the jump, measuring take-off, landing and
> revolutions, naming the jump), the 3D-character pipeline, trained models and
> datasets are private. Reviewers can get read access to the full source on
> request — see [Access to the full source](#access-to-the-full-source).

JumpSight analyses figure-skating jumps from a single phone video. For each
jump it reports the jump type, the number of revolutions the way judges count
them, take-off and landing times, air time, rotation speed and a set of landing
checks — each with a confidence level and the reason behind it.

Live: **https://jumpsight.pp.ua** (English and Ukrainian).

## What it looks like

### Jump analysis

![Jump analysis: what the system measures on the left, the original video on the right](docs/media/jump-analysis.gif)

Left: what the engine measures. Right: the original frames. Played at half
speed. From the run on this clip (60 fps): take-off at frame 79, landing at
frame 117, 0.633 s in the air, 2.2 revolutions in flight.
Full quality: [jump-analysis.mp4](docs/media/jump-analysis.mp4).

### Exercise demonstrations with a 3D character

![Two 3D characters performing exercises](docs/media/character.gif)

A coach films an exercise on a phone; the app teaches it with a 3D character
that performs the same movement, so neither the coach's footage nor voice is
shown. A clip is published only if it passes automatic accuracy gates.
Full quality: [character-a.mp4](docs/media/character-a.mp4), [character-b.mp4](docs/media/character-b.mp4).

## What is in this repository

| Part | What it does | Where |
|---|---|---|
| Web application | uploads (whole, chunked, live parts while filming), job queue with honest states, status and server-sent events, owner checks on every job and media URL, security headers | `src/jumpsight_app` |
| Coaching service | chat that answers from a knowledge base with sources (rules first, then retrieval, a language model allowed only to rephrase the sources), daily session and 14-day plan from measured faults, fitness tests, history, coach and student accounts, Google sign-in | `src/jumpsight_coach` |
| Shared core | paths, evidence format, job queue | `src/jumpsight_core` |
| Mobile client | plain JavaScript PWA, one file per screen, English and Ukrainian | `web/` |
| Tests | 348 Python tests + client unit test; package boundaries enforced by `tests/test_architecture.py` | `tests/` |

| Part | Files | Lines |
|---|---|---|
| Web application | 20 | 2,523 |
| Coaching service | 59 | 11,735 |
| Shared core | 5 | 282 |
| Mobile client | 29 | 14,446 |
| Tests | 49 | 3,944 |

How it fits together: [docs/how-it-works.md](docs/how-it-works.md).
Where each kind of change goes: [docs/extending.md](docs/extending.md).

## What is private

The engine is reached only through `src/jumpsight_app/engine_bridge/`, which
in this edition is an **interface without an implementation**: `available()`
is False, and an analysis job ends with the error `ENGINE_UNAVAILABLE` —
the loud failure the app is built to show, never a made-up result. The same
holds for the live analysis worker and the 3D avatar of the user's own jump.

Not included: the analysis engine, the jump-name model, the 3D-character
pipeline, trained weights, datasets, training recipes, deployment
configuration.

## Principles

- **No invented numbers.** Every value is measured, explicitly marked as
  inferred, or absent with a reason. Nothing fills a gap with a
  plausible-looking number.
- **Confidence next to every conclusion.** Lutz and flip differ only by the
  blade edge, which one camera cannot see; they are shown as a pair and never
  with high confidence.
- **The coach answers from sources.** If a statement in a generated answer is
  not found in the retrieved sources, the answer is replaced by the source
  excerpt itself.
- **Measured, not assumed.** Decisions were checked on data with known truth;
  ideas that did not improve the product were dropped.

## Measured results (full system)

| What | Result | Data |
|---|---|---|
| Revolutions in flight, flight window given | 214 of 221 measured, median error 0.029 rev, 212 of 214 within 0.25 rev | motion capture, 4 skaters, 30 fps |
| Jump name, strict | 33 of 54 | web and broadcast clips |
| Jump name, answers shown to the user | 32 of 37 correct, an answer on 37 of 54 | web and broadcast clips |
| Revolution count, end to end | 22 of 31 correct, a count on 31 of 54 | web and broadcast clips |

There is no labelled set of phone videos yet, so accuracy on the target input
is not known; landing checks have no measured sensitivity yet.

## Running it

Python 3.11.

```
pip install -e ".[app,coach,dev]"
ruff check .
pytest -m "not requires_models and not requires_media"
uvicorn jumpsight_app.web:app --port 8000
```

The app, the client, accounts and the coach run; an uploaded video ends with
`ENGINE_UNAVAILABLE` because the engine is not part of this edition. The chat
needs `OPENAI_API_KEY` for generated answers; without it, rule-based answers
and source excerpts still work.

## Access to the full source

The full source (engine and character pipeline included, about 37,000 lines
and 1,000+ tests) is in a private repository. If you are reviewing my work,
contact me via [maxsaiets.com](https://maxsaiets.com) with your GitHub
username and I will grant read access.

## Licence

All rights reserved. See [LICENSE](LICENSE).
