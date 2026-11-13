"""A missing engine must fail the job loudly, not fall back to anything else."""

from pathlib import Path

from jumpsight_app import engine_bridge, webapp


def test_job_fails_with_a_clear_error_when_the_engine_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(webapp, "WORK", tmp_path)
    monkeypatch.setattr(webapp, "JOBS", {"j1": {"state": "queued", "name": "clip.mp4", "started": 0.0}})
    monkeypatch.setattr(engine_bridge, "available", lambda: False)

    webapp._prescan_job_impl("j1", Path("clip.mp4"))

    job = webapp.JOBS["j1"]
    assert job["state"] == "error"
    assert job["error_code"] == "ENGINE_UNAVAILABLE"
    assert "engine" in job["error"]
    assert (tmp_path / "j1" / "job.json").is_file()


def test_public_edition_reports_why_the_engine_is_missing():
    assert engine_bridge.available() is False
    assert "private" in engine_bridge.unavailable_reason()
