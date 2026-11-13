# jumpsight_coach: coaching service

Chat with sources, daily session and plan, history and progress, skills, fitness, accounts with coach and student links, sign-in. Depends only on `jumpsight_core`: it runs on its own, and a host application connects through `integration.py`.

## Use

```
uvicorn jumpsight_coach.api:app --port 8001          # standalone
python -m jumpsight_coach.knowledge build            # chat corpus and embeddings (once)
```

When mounted by `jumpsight_app`, the app calls `jumpsight_app.coach_host.install()` to provide live jobs and the 3D-avatar generator. Without a host those ports return no jobs and no avatar.

## Layout

| Area | Module | What it does |
|---|---|---|
| HTTP API | `api/` | One router per area: `chat`, `plans`, `history`, `profile`, `team`, `auth`, `media`, `mascot`, `recommendations`, `feedback`; `bootstrap` holds startup warm-up |
| Chat | `knowledge/` | `corpus` gathers corpus rows, `index` builds and loads embeddings (`build`), `lexical` is the BM25 fallback, `lookups_*` answer known question types without a model, `answer` runs retrieval and the grounded paraphrase, `validate` checks numbers and words against the sources |
| Embeddings | `embed.py` | Second index over drills and causes for exercise selection; model `intfloat/multilingual-e5-small`, 384 dimensions |
| LLM | `llm.py`, `prompts.py` | OpenAI client, versioned prompts; never required for a correct answer |
| Recommendations | `pipelines.py`, `core.py` | Rule, case and semantic pipelines and the 14-day programme |
| Session | `session/` | `focus`, `rules`, `blocks`, `builder`, `planner`, `outcomes` |
| Users | `accounts.py`, `sessions.py`, `auth_store.py`, `userctx.py`, `statefile.py` | Accounts, session tokens, credential store, per-request user, atomic JSON state |
| Knowledge base | `kb/` | English YAML with source attribution; checked by `kb_lint.py` |
| Lesson-library ingest | `ingest/` | Offline tools: motion description, cards, context, steps, transcript chunks, drill mining |

## Extension

- A new structured chat answer: add a `_..._lookup` function in the matching `knowledge/lookups_*.py` and register it in the order list in `knowledge/answer.py`. Lookups run before retrieval and must cite a source.
- A new drill: add an entry to `kb/drills.yaml` with `source` and `url`, then run `python -m jumpsight_coach.kb_lint`.
