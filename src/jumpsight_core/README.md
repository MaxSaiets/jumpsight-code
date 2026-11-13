# jumpsight_core: shared contracts

The only package every other package may import. It has no dependency of its own beyond the standard library.

| Module | Purpose |
|---|---|
| `paths.py` | Every filesystem location, each overridable by a `JS_*` variable. Mutable state lives under `JS_VAR_DIR`, never in the source tree. |
| `evidence.py` | Normalises stored landing-check features to the current evidence contract, for results written by older engine versions. |
| `job_queue.py` | Bounded thread-pool queue so the number of requests does not multiply heavy models in memory. |
| `facade.py` | Lets a package that was split into submodules keep one public namespace, including assignments made by tests. |
