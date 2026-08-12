"""Optional local-dev HTTP API for `job_runner`, following the exact
`try: from fastapi import FastAPI / except Exception: FastAPI = None`
fallback already established in `api/rag_server.py`.

**Local-dev only. Not production-ready. No authentication in v1.** This
module exists so a future SaaS/API worker has a concrete starting point,
not so this repository ships a hardened service today: no auth, no
upload handling, no rate limiting, no TLS, synchronous request handling
(a `run` request blocks until the pipeline finishes). Do not expose this
outside a local machine.

`fastapi` is declared (unpinned) in `requirements.txt`, so whether it is
actually importable is an environment fact, not a repository constant --
this repository's local sandbox does not have it installed, while a CI
job that runs `pip install -r requirements.txt` does (see
`docs/ci_failure_audit.md` for the PR #203 Required Checks failure this
distinction caused, and its fix). `API_AVAILABLE` below reflects the
*actual* import state in whatever environment this module runs in -- it
is computed once from a real `try: import / except: None`, never
hardcoded. The plain functions (`health`/`create_job`/`get_job`/
`run_job`/`list_jobs`) work regardless -- they are what the tests import
and call directly -- and are the same functions the FastAPI routes call
when the dependency is present. Every one of them is a thin wrapper over
`job_runner.store.JobStore` / `job_runner.runner.run_pipeline_job`; no
pipeline logic is duplicated here. See docs/job_runner.md.
"""
from __future__ import annotations

from typing import Any, Optional

try:
    from fastapi import FastAPI
except Exception:
    FastAPI = None

from job_runner.export_job import _job_summary, _result_summary
from job_runner.store import DEFAULT_JOBS_ROOT, JobStore

API_AVAILABLE: bool = FastAPI is not None


def health() -> dict[str, Any]:
    return {"ok": True, "fastapi_available": API_AVAILABLE}


def create_job(payload: dict[str, Any], *, jobs_root: str = DEFAULT_JOBS_ROOT) -> dict[str, Any]:
    """`payload` mirrors the CLI's `create` arguments: one of
    `spec_path`/`spec_dict`, plus optional `requested_outputs`/`job_name`/
    `priority`/`max_attempts`. Never executes the pipeline."""
    store = JobStore(payload.get("jobs_root", jobs_root))
    job = store.create_job(
        spec_path=payload.get("spec_path"), spec_dict=payload.get("spec_dict"),
        requested_outputs=payload.get("requested_outputs"), job_name=payload.get("job_name", ""),
        priority=payload.get("priority", 0), max_attempts=payload.get("max_attempts", 1),
    )
    return _job_summary(job)


def get_job(job_id: str, *, jobs_root: str = DEFAULT_JOBS_ROOT) -> dict[str, Any]:
    store = JobStore(jobs_root)
    job = store.load_job(job_id)
    out = _job_summary(job)
    result = store.load_result(job_id)
    if result is not None:
        out["result"] = _result_summary(result)
    return out


def run_job(job_id: str, *, jobs_root: str = DEFAULT_JOBS_ROOT) -> dict[str, Any]:
    """Synchronous: blocks until the pipeline run finishes (see module
    docstring -- no background queue in v1)."""
    from job_runner.runner import run_pipeline_job

    store = JobStore(jobs_root)
    job = store.load_job(job_id)
    result = run_pipeline_job(job, store=store)
    return _result_summary(result)


def list_jobs(status: Optional[str] = None, *, jobs_root: str = DEFAULT_JOBS_ROOT) -> list[dict[str, Any]]:
    store = JobStore(jobs_root)
    return [_job_summary(job) for job in store.list_jobs(status=status)]


def get_app() -> Any:
    """Returns a FastAPI app wired to the functions above, or `None` if
    `fastapi` is not installed in this environment -- callers must check
    for `None` rather than assume the API is usable."""
    if not API_AVAILABLE:
        return None

    app = FastAPI(title="job_runner API (local dev only, no auth)")
    app.get("/health")(health)
    app.post("/jobs")(lambda payload: create_job(payload))
    app.get("/jobs")(lambda status=None: list_jobs(status))
    app.get("/jobs/{job_id}")(lambda job_id: get_job(job_id))
    app.post("/jobs/{job_id}/run")(lambda job_id: run_job(job_id))
    return app


app = get_app()


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args(argv)
    if args.smoke_test:
        _ = health()
        print("job_runner_api_smoke_ok")
        return 0
    if API_AVAILABLE:
        print("FastAPI available -- run e.g. `uvicorn job_runner.api:app` (local dev only, no auth).")
    else:
        print("FastAPI is not installed in this environment -- job_runner.api's plain functions "
              "(health/create_job/get_job/run_job/list_jobs) still work and are what tests call directly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
