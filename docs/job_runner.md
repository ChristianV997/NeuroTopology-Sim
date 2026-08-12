# Local/API Report Pipeline Job Runner v1

Status: **implemented.** This document describes the `job_runner/`
package as it exists today. It does not describe, and should not be read
as promising, any of the capabilities listed in [Future
work](#future-work) -- those are explicitly out of scope for this
milestone.

This is the bridge from "manual CLI report generation" to "future SaaS
worker / batch report service." Every prior milestone
([docs/report_pipeline_runner.md](report_pipeline_runner.md),
[docs/html_report_pack_renderer.md](html_report_pack_renderer.md)) built
one deterministic function call (`run_report_pipeline`) and one CLI
invocation per run. `job_runner/` adds a **tracked execution layer**
around that call: a job has an id, a status, a store, a lock, and a
result -- the minimum a queue worker, a batch demo, or a lab-onboarding
script needs, without adding a queue, a database, or a network service.

```
ReportPipelineSpecV1 (already exists)
        |
        v   job_runner.store.JobStore.create_job()
PipelineJobV1  (job_status="created", not yet executed)
        |
        v   job_runner.runner.run_pipeline_job()
        |     -- calls workflows.report_pipeline.run_report_pipeline() unmodified
        |     -- optionally calls workflows.html_report_pack.render_html_report_pack() unmodified
        v
PipelineJobResultV1  (report_pack_id / html_pack_id / errors / warnings)
```

## What it does

Given an already-valid `ReportPipelineSpecV1` (a file path or an
in-memory dict), `job_runner`:

- creates a `PipelineJobV1` record on disk without executing anything
  (`JobStore.create_job`);
- executes exactly one job by calling `workflows.report_pipeline.run_report_pipeline`
  and, if requested, `workflows.html_report_pack.render_html_report_pack`
  (`job_runner.runner.run_pipeline_job`);
- tracks job status through an explicit lifecycle
  (`created -> running -> completed|completed_with_warnings|failed`, plus
  `queued`/`cancelled`/`blocked` for future use);
- prevents two attempts at the same job from running concurrently (an
  exclusive lock file);
- exposes all of the above through a CLI (`python -m job_runner.export_job`)
  and, where the dependency is available, a minimal local HTTP API
  (`job_runner.api`).

## What it does not do

- **No new scientific logic.** `job_runner` calls
  `workflows.report_pipeline.run_report_pipeline`/
  `workflows.html_report_pack.render_html_report_pack` unmodified -- it
  contains no feature extraction, no raw EEG/fMRI signal processing, no
  persistent-homology computation, and no LLM call.
- **No user accounts, authentication, or billing.**
- **No cloud deployment, file-upload UI, or frontend dashboard.**
- **No dataset download.** A job's `pipeline_spec` is executed exactly as
  `workflows.export_report_pack` would execute it directly -- if the
  underlying spec's `input_mode` needs a local path, that path must
  already exist; `job_runner` never fetches anything over the network.
- **No seed-registry mutation.** `job_runner/runner.py` and
  `job_runner/store.py` never call a registry's `.save(...)`/construct a
  `SeedRegistry` themselves -- every registry write, if any, happens
  inside `run_report_pipeline` exactly as it already did.
- **Does not itself constitute evidence.** A `PipelineJobResultV1` is a
  tracked record of one execution attempt, indexing the
  `TransitionRecordV1`/`EvidenceBundleV1`/`EvidenceReportV1`/`ReportPackV1`
  artifacts the underlying modules already produced -- it carries no
  `claim_scope`/`evidence_level` field of its own (see [How a job result
  differs from evidence](#how-a-job-result-differs-from-evidence)).

## Why local-first and file-backed

The mission for this milestone was explicit: build the execution
substrate a future SaaS worker would sit on top of, without building the
SaaS worker itself. A file-backed job store needs no database, no
message broker, and no long-running service to be useful today -- `git
status`/`ls`/`cat` are enough to inspect it -- while still being a
faithful model of what a real queue worker would do (create a job
record, execute it, write a result, release a lock). Every write goes
through `dataset_acquisition.store.validate_target_root`, the same
`outputs/`/`data/`-only safety check every other module in this
repository already uses, so a job store can never write into a tracked
source directory.

## Job lifecycle

```
created --(run_pipeline_job)--> running --> completed
                                         --> completed_with_warnings
                                         --> failed
```

`queued`, `cancelled`, and `blocked` are valid `job_status` values (see
[PipelineJobV1 schema](#pipelinejobv1-schema-summary)) reserved for a
future queue worker that schedules jobs rather than running them
immediately -- `job_runner.runner.run_pipeline_job` itself only ever
transitions `created|queued -> running -> {completed, completed_with_warnings,
failed}`.

- A **dry-run** spec (`spec.dry_run=True`) always finishes `completed`,
  but its result never claims report generation: `report_pack_id`,
  `report_pack_path`, `html_pack_id`, `html_pack_path`,
  `index_html_path`, and `generated_files` are all forced empty/`None`
  regardless of what `requested_outputs` asked for.
- A **failed** pipeline run (bad input, denied registry use, ...) never
  crashes the job runner -- the failure is caught, `job_status="failed"`,
  and the underlying error message(s) are recorded in both the job's
  `error_summary` and the result's `errors` list.
- An **HTML rendering failure that happens after a valid report pack was
  already produced** does not fail the whole job -- the report pack is
  real and unaffected, so the job finishes `completed_with_warnings` with
  the renderer's error recorded in `warnings`, and `html_pack_id`/
  `index_html_path` left `None`.

## Job store

`job_runner.store.JobStore` is stdlib-only and file-backed:

```
outputs/jobs/<job_id>/
    PipelineJob.json          -- the PipelineJobV1 record (always present)
    PipelineJobResult.json    -- the PipelineJobResultV1 record (only after a run attempt)
    PipelineJob.lock          -- present only while a run attempt is in progress
    logs/
        summary.json          -- small, human-readable run summary
```

- **Atomic writes.** Every write goes through `_atomic_write_text`:
  write to a temp file in the same directory (`tempfile.mkstemp`), then
  `os.replace` -- atomic on POSIX, so a concurrent reader never observes
  a partially-written `PipelineJob.json`.
- **Locking.** `acquire_job_lock`/`release_job_lock` use
  `os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)`, which atomically
  raises `FileExistsError` (converted to `JobLockError`) if another
  attempt already holds the lock. This is deliberately stdlib-only --
  `filelock` happens to already be installed in this repository's
  environment, but the mission's Phase C requirement for the job store
  itself was stdlib-first, so no third-party lock library is used here.
- **Output-root safety.** `JobStore.__init__` validates `jobs_root` via
  `dataset_acquisition.store.validate_target_root` at construction --
  the same `outputs/`/`data/`-only, no-`..`-traversal check every other
  module in this repository already uses. A job's own `output_root` (the
  report pack's destination) is validated the same way inside
  `PipelineJobV1.validate()`.
- Core functions: `create_job`, `load_job`, `list_jobs`, `save_job`,
  `update_job_status`, `write_result`, `load_result`, `write_summary`,
  `acquire_job_lock`, `release_job_lock`, `is_locked`.

## Runner behavior

`job_runner.runner.run_pipeline_job(job, *, store=None) -> PipelineJobResultV1`:

1. Validates the job and its embedded spec structurally
   (`job.validate_or_raise()`, `spec.validate_or_raise()`) -- before
   acquiring any lock, so a structurally invalid job never blocks a
   retry.
2. Acquires the job's lock (`JobLockError` propagates uncaught -- another
   attempt is genuinely in progress right now, this is a caller-level
   problem, not an execution failure to record).
3. Sets `job_status="running"`, records `started_at`, increments
   `attempts`, persists the job.
4. Calls `workflows.report_pipeline.run_report_pipeline(spec)` unmodified.
5. If `html_report_pack` was requested and the spec itself didn't already
   produce one, calls `workflows.html_report_pack.render_html_report_pack`
   unmodified on the just-produced report pack.
6. Captures every artifact path/id the underlying manifest already
   computed (`report_pack_id` read back from the written `ReportPack.json`,
   `html_pack_id`/`index_html_path` from the manifest's own
   `metadata["html_report_pack"]` when the spec rendered it directly).
7. Writes a `PipelineJobResultV1` via the store.
8. Sets the job's final status (`completed`/`completed_with_warnings`/`failed`)
   and `completed_at`, persists the job, writes the summary.
9. Releases the lock in a `finally` block -- guaranteed even if step 4/5
   raised something unexpected.
10. Never raises past a *recoverable* execution failure -- every problem
    inside `run_report_pipeline`/`render_html_report_pack` is caught and
    turned into `job_status="failed"` + a recorded error message,
    mirroring `run_report_pipeline`'s own "fail into the manifest, don't
    crash" discipline.

## CLI

```bash
python -m job_runner.export_job create --spec pipeline_spec.json --out outputs/jobs \
    --requested-output report_pack --requested-output html_report_pack

python -m job_runner.export_job run --job outputs/jobs/<job_id>/PipelineJob.json

python -m job_runner.export_job run-spec --spec pipeline_spec.json --out outputs/jobs \
    --requested-output html_report_pack

python -m job_runner.export_job status --job <job_id or path/to/PipelineJob.json>

python -m job_runner.export_job list --jobs-root outputs/jobs --status completed
```

- `create` only writes a `PipelineJobV1` -- it never executes the
  pipeline.
- `run` executes exactly one already-created job (by `job_id` or by a
  direct path to its `PipelineJob.json`).
- `run-spec` is `create` immediately followed by `run` in one
  invocation.
- `status` prints the job's current record and, if present, its result,
  as JSON.
- `list` prints every job under `--jobs-root`, optionally filtered by
  `--status`.
- Every subcommand fails clearly (non-zero exit, `FAILED: ...` message)
  on an invalid spec, an invalid output root, a missing job, a lock
  conflict, or an unsupported `--requested-output` value.

## Optional local API

`job_runner/api.py` follows the exact `try: from fastapi import FastAPI
/ except Exception: FastAPI = None` fallback already established in
`api/rag_server.py`. **`fastapi` is declared (unpinned) in
`requirements.txt` but is not installed in this repository's Python
environments as of this milestone** -- confirmed via `pip show fastapi`
(not found) and a direct `import fastapi` (`ModuleNotFoundError`) in both
the root environment and `.venv/`; the isolated `apps/awareness_studio/`
environment does declare `fastapi>=0.111` in its own `pyproject.toml`,
but that is a separate Python environment per this repository's
documented "Two Python Environments" split and is not importable from
`job_runner/`.

`job_runner.api.API_AVAILABLE` reflects this honestly (`False` today).
`job_runner.api.app` is a real `FastAPI` instance when the dependency is
present, and `None` otherwise -- callers must check for `None` rather
than assume the API is usable. The plain functions underneath
(`health`/`create_job`/`get_job`/`run_job`/`list_jobs`) work regardless
of `fastapi`'s availability -- they are what the test suite calls
directly, and they are the same functions the FastAPI routes call when
the dependency is present, so no logic is duplicated between the two.

Endpoints (once `fastapi` is installed): `GET /health`, `POST /jobs`,
`GET /jobs/{job_id}`, `POST /jobs/{job_id}/run`, `GET /jobs`.

**Local dev only. Not production-ready.** No authentication in v1, no
upload handling, no rate limiting, no TLS, and request handling is
synchronous -- a `run` request blocks until the pipeline finishes. Do not
expose this outside a local machine.

## Job store / result structure

### PipelineJobV1 schema summary

`schema_version`, `job_id`, `job_name`, `pipeline_spec_path`,
`pipeline_spec` (embedded dict), `requested_outputs`
(`report_pack`/`html_report_pack`/`json_manifests_only`), `job_status`
(`created`/`queued`/`running`/`completed`/`completed_with_warnings`/`failed`/
`cancelled`/`blocked`), `priority`, `created_at`, `started_at`,
`completed_at`, `output_root`, `lock_path`, `attempts`, `max_attempts`,
`error_summary`, `limitations`, `provenance`, `metadata`.

`job_id` deliberately includes `created_at` in its hash basis (see
[The job_id tradeoff](#the-job_id-tradeoff) below) -- resubmitting an
identical spec twice must produce two distinct, independently trackable
jobs, not a collision on the same output directory.

### PipelineJobResultV1 schema summary

`schema_version`, `result_id`, `job_id`, `job_status`, `pipeline_id`,
`pipeline_run_id`, `report_pack_id`, `html_pack_id`, `output_root`,
`pipeline_manifest_path`, `report_pack_path`, `html_pack_path`,
`index_html_path`, `generated_files`, `errors`, `warnings`, `started_at`,
`completed_at`, `repo_commit`, `limitations`, `provenance`, `created_at`,
`metadata`.

`result_id` is content-addressed over the result's own identity fields
(`job_id`/`job_status`/`report_pack_id`/`html_pack_id`/`generated_files`)
without its own separate `created_at` -- since `job_id` already anchors
this result to one execution event, re-deriving the same finished
outcome for the same job is recognized as the same result.

### The job_id tradeoff

`PipelineJobV1` is structurally an **execution event**, not a pure
request identity -- unlike `pipeline_id`/`report_pack_id`/`html_pack_id`
(which identify *what would be produced* and stay pure content
addresses), a job's whole purpose is to track *one specific attempt*
over time, with mutable `job_status`/`attempts`/`started_at`/
`completed_at` fields. `compute_job_id` therefore includes `created_at`
in its hash basis, the same "documents one execution event" precedent
`workflows.report_pipeline.compute_run_id` and the feature-recipe
`compute_manifest_id` functions already established in this repository.
The tradeoff: two jobs created from the identical spec at different
times get different `job_id`s and different output directories (by
design -- each is an independently trackable attempt), so a caller who
wants true request-level deduplication should compare `pipeline_id`
(inside the embedded `pipeline_spec`), not `job_id`.

## How a job result differs from evidence

A `PipelineJobResultV1` is not itself evidence -- it is a tracked record
of one pipeline execution attempt, indexing the
`TransitionRecordV1`/`EvidenceBundleV1`/`EvidenceReportV1`/`ReportPackV1`
artifacts the underlying, already-governed modules produced. It carries
no `claim_scope`/`evidence_level` field of its own (`job_runner.validation`
explicitly rejects one if ever added), and its `limitations` always
state that it is not itself evidence. See
[docs/report_pipeline_runner.md#how-a-report-pack-differs-from-evidence](report_pipeline_runner.md#how-a-report-pack-differs-from-evidence)
for where the actual scientific/governance claims a report pack
references are made and bounded -- `job_runner` only tracks execution of
that pipeline, it makes no claims of its own.

## Future SaaS/API worker relevance

`run_pipeline_job(job) -> PipelineJobResultV1` is a plain Python function
with no CLI/filesystem-argv coupling beyond the job object itself -- a
future queue worker can call it directly with a job built from an API
request body, exactly as `job_runner.api.create_job`/`run_job` already do
from a parsed JSON payload. `PipelineJobV1`/`PipelineJobResultV1` are
both already JSON-serializable, so a worker's job payload and result
payload need no new serialization layer. This is the concrete substrate
for future SaaS workers, batch demos, lab onboarding, and productized
report generation.

## Limitations

- `json_manifests_only` in `requested_outputs` is a no-op relative to
  `report_pack`/`html_report_pack` -- its presence signals "don't force
  extra artifact generation beyond what the spec's own `include_*` flags
  already produce," it does not itself trigger any runner behavior.
- No background queue worker exists in v1 -- `run` (CLI) and `run_job`
  (API) both execute synchronously and block until the pipeline
  finishes.
- The lock is a local sentinel file, not a distributed lock -- it
  prevents two attempts at the same job on the same machine from running
  concurrently, not across machines.
- `job_runner.api` is local-dev-only and unauthenticated even when
  `fastapi` is installed -- see [Optional local API](#optional-local-api).

## Future work

**Not implemented by this milestone** -- listed only to show what this
substrate is for; none of these descriptions is a commitment to a
design:

- **Upload staging area** -- accepting a caller-supplied spec/dataset
  path safely from an untrusted HTTP request, not just a local file
  path.
- **Authenticated SaaS API** -- real auth (API keys, per-tenant
  isolation) on top of the same `create_job`/`get_job`/`run_job`/`list_jobs`
  functions.
- **Background queue worker** -- a real consumer (e.g. backed by a
  message queue) that dequeues `queued` jobs and calls
  `run_pipeline_job` asynchronously, using the `queued`/`blocked`
  `job_status` values this schema already reserves. A bounded,
  local, single-process version of this now exists -- see
  [docs/job_worker.md](job_worker.md).
- **Signed report archives** -- a tamper-evident bundle of a completed
  job's `ReportPack.json`/`HtmlReportPack.json`/referenced artifacts.
- **PDF export** of a report pack or HTML report pack.
- **Benchmark-pack batch runner** -- a mode that creates and runs many
  jobs across a dataset registry in one invocation, building on
  `benchmarks/` (`docs/benchmark_dataset_registry.md`).
- **Hosted dashboard** for browsing job history -- `list`/`status`
  already expose the same data as JSON; a dashboard would only be a
  presentation layer over it.

This milestone does not imply clinical validity for any artifact a job
references, does not imply consciousness or spiritual-state detection
regardless of a dataset's subject matter, and does not imply that a
`PipelineJobResultV1` is clinical evidence -- evidence begins at
`adapters.*`/`evidence.builder`/`reports.evidence_report`, exactly as it
did before this milestone; `job_runner` only tracks execution of the
pipeline that references it.
