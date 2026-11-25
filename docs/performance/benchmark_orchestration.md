# Benchmark Orchestration

Bounded, deterministic orchestration for local benchmark / test matrices.
Validates every case before execution, runs **one case per isolated process**,
enforces timeouts / worker caps / retry limits, and emits finite JSON + Markdown
without hiding failures.

| Artifact | Path |
| --- | --- |
| Package | `tools/benchmark_orchestration/` |
| CLI | `scripts/run_benchmark_matrix.py` |
| Tests | `tests/benchmark_orchestration/` |
| Example matrix | `tools/benchmark_orchestration/examples/local_smoke_matrix.json` |

This package does **not** modify `tools/streaming/**`, `scripts/run_tests_isolated.py`,
existing benchmark scripts, CI workflows, or scientific / adapter / dashboard code.

> **Scientific-integrity note.** Matrices and dry-run plans are engineering
> scaffolding for triage and prioritization — never scientific evidence.

## Matrix schema (`1.0`)

```json
{
  "schema_version": "1.0",
  "provenance_label": "local-smoke-matrix",
  "defaults": { "timeout_s": 60, "max_retries": 0, "optional_deps": [] },
  "cases": [
    {
      "id": "unique-case-id",
      "command": ["python", "-m", "pytest", "tests/performance/test_streaming_bounded.py", "-q"],
      "timeout_s": 120,
      "max_retries": 1,
      "optional_deps": [],
      "tags": ["performance"],
      "config": { "chunk_size": 256 },
      "memory_telemetry_ref": null,
      "local_only": true
    }
  ]
}
```

Validation rejects: empty/missing cases, duplicate IDs, invalid timeouts, and
(by default) commands containing network/remote markers (`aws`, `docker`,
`curl`, `wget`, `http://`, `s3://`, …). YAML matrices are supported when PyYAML
is installed; JSON works with stdlib only.

Case ordering is **lexicographic by `case_id`** after validation (deterministic).

## Campaign limits

| Limit | Meaning |
| --- | --- |
| per-case `timeout_s` | Hard kill of the child process tree; status `TIMEOUT` (exit 124) |
| `--total-timeout-s` | Remaining cases become `NOT_RUN` — never PASS |
| `--max-workers` | Cap on concurrent case processes (default 1) |
| `--max-retries` | Bounded retries for crash/infra only; never infinite |

## Status taxonomy

| Status | Meaning |
| --- | --- |
| `PASS` | Exit code 0 |
| `CORRECTNESS_FAILURE` | Non-zero exit (typically assertion / pytest failure) |
| `TIMEOUT` | Per-case wall clock exceeded; **never remapped to PASS** |
| `CHILD_CRASH` | Signal-style / abnormal child termination |
| `INFRASTRUCTURE_BLOCKED` | Executable missing / OS launch failure |
| `OPTIONAL_DEPENDENCY_MISSING` | Declared `optional_deps` import not found |
| `NOT_RUN` | Dry-run, campaign budget exhausted, or not yet executed |

## Captured fields (per case)

`case_id`, `command`, `input_configuration`, `status`, `duration_s`, `exit_code`,
`timed_out`, `stdout_ref`, `stderr_ref`, `checksum` (SHA-256 of captured
stdout/stderr), `memory_telemetry_ref`, `attempts`, `retries_used`.

## Resume

`--resume` loads `output/manifest.json` and skips cases that already have a
**terminal** status. Partial manifests are rewritten after each completed case
(atomic replace). Source trees are never modified during execution.

## CLI

```bash
# Dry-run: validate + plan (all NOT_RUN), no network, no child processes
PYTHONPATH=. python scripts/run_benchmark_matrix.py \
  --matrix tools/benchmark_orchestration/examples/local_smoke_matrix.json \
  --output artifacts/benchmark_orchestration --dry-run

# Execute locally with caps
PYTHONPATH=. python scripts/run_benchmark_matrix.py \
  --matrix tools/benchmark_orchestration/examples/local_smoke_matrix.json \
  --output artifacts/benchmark_orchestration \
  --max-workers 1 --total-timeout-s 600 --max-retries 0
```

Exit codes: `0` success / dry-run OK · `1` correctness/crash/infra · `3` optional-dep only · `124` any timeout · `2` matrix validation error.

## Relationship to PR #236 triage

PR #236 recorded failed and timed-out isolated batches. This orchestrator does
not rewrite those outcomes; it provides a **declarative, resumable** way to
prioritize and re-run local cases with explicit `TIMEOUT` vs `CORRECTNESS_FAILURE`
classification so timeouts are never hidden as passes.

## Memory and process limits

- One OS process per case; BLAS/OpenMP thread env vars pinned to `1`.
- Worker cap bounds concurrency, not RSS.
- `memory_telemetry_ref` is a passthrough path for callers that already produced
  telemetry elsewhere (e.g. PR #215); this package does not rewrite streaming
  telemetry modules.
- Peak process RSS is not fabricated here.

## Known limitations

- ThreadPoolExecutor schedules subprocesses; true process-pool scheduling of
  Python callables is unnecessary because each case already isolates via
  `subprocess.Popen`.
- Retry policy intentionally does **not** retry `TIMEOUT` or
  `CORRECTNESS_FAILURE` (would hide triage signal).
- Wall-clock budgets are host-dependent.
- Local-only heuristics are substring-based; `--allow-network` opts out explicitly.
