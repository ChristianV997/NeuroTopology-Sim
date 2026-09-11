# Research-Cycle Resource Benchmarks

A **local-only, additive** benchmark harness that measures throughput, memory
(tracemalloc + optional RSS), disk usage, determinism, budget compliance, and
failure handling for research-cycle infrastructure *contracts*. It uses
deterministic synthetic fixtures and protocol adapters only.

- Package: `tools/benchmarking/research_cycle_benchmarks/`
- CLI: `scripts/benchmark_research_cycle.py`
- Tests: `tests/benchmarking/research_cycle_benchmarks/`

> **Safety / integrity.** No dataset downloads, no real or full simulations, no
> external API calls, no unbounded concurrency. It imports no simulation kernels,
> performance-policy, process-runner, streaming, orchestrator, or database code,
> and depends on no files other agents are producing in this wave (protocol
> adapters / local fixtures only). Output is synthetic **performance evidence
> only** and makes **no scientific claims**.

## Targets

Each target has a `baseline` (full materialization) and a `candidate` (bounded)
implementation returning the **same deterministic checksum** for a fixture, so
correctness equivalence is verified while memory behavior is compared:

1. `ledger_append_export` — append + export (baseline: full list + JSON array;
   candidate: streamed JSONL). Reports disk usage.
2. `artifact_manifest_scan` — aggregate scan (baseline: materialized; candidate: streamed).
3. `duplicate_artifact_detection` — dup shas (baseline: full count map; candidate: seen/dup sets).
4. `evidence_graph_projection` — degree distribution (baseline: adjacency lists; candidate: counters).
5. `research_plan_audit` — K/C governance-style task audit (streamed counters).
6. `bounded_cache_planning` — recency+capacity eviction (baseline: full sort; candidate: bounded heap).
7. `simulation_campaign_manifest_planning` — budget-bounded selection + batching (planning only).
8. `checkpoint_recovery_planning` — resume set + checkpoint layout.

## Benchmark schema (versioned)

`schema = "research_cycle_benchmarks/v1"`. Top level: `schema`, `schema_version`,
`evidence_class` (`performance_only`), `synthetic`, `config`
(`seed`, `size`, `repetitions`, `targets`, `max_workers`), `budgets`,
`telemetry_environment` (`platform`, `python_version`), `num_targets`, `summary`,
`all_equivalent`, `all_within_budget`, `results`, `notes`.

Each `results[]` record separates **deterministic** from **telemetry** fields:

- `target`, `status` (`ok` | `checksum_mismatch` | `malformed_record` | `error` |
  `timeout` | `child_crash` in isolated mode).
- `deterministic`: `checksum_baseline`, `checksum_candidate`, `checksum_match`,
  `feature_count`, `budget` (per-metric verdicts + `within_budget`).
- `telemetry`: `baseline`/`candidate` (`runtime_best_s`, `runtime_mean_s`,
  `tracemalloc_peak_bytes`, `rss_after_bytes`, `disk_bytes`),
  `tracemalloc_peak_ratio_candidate_over_baseline`,
  `runtime_ratio_candidate_over_baseline_advisory`.
- `confidence`, `measurement_quality`, `recommendations`, `evidence_class`, `synthetic`.

All numbers are finite or `null` (`json_safe`, `allow_nan=False`). Deterministic
fields are reproducible across runs; telemetry fields vary and are labeled as such.

## Resource budgets

Configurable `ResourceBudgets(memory_bytes, disk_bytes, runtime_s, rss_bytes)`;
each `None` disables that check. Comparison rules:

- Missing metric → `None` (unknown), never a pass-by-omission; missing metrics
  stay `null`, never `0`.
- `memory_within_budget` (tracemalloc) and `disk_within_budget` are **authoritative**.
- `runtime_within_budget` and `rss_within_budget` are **advisory** (hardware- and
  allocator-dependent).

## Usage

```bash
# In-process, all targets, human summary
python scripts/benchmark_research_cycle.py --size 256 --repetitions 3

# Finite JSON + atomic report + budgets
python scripts/benchmark_research_cycle.py --json --output out/rcb.json \
    --memory-budget-mb 8 --disk-budget-mb 4

# Child-isolated: each target in its own bounded, timed subprocess
python scripts/benchmark_research_cycle.py --isolated --per-target-timeout-s 30
```

Exit code is `0` when every target is equivalent/ok, else `1`.

## Child isolation & bounded concurrency

`--isolated` runs each target via `execute_child` in its own process group
(`shell=False`), with a hard per-target timeout and tree termination
(POSIX `SIGTERM`→`SIGKILL`; Windows `CTRL_BREAK`→`taskkill /F /T`). Execution is
strictly sequential (`max_workers = 1`) — there is no unbounded fan-out. A
timeout is recorded as `status="timeout"` (never a pass).

## Extending to real contracts

Real research-cycle contracts (when merged by their owning agents) are plugged in
via `adapters.WorkloadProtocol` — wrap the real `baseline`/`candidate` callables
in a `TargetSpec` and register alongside `TARGETS`. The core never imports them,
preserving the no-cross-agent-import guarantee.

## Limitations

- Fixtures are synthetic performance scaffolding; they exercise contract shapes,
  not real research data, and create no scientific/biological evidence.
- `tracemalloc` tracks Python-domain allocation (comparable); RSS/runtime are
  hardware-dependent (advisory) and RSS is `null` when `psutil`/`/proc` is absent.
- At small `--size`, tracemalloc ratios are noisy; a candidate whose ratio exceeds
  1.0 is surfaced in `recommendations` (the harness intentionally flags a
  "bounded" path that is not actually lower memory).
- Disk usage is reported only for targets that write an export.
```
