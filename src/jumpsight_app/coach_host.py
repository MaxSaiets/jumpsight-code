"""Registers this application as the host of the coach service.

Implementations look up module attributes at call time, so tests that patch
`webapp` or `avatar_generator` are seen by the coach.
"""

from __future__ import annotations

from jumpsight_coach import integration


def _find_job(job_id: str) -> dict | None:
    from jumpsight_app import webapp

    return webapp._job(job_id)


def _running_jobs():
    from jumpsight_app import webapp

    return list(webapp.JOBS.items())


def _avatar_cache_is_current(avatar, result, video) -> bool:
    from jumpsight_app import avatar_generator

    return avatar_generator._cache_is_current(avatar, result, video)


def _avatar_generate(stem: str) -> str:
    from jumpsight_app import avatar_generator

    return avatar_generator.generate(stem)


def install() -> None:
    from jumpsight_app import avatar_generator

    integration.install(
        find_job=_find_job,
        running_jobs=_running_jobs,
        avatar_cache_is_current=_avatar_cache_is_current,
        avatar_generate=_avatar_generate,
        avatar_generator_version=avatar_generator.GENERATOR_VERSION,
    )
