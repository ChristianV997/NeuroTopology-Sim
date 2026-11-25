# Batch-2 Pipeline Benchmarks

Local-only, additive harness that reproduces **engineering** causes of
all-day simulation and streaming runs using synthetic fixtures. It does
**not** modify production streaming, data-access, topology, or solver code.

- Package: `tools/benchmarks/batch2_pipeline/`
- CLI: `scripts/benchmark_batch2_pipeline.py`
- Tests: `tests/benchmarks/batch2_pipeline/`
- Makefile: `tools/benchmarks/batch2_pipeline/Makefile`

Evidence class is always `performance_only`. Missing metrics are `null`,
never fabricated `0`. Results are performance engineering measurements only;
they are not empirical or clinical claims.

## Required tooling (this environment)

The Batch-2 brief requested `/ecc:*`, `gstack`, `$coderos-operator`,
`$openai-developers:agents`, and REA. In this Cloud Agent environment those
tools are **UNAVAILABLE**. REA status: `REA_UNAVAILABLE`. Methodology follows
the in-repo `tools/benchmarking/pipeline_efficiency` pattern (measure →
compare baseline/candidate → budgets → finite JSON → isolated child).

## Targets

| Target | Baseline (waste) | Candidate (bounded) |
|---|---|---|
| `full_recording_reread` | Unpack full recording every window | Unpack once, slice windows |
| `preprocess_per_window` | Filter full recording per window | Preprocess once, slice |
| `checkpoint_fsync_overhead` | fsync after every subject | One atomic fsync at end; reports `process_work_s` vs `checkpoint_s` |
| `manifest_write_amplification` | Rewrite+fsync per item | Single batched write |
| `window_cache_hits` | Always miss on second pass | LRU cache hits |
| `subject_loop_disk_staging` | Leave `.part` siblings | Atomic `replace` without orphans |
| `worker_bound_enforcement` | Planned workers ≫ 1 | `worker_count=1` |

Baseline and candidate return the same deterministic checksum for a fixed
seed. Engineering counters (`read_counts`, `preprocess_calls`, `cache_hits`,
`manifest_writes`, `fsync_calls`, `worker_count`) are deterministic for a fixed
seed. Advisory timing (`runtime_*`, `process_work_s`, `checkpoint_s`) and
tracemalloc/RSS/disk live on the telemetry object, never inside `counters`.

## Schema

`schema = "batch2_pipeline/v1"`. Top level: `schema`, `evidence_class`
(`performance_only`), `synthetic`, `config` (`seed`, `size`, `repetitions`,
`targets`, `max_workers=1`), `budgets`, `telemetry_environment`,
`tooling_availability`, `production_probe`, `summary`, `all_equivalent`,
`all_within_budget`, `bottleneck_ranking`, `optimization_candidates`,
`results`, `notes`.

Status values: `ok`, `checksum_mismatch`, `malformed_record`, `error`,
`budget_overrun`, plus `timeout` / `child_crash` / `infrastructure_failure`
in isolated mode.

## Resource budgets

`ResourceBudgets(memory_bytes, disk_bytes, runtime_s, rss_bytes, max_workers=1)`.
`None` disables a check. Missing metric → unknown (`null`), never a
pass-by-omission. Tracemalloc, disk, and worker count are authoritative;
runtime and RSS are advisory.

## Usage

```bash
python scripts/benchmark_batch2_pipeline.py --size 16 --repetitions 1
python scripts/benchmark_batch2_pipeline.py --json --output /tmp/b2.json \
    --memory-budget-mb 64 --disk-budget-mb 16 --max-workers 1
python scripts/benchmark_batch2_pipeline.py --isolated --per-target-timeout-s 30 --size 12
python scripts/benchmark_batch2_pipeline.py generate \
    --out tools/benchmarks/batch2_pipeline/outputs --size 16 --repetitions 1
python scripts/benchmark_batch2_pipeline.py validate \
    --root tools/benchmarks/batch2_pipeline/outputs
make -C tools/benchmarks/batch2_pipeline cycle
```

## Optimization policy

The harness **does not patch production code**. `optimization_candidates` are
emitted only when measured counter deltas (reads, preprocess, fsync, manifest
writes, disk) support them. No speedup is claimed unless the advisory runtime
ratio is measured against the reproducible baseline (`measured_speedup`).

## Limitations

- Fixtures are synthetic performance scaffolding.
- `tracemalloc` is Python-domain allocation; RSS stays `null` when unavailable.
- Runtime ratios are advisory and host-dependent.
- Checkpoint timing splits process work from fsync cost on the local filesystem.
- No remote datasets, no live S3, no Awareness Studio import.
