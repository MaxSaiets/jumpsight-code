"""Bounded local queue: the number of requests does not multiply the heavy models."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Lock


class QueueFull(RuntimeError):
    """The task was not accepted; the client may retry it later."""


class AnalysisQueue:
    """Single-process queue; the cloud dispatcher has its own scaling.

    The record is created before submit, so a repeat of one job_id does not start
    a second processing. The limit covers both active and waiting tasks.
    """

    def __init__(self, workers: int = 1, pending: int = 8):
        self.workers = max(1, workers)
        self.capacity = self.workers + max(0, pending)
        self._lock = Lock()
        self._jobs: dict[str, str] = {}
        self._cancelled: set[str] = set()
        self._executor = ThreadPoolExecutor(self.workers, thread_name_prefix="js-analysis")

    def submit(self, job_id: str, work: Callable, *args) -> bool:
        with self._lock:
            if job_id in self._jobs:
                return False
            if len(self._jobs) >= self.capacity:
                raise QueueFull("The analysis queue is full. Upload again in a little while.")
            self._jobs[job_id] = "queued"

        def run():
            with self._lock:
                if job_id in self._cancelled:
                    self._cancelled.discard(job_id)
                    self._jobs.pop(job_id, None)
                    return None
                self._jobs[job_id] = "running"
            try:
                return work(*args)
            finally:
                with self._lock:
                    self._jobs.pop(job_id, None)

        try:
            self._executor.submit(run)
        except BaseException:
            with self._lock:
                self._jobs.pop(job_id, None)
            raise
        return True

    def cancel(self, job_id: str) -> str:
        """'queued' — removed from the queue before start; 'running' — already being computed,
        the thread cannot be stopped (the result is simply not shown);
        'unknown' — there is no such task in the queue."""
        with self._lock:
            state = self._jobs.get(job_id)
            if state == "queued":
                self._cancelled.add(job_id)
                return "queued"
            return state or "unknown"

    def position(self, job_id: str) -> int | None:
        with self._lock:
            waiting = [key for key, state in self._jobs.items() if state == "queued"]
            return waiting.index(job_id) + 1 if job_id in waiting else None

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "active": sum(s == "running" for s in self._jobs.values()),
                "queued": sum(s == "queued" for s in self._jobs.values()),
                "capacity": self.capacity,
                "workers": self.workers,
            }

    def shutdown(self):
        self._executor.shutdown(wait=True)
