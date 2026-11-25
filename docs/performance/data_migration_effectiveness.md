# Data-Migration Effectiveness Benchmarks

Local-only, additive harness that measures whether **bounded data-access** and
**streaming** paths improve reliability and resource use compared with a
**rejected full-object** policy baseline. Fixtures are synthetic. The harness
does not download OpenNeuro, AWS, DANDI, or any other remote data, does not
import Awareness Studio, and does not modify production cache, policy, or
streaming implementations.

- Package: `tools/benchmarking/data_migration_effectiveness/`
- CLI: `scripts/benchmark_data_migration_effectiveness.py`
- Tests: `tests/benchmarking/data_migration_effectiveness/`
- Makefile: `tools/benchmarking/data_migration_effectiveness/Makefile`

Evidence class is always `performance_only`. Missing metrics are `null`, never
fabricated `0`. Correctness (checksums) is stored separately from telemetry
(runtime, RSS, tracemalloc, disk, occupancy, eviction, retries). This document
does **not** claim scientific improvement.

## Targets

| Target | Live path (read-only) | What is measured |
|---|---|---|
| `bounded_vs_rejected_full_object` | `BoundedChunkCache.fetch` vs `DataAccessPolicy` reject | Bounded mock fetch vs rejected full-object request |
| `planning_latency` | `BoundedChunkCache.plan` | Dry-run planning latency (zero remote I/O) |
| `cache_occupancy_and_eviction` | `BoundedChunkCache.evict` | Occupancy and lease-aware LRU eviction |
| `retry_overhead` | `MockTransferAdapter.set_transient_failure` | Retry attempts after local ConnectionResetError |
| `manifest_recovery` | `tools.streaming.base_runner.load_manifest` | Corrupt dest + complete `.tmp` recovery |
| `streaming_vs_full_materialization` | `bounded_stream` vs `ndarray.copy` | Allocation of bounded stream vs in-process full copy |
| `timeout_case` | fetch with injected `TimeoutError` | Local timeout until retries exhaust |
| `corruption_case` | cached-file bit-flip then fetch | Checksum mismatch detection / recovery |
| `partial_transfer_case` | `cleanup_stale_partials` | Stale `.part.*` cleanup |
| `disk_budget_case` | `max_cache_bytes=8` | Cache-budget rejection of oversized object |

Full-object remote download is represented as a **rejected local policy
outcome**, not a remote GET. `allow_network=True` is used only with
`MockTransferAdapter` and local bytes.

## Schema

`schema = "data_migration_effectiveness/v1"`. Top level: `schema`,
`evidence_class` (`performance_only`), `synthetic`,
`scientific_improvement_claimed=false`, `network_accessed=false`,
`full_dataset_download=false`, `config` (`seed`, `size`, `repetitions`,
`targets`, `max_workers=1`), `production_available`, `summary`,
`all_checksums_match`, `regressions`, `optimization_candidates`, `results`,
`limitations`.

Each result separates **deterministic** fields from **telemetry**. Status is
one of `ok`, `checksum_mismatch`, `malformed_record`, `error`,
`budget_overrun`, `timeout`, `rejected`, plus `child_crash` /
`infrastructure_failure` in isolated mode.

`timeout_case` is expected to report `status=timeout` with matching checksums.
That is an engineering outcome, not a scientific FAIL.

## Resource budgets

`ResourceBudgets(memory_bytes, disk_bytes, runtime_s, rss_bytes)`. `None`
disables a check. Missing metric → unknown (`null`), never a pass-by-omission.
Tracemalloc and disk are authoritative when present; runtime and RSS are
advisory.

## Usage

```bash
python scripts/benchmark_data_migration_effectiveness.py --size 64 --repetitions 1
python scripts/benchmark_data_migration_effectiveness.py --json-stdout \
  --output /tmp/dme --size 64
python scripts/benchmark_data_migration_effectiveness.py --isolated \
  --per-target-timeout-s 30 --size 32
python scripts/benchmark_data_migration_effectiveness.py generate \
  --output tools/benchmarking/data_migration_effectiveness/outputs --size 64
python scripts/benchmark_data_migration_effectiveness.py validate \
  --output tools/benchmarking/data_migration_effectiveness/outputs
make -C tools/benchmarking/data_migration_effectiveness cycle
```

## Optimization policy

The harness **does not patch production code**. `optimization_candidates` are
emitted only when a measured tracemalloc ratio > 1.15 with absolute peak
≥ 64 KiB, an advisory runtime ratio > 1.25 with runtime ≥ 0.05 s, or a disk
ratio > 1.25 with footprint ≥ 4 KiB. The policy-reject vs bounded-fetch target
is excluded from those hints because the baseline is a no-op stub.
Recommendations are engineering hypotheses for a later dedicated patch, not
proof of a faster algorithm and not scientific evidence.

## Limitations

- Fixtures are synthetic performance scaffolding.
- `tracemalloc` is Python-domain allocation; RSS is host/allocator dependent
  and stays `null` when `psutil` and `/proc` are unavailable.
- Runtime ratios are advisory. Do not change production from a single-host
  sample.
- No OpenNeuro, AWS, DANDI, or other remote service is contacted.
- Checksum equivalence is the correctness gate; telemetry is not.
