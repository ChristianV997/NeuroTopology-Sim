# Background Queue Worker + Batch Report Runner v1

Status: **implemented.** This document describes the `job_runner.queue`/
`job_runner.worker`/`job_runner.batch`/`job_runner.batch_manifest`
modules as they exist today. It does not describe, and should not be
read as promising, any of the capabilities listed in [Future
work](#future-work) -- those are explicitly out of scope for this
milestone.

This is the bridge from one-off job execution ([docs/job_runner.md](job_runner.md))
to nightly batch demos, benchmark-pack generation, and repeatable
productized report production. It adds two things on top of
`job_runner`'s existing `PipelineJobV1` store: a **worker** that
discovers and runs queued jobs one at a time under their existing locks,
and a **batch** primitive that creates and runs many jobs from a list of
`ReportPipelineSpecV1` files in one call.

```
outputs/jobs/<job_id>/PipelineJob.json  (already exists, per docs/job_runner.md)
        |
        v   job_runner.queue.scan_job_queue() / select_next_jobs()
        |     -- read-only; never executes, never mutates a job file
        v
job_runner.worker.run_worker_once() / run_worker_loop()
        |     -- calls job_runner.runner.run_pipeline_job() unmodified, one job at a time
        v
WorkerRunManifestV1  (jobs_selected/completed/failed/blocked/skipped, result_paths)

ReportPipelineSpecV1 files (many)
        |
        v   job_runner.batch.create_batch_from_specs()
        |     -- one JobStore.create_job() call per spec, never mutated
        v
BatchRunManifestV1  (job_ids, batch_status="created")
        |
        v   job_runner.batch.run_batch()
        |     -- runs only this batch's own job_ids, via run_pipeline_job()
        v
BatchRunManifestV1  (batch_status updated, completed/failed/blocked/skipped_count)
```

## What it does

- **Scans** `outputs/jobs/` for created/queued/running/completed/failed/
  blocked/cancelled jobs without executing anything
  (`job_runner.queue.scan_job_queue`).
- **Selects** eligible jobs deterministically by priority, then creation
  time, then job id (`job_runner.queue.select_next_jobs`).
- **Runs** up to a bounded number of selected jobs, one at a time, each
  under its own existing lock, via the unmodified
  `job_runner.runner.run_pipeline_job` (`job_runner.worker.run_worker_once`).
- **Loops** a bounded number of times with an optional sleep between
  iterations -- never an unbounded daemon (`job_runner.worker.run_worker_loop`).
- **Creates a batch** of jobs from a list of `ReportPipelineSpecV1`
  files in one call, without running any of them
  (`job_runner.batch.create_batch_from_specs`).
- **Runs a batch**, executing only the jobs that batch itself created,
  and aggregates a `batch_status` from the outcome
  (`job_runner.batch.run_batch`).
- Exposes all of the above through a CLI
  (`python -m job_runner.export_worker`).

## What it does not do

- **No new scientific logic.** The worker and batch runner call
  `job_runner.runner.run_pipeline_job` (which itself calls
  `workflows.report_pipeline.run_report_pipeline`/
  `workflows.html_report_pack.render_html_report_pack` unmodified) --
  neither module contains feature extraction, raw EEG/fMRI signal
  processing, or an LLM call.
- **No distributed queue, no cloud deployment, no authentication, no
  billing, no upload UI, no frontend dashboard.**
- **No dataset download.** A job's `pipeline_spec` is executed exactly
  as it already would be by `job_runner.runner.run_pipeline_job` directly
  -- the worker/batch layer adds no new input-fetching behavior.
- **No seed-registry mutation.** `job_runner/queue.py`, `job_runner/worker.py`,
  `job_runner/batch.py`, and `job_runner/batch_manifest.py` never call a
  registry's `.save(...)`/construct a `SeedRegistry` themselves -- a
  source-guard test (`test_job_worker_never_touches_seed_registries`)
  asserts this directly.
- **No Celery/RQ/Redis/cloud dependency.** Scanning, selection, and
  looping are pure Python over the file-backed `outputs/jobs/` layout
  `job_runner.store` already uses -- no new dependency was added for
  this milestone.
- **Does not itself constitute evidence.** `WorkerRunManifestV1`/
  `BatchRunManifestV1` are tracked records of execution attempts,
  indexing the same `PipelineJobResultV1`/`ReportPackV1` artifacts
  `job_runner.runner` already produces -- neither carries a
  `claim_scope`/`evidence_level` field of its own.

## Why this is not a distributed/cloud queue

The mission for this milestone was explicit: build the local execution
substrate a future distributed worker would sit on top of, without
building the distributed system itself. `job_runner.queue`'s scanning is
a plain filesystem glob over `outputs/jobs/*/PipelineJob.json`; the
worker's "queue" is that same directory, re-scanned on each loop
iteration; a "batch" is just a manifest file listing job ids created
together. There is no message broker, no shared lock service beyond the
file-based `PipelineJob.lock` sentinel `job_runner.store` already uses,
and no cross-machine coordination -- this worker assumes a single
process on a single machine, exactly like every other CLI tool in this
repository.

## Queue scanning

`job_runner.queue.scan_job_queue(jobs_root, status_filter=None) -> JobQueueStateV1`
reads every `PipelineJob.json` under `jobs_root` and buckets each job's
`job_id` by status: `created`/`queued` jobs go into `queued_job_ids`
(nothing in `job_runner.store` ever transitions a job to `"queued"`
today, so a freshly created job and an explicitly queued one are treated
as the same kind of pending work), `running` jobs into `running_job_ids`,
`completed`/`completed_with_warnings` into `completed_job_ids`, and so on
for `failed`/`blocked`/`cancelled`. An unparseable job file is recorded
in `metadata["scan_warnings"]` rather than silently dropped or crashing
the scan. Scanning never executes anything and never mutates a job file.

`job_runner.queue.select_next_jobs(jobs_root, max_jobs=1, statuses=("queued", "created"))`
returns up to `max_jobs` `PipelineJobV1` records, ordered deterministically
by `(-priority, created_at, job_id)` -- higher priority first, ties
broken by earliest creation, then by job id. `running`/`completed`/
`completed_with_warnings`/`failed`/`cancelled`/`blocked` jobs are never
selected regardless of the `statuses` argument.

## Worker behavior

`job_runner.worker.run_worker_once(jobs_root, max_jobs=1, dry_run=False, worker_id=None) -> WorkerRunManifestV1`:

1. Selects up to `max_jobs` eligible jobs via `select_next_jobs`.
2. If `dry_run`: records the selected jobs and returns without executing
   anything.
3. Otherwise, for each selected job (in order):
   - if the job has already exhausted `max_attempts` (a defensive check
     for a job manually reset to `"queued"` after already failing every
     attempt), it is counted in `jobs_blocked` and never run;
   - otherwise calls `job_runner.runner.run_pipeline_job(job)` under that
     job's own lock;
   - a `JobLockError` (another attempt genuinely in progress) is recorded
     in `lock_conflicts`, not treated as a failure;
   - any other exception is recorded in `jobs_failed`/`errors`;
   - a successful result is bucketed into `jobs_completed`/`jobs_failed`
     by its own `job_status`.
4. Never raises past a recoverable per-job problem -- always continues to
   the next selected job.

`job_runner.worker.run_worker_loop(jobs_root, max_jobs_per_loop=1, max_loops=1, poll_interval_seconds=0, dry_run=False)`
calls `run_worker_once` up to `max_loops` times, sleeping
`poll_interval_seconds` between iterations, and returns one
`WorkerRunManifestV1` per loop (including loops that found no eligible
jobs). `max_loops` is required and capped -- there is no "run forever"
mode in v1.

## Batch behavior

`job_runner.batch.create_batch_from_specs(spec_paths, jobs_root, requested_outputs=None, batch_name="") -> BatchRunManifestV1`
creates one `PipelineJobV1` per spec path via the existing
`JobStore.create_job(spec_path=...)` -- every spec file is only ever
opened for reading, never mutated, and nothing is executed. The
resulting `BatchRunManifestV1` (`batch_status="created"`) is written to
`outputs/jobs/batches/<batch_id>/BatchRunManifest.json`.

`job_runner.batch.run_batch(batch_manifest_path, max_jobs=None, dry_run=False) -> BatchRunManifestV1`
runs only the jobs that batch itself created (by `job_ids`, never a
queue-wide scan), one at a time via `run_pipeline_job`. A job already
`blocked` before the call is counted in `blocked_count` and never
executed; a `cancelled` job is counted in `skipped_count` and never
executed; a lock conflict is also counted in `skipped_count`. The
aggregate `batch_status` is:

- `completed` if every selected job completed (or the batch is empty),
- `failed` if every selected job failed,
- `blocked` if every selected job was already blocked,
- `completed_with_failures` for any other mix (including partial
  skips/lock conflicts),
- `queued` for a `dry_run` call (nothing was actually run).

## CLI

```bash
python -m job_runner.export_worker scan --jobs-root outputs/jobs

python -m job_runner.export_worker run-once --jobs-root outputs/jobs --max-jobs 1

python -m job_runner.export_worker loop --jobs-root outputs/jobs \
    --max-loops 3 --max-jobs-per-loop 1 --poll-interval-seconds 0

python -m job_runner.export_worker create-batch --spec a.json --spec b.json \
    --jobs-root outputs/jobs --requested-output report_pack --requested-output html_report_pack \
    --batch-name demo_batch

python -m job_runner.export_worker run-batch --batch outputs/jobs/batches/<batch_id>/BatchRunManifest.json
```

- `scan` prints queue counts as JSON.
- `run-once` prints `worker_run_id`, selected/completed/failed/blocked/
  skipped job ids, lock conflicts, and result paths.
- `loop` prints an aggregate summary across all loop iterations.
- `create-batch` prints `batch_id` and the created `job_ids`.
- `run-batch` prints the batch's final status and counts.
- `--dry-run` is supported by `run-once`, `loop`, and `run-batch`.
- `loop` requires `--max-loops` explicitly -- there is no default
  "run forever" behavior.
- Every subcommand fails clearly (non-zero exit, `FAILED: ...` message)
  on an invalid `jobs-root`, a missing batch manifest, or an out-of-bounds
  `--max-jobs`/`--max-loops`/`--poll-interval-seconds`.
- Lock conflicts are reported, not fatal, unless *every* job the worker
  selected in that invocation hit one.

## Output structure

```
outputs/jobs/
    <job_id>/PipelineJob.json, PipelineJobResult.json, ...   (unchanged, see docs/job_runner.md)
    batches/
        <batch_id>/
            BatchRunManifest.json
```

No new job-record layout was introduced -- `job_runner.worker`/
`job_runner.batch` only read and call `job_runner.store`/
`job_runner.runner`, which already own `outputs/jobs/<job_id>/`. The
only new on-disk artifact is `BatchRunManifest.json`, one per batch,
under `outputs/jobs/batches/<batch_id>/`.

## Integration with `ReportPipelineSpecV1`/`PipelineJobV1`

Both the worker and the batch runner operate entirely in terms of
already-existing `job_runner` objects: `run_worker_once`/`run_worker_loop`
call `job_runner.runner.run_pipeline_job(job: PipelineJobV1)` unmodified;
`create_batch_from_specs` calls `job_runner.store.JobStore.create_job`
(which itself validates each `ReportPipelineSpecV1` before creating a
job) unmodified. No new pipeline-execution code path was added anywhere
in this milestone.

## Future SaaS/API worker relevance

`run_worker_once`/`run_batch` are plain Python functions with no
CLI/filesystem-argv coupling beyond their arguments -- a future
authenticated API endpoint or hosted worker process could call either
directly, exactly as `job_runner.api.run_job` already calls
`job_runner.runner.run_pipeline_job` from a parsed JSON payload
(see [docs/job_runner.md](job_runner.md#optional-local-api)).
`WorkerRunManifestV1`/`BatchRunManifestV1` are already JSON-serializable,
so a hosted worker's status/result payload needs no new serialization
layer. This is the concrete substrate for future SaaS workers, nightly
batch demos, benchmark-pack generation, lab onboarding, and productized
report production.

## Limitations

- `run_worker_loop`'s bound is process-lifetime, not wall-clock --
  running it inside a long-lived process (e.g. under `cron`/`systemd`)
  is the intended way to approximate a recurring worker in v1, not a
  built-in scheduler.
- The lock is the same local sentinel file `job_runner.store` already
  uses -- it prevents two attempts at the same job on the same machine
  from running concurrently, not across machines.
- A job's `attempts >= max_attempts` guard in `run_worker_once` is
  defensive, not a retry policy -- there is no backoff, no automatic
  retry scheduling, and no way to "unblock" a job in v1 beyond manually
  editing its `PipelineJob.json`.
- `run_batch`'s `blocked`/`cancelled` handling only recognizes a job
  whose status was already `blocked`/`cancelled` *before* the call --
  nothing in this milestone ever sets either status itself.
- No authenticated API exists for the worker/batch functions -- see
  [docs/job_runner.md#optional-local-api](job_runner.md#optional-local-api)
  for the same limitation on the existing job API.

## Future work

**Not implemented by this milestone** -- listed only to show what this
substrate is for; none of these descriptions is a commitment to a
design:

- **Authenticated API** exposing `run_worker_once`/`create_batch_from_specs`/
  `run_batch` the same way `job_runner.api` exposes single-job creation
  and execution today.
- **Hosted worker deployment** -- running `run_worker_loop` as a real
  managed service rather than a bounded local CLI invocation.
- **Upload staging area** -- accepting a caller-supplied spec list
  safely from an untrusted HTTP request, not just local file paths.
- **Retry policy** -- automatic re-queueing with backoff for a failed
  job, rather than the current single-attempt-per-invocation behavior.
- **Distributed locks** -- replacing the local sentinel lock file with a
  cross-machine lock service once more than one worker process needs to
  share a job store.
- **Scheduled batch jobs** -- a cron-like trigger that calls
  `create_batch_from_specs`/`run_batch` on a recurring schedule. A
  curated (non-scheduled) batch mode now exists -- see
  [docs/benchmark_pack_generator.md](benchmark_pack_generator.md).
- **PDF export** of a batch's aggregated report packs.

This milestone does not imply clinical validity for any artifact a job
or batch references, does not imply consciousness or spiritual-state
detection regardless of a dataset's subject matter, and does not imply
that a `WorkerRunManifestV1`/`BatchRunManifestV1` is clinical evidence --
evidence begins at `adapters.*`/`evidence.builder`/`reports.evidence_report`,
exactly as it did before this milestone; the worker and batch runner only
track execution of the pipeline that references it.
