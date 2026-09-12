# Bounded local simulation execution

`tools.simulation_execution` provides a small local execution API for already-declared engineering workloads. It is process-isolated, resumable, and deliberately does not know how to construct or execute scientific solver equations.

## Contract

Each `WorkUnit` must provide a stable `unit_id`, `workload_id`, exact argv, explicit output directory, expected output names, and optional input references, seed, configuration, dependencies, and timeout. `RunnerConfig` requires an explicit output root and an exact `workload_id -> argv` allowlist. Commands use `shell=False`; no shell fragments, AWS/cloud routes, package installation, daemons, LLMs, or unrestricted command discovery are supported.

The runner writes `execution_manifest.json` atomically after initialization and after every work unit. Each record includes command identity, code revision, configuration, seed, input/output references, resource telemetry, stdout/stderr with bounded capture, checksums, state, and limitations. A work unit must create a finite `unit_manifest.json` whose `work_unit_id` matches and whose `complete` value is true before it can be `PASS`.

## State machine

`PASS` means the allowlisted process exited zero and every declared output is contained, present, finite where JSON, and covered by a checksum. `TIMEOUT` terminates the process group/session and has null checksums. `PARTIAL` covers an explicitly partial unit manifest and also has null checksums. `FAILED` covers non-zero exit, invalid/missing output, exceeded disk or memory budgets, and has null checksums. `BLOCKED` covers allowlist, network-policy, or output-containment violations. `NOT_RUN` records a dependency that was not eligible. `INFRASTRUCTURE_FAILURE` records launch, persistence, or required resource-measurement failures.

No non-`PASS` unit receives a valid output checksum. Successful execution is an engineering/runtime result only; it is not scientific validation, empirical evidence, biological evidence, causal evidence, or evidence about consciousness.

## Isolation and recovery

Every child receives a new process group/session. Timeouts terminate the whole group/tree, and stdout/stderr are spooled to temporary files before bounded truncation. The default environment fixes hash seed, locale, timezone, source-date epoch, and numerical thread counts. Network-disabled mode is the default: Python workloads receive a socket guard and non-Python workloads are blocked unless the caller explicitly opts into network-enabled mode.

On resume, only a prior `PASS` record whose output files still exist with exactly matching checksums is skipped. Changed, missing, or invalid outputs rerun. Dependency failures leave dependent units `NOT_RUN`; partial, timed-out, or failed units never become complete through recovery. The existing artifact-lineage extractor is accessed only through `lineage_adapter.py`, and its absence cannot turn execution failure into `PASS`.
