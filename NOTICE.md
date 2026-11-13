# Third-party notices

This project is proprietary (see [LICENSE](LICENSE)). It uses the following third-party material.

## Data

**ISU protocol data.** `src/jumpsight_coach/kb/isu_jump_reference.json` is derived from ISU competition protocols published as structured data by BuzzFeed News (repositories "figure-skating-scores" and "2018-02-figure-skating-analysis"), 17 international competitions, October 2016 to December 2017, licensed CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). The file states this in its `attribution` field. The values were aggregated and changed (base values, call rates, median grade of execution per jump).

**Wikipedia.** The chat corpus built by `python -m jumpsight_coach.knowledge build` contains chunks of Wikipedia articles, CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/). Each stored chunk keeps its article title and URL as its source. The built corpus is not committed.

## Models and software used at runtime

| Component | Licence |
|---|---|
| PyTorch | BSD-3-Clause |
| OpenCV | Apache-2.0 |
| NumPy, SciPy | BSD-3-Clause |
| FastAPI | MIT |
| Uvicorn | BSD-3-Clause |
| SQLAlchemy | MIT |
| psycopg | LGPL-3.0 (unmodified library) |
| sentence-transformers | Apache-2.0 |
| intfloat/multilingual-e5-small | MIT |
| MediaPipe (offline lesson description) | Apache-2.0 |
| Matplotlib | Matplotlib licence (PSF-based) |
| Pillow | HPND |
| Archivo, IBM Plex Mono (fonts, loaded by the client) | SIL Open Font License 1.1 |
| FFmpeg (called as an external program, not redistributed) | LGPL/GPL |

## Optional components with restrictive terms (offline character pipeline)

| Component | Terms |
|---|---|
| NLF body tracker weights | noncommercial research use |
| SMPL body model parameterisation | non-commercial restriction |
| Ultralytics YOLO11 | AGPL-3.0 |
| Blender | GPL (used as an external program) |
| Character "Snow" (if used) | CC BY 4.0, credit: "Snow Rig (CC) Blender Foundation | studio.blender.org" |
| OpenAI text-to-speech and chat API | OpenAI business terms; synthetic voice must be disclosed as AI-generated |
