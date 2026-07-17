"""Background job queue. Lives in the API layer — core stays synchronous.

Jobs run on a small thread pool; results are parked as JSON in the
workspace (``~/.excellia/jobs/``) so they survive the request that
started them and can be fetched by id. Long-running ops (big files,
training, per-row LLM transforms) go through here; small files keep
using the sync endpoints.
"""

from __future__ import annotations

import json
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable

from fastapi import HTTPException

from excellia.core import store

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="excellia-job")
_jobs: dict[str, dict[str, Any]] = {}
_lock = Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _result_path(job_id: str) -> Any:
    return store.home() / "jobs" / f"{job_id}.json"


def submit(op: str, fn: Callable[[], dict], params_summary: dict | None = None) -> dict:
    """Queue ``fn`` and return {job_id, status, poll} immediately."""
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = {
            "job_id": job_id, "op": op, "status": "queued",
            "submitted": _now(), "params": params_summary or {},
        }

    def run() -> None:
        with _lock:
            _jobs[job_id]["status"] = "running"
            _jobs[job_id]["started"] = _now()
        try:
            result = fn()
            _result_path(job_id).write_text(
                json.dumps(result, default=str), encoding="utf-8"
            )
            with _lock:
                _jobs[job_id].update(status="done", finished=_now())
        except HTTPException as e:  # instructive core/API error, not a crash
            with _lock:
                _jobs[job_id].update(status="error", error=str(e.detail), finished=_now())
        except Exception as e:
            with _lock:
                _jobs[job_id].update(
                    status="error", finished=_now(),
                    error=f"{type(e).__name__}: {e}",
                    trace=traceback.format_exc(limit=3),
                )
        store.record(f"job:{op}", params=params_summary,
                     summary={"job_id": job_id, "status": _jobs[job_id]["status"]})

    _executor.submit(run)
    return {"job_id": job_id, "status": "queued",
            "poll": f"GET /jobs/{job_id} until status is 'done', then read 'result'"}


def status(job_id: str) -> dict:
    """Job record; includes the parked result once done."""
    with _lock:
        job = _jobs.get(job_id)
    if job is None:
        # Not in this process — maybe a previous API run; try the parked result.
        path = _result_path(job_id)
        if path.exists():
            return {"job_id": job_id, "status": "done",
                    "result": json.loads(path.read_text(encoding="utf-8")),
                    "note": "restored from a previous API session"}
        raise HTTPException(
            404, f"No job '{job_id}'. List jobs with GET /jobs; results expire "
                 "when the workspace jobs/ dir is cleaned.")
    job = dict(job)
    if job["status"] == "done":
        path = _result_path(job_id)
        if path.exists():
            job["result"] = json.loads(path.read_text(encoding="utf-8"))
    return job


def list_jobs() -> list[dict]:
    with _lock:
        return sorted(_jobs.values(), key=lambda j: j["submitted"], reverse=True)
