# Migration-wave measurements

Local-only harness that compares **current `origin/main`** with migration PRs
**#331**, **#344**, **#345**, and **#346** for bounded data access, cache
eviction, and resumable streaming. Fixtures are synthetic BIDS/NWB/S3 fakes.
`evidence_class` is always `performance_only`. This package does not download
remote datasets, does not call AWS/OpenNeuro/DANDI, and does not modify
production cache, streaming, DANDI, or S3 code.

| Item | Path |
| --- | --- |
| Package | `tools/benchmarking/migration_wave/` |
| CLI | `scripts/benchmark_migration_wave.py` |
| Tests | `tests/benchmarking/migration_wave/` |
| Makefile | `tools/benchmarking/migration_wave/Makefile` |

Missing metrics are `null`, never fabricated `0`.

## Variants (read-only inspection)

| Variant | PR | State at measurement | Native planning surface |
| --- | --- | --- | --- |
| `current_main` | live `origin/main` | integrated | `fetch_ds000245.plan` when present, else `BoundedChunkCache.plan` |
| `pr_331` | #331 | open draft | `ApprovedAcquisitionAdapter.plan` |
| `pr_344` | #344 | closed, unmerged | `fetch_ds000245.plan` |
| `pr_345` | #345 | closed, unmerged | `WindowRequest.validate` |
| `pr_346` | #346 | open draft | `BoundedS3ObjectStore._head` with an in-memory fake client |

Current main already contains related bounded OpenNeuro (`60dd196`) and DANDI/NWB
(`a2b582b8`) work. #344/#345 are compared as frozen PR heads, not as “not yet
on main.” #331 and #346 are additive vs this main.

## Targets

| Target | What is measured |
| --- | --- |
| `planning_latency` | Native dry-run planning (zero remote bytes) |
| `bounded_transfer_planning` | Multi-item `BoundedChunkCache.plan` |
| `cache_occupancy` | Mock fetch occupancy and second-fetch duplicate-work flag |
| `eviction_latency` | `BoundedChunkCache.evict` on planted/mock objects |
| `retry_overhead` | `MockTransferAdapter` transient failures |
| `manifest_recovery` | Streaming atomic recovery, or S3 `.part` manifest on #346 |
| `checksum_verification` | Wrong expected checksum must fail closed |

Memory allocation, disk use, and runtime are telemetry on every target
(`tracemalloc_peak_bytes`, `disk_bytes`, `runtime_best_s`, `rss_after_bytes`).

## Failure modes

The harness and tests detect timeout, malformed child JSON, checksum mismatch
(same-surface vs current_main or injected probe), partial recovered state,
disk-budget overrun, and duplicate work (second fetch with `attempts > 0`).

## Usage

```bash
python scripts/benchmark_migration_wave.py --size 64 --repetitions 1
python scripts/benchmark_migration_wave.py generate \
    --out tools/benchmarking/migration_wave/outputs --size 64 --repetitions 1
python scripts/benchmark_migration_wave.py validate \
    --root tools/benchmarking/migration_wave/outputs
make -C tools/benchmarking/migration_wave cycle
```

Optional isolated PR roots: `--pr-331-root`, `--pr-344-root`, `--pr-345-root`,
`--pr-346-root`, or `MW_PR_331_ROOT` and siblings. Defaults look for
`/tmp/mw-pr-331` through `/tmp/mw-pr-346`.

## Optimization policy

This harness **does not patch production**. Candidates are emitted only when a
measured ratio vs `current_main` exceeds floors (tracemalloc > 1.15 and ≥ 64 KiB;
advisory runtime > 1.25 and ≥ 50 ms; disk > 1.25 and ≥ 4 KiB). Same-surface
comparisons only.

## Guardrails

No clinical claims. No ontology promotion. No proof claims. No real-data
execution. No live APIs in tests. No API keys in tests. No Q/Qabs/fdress proof
framing. No TOE or consciousness claims.
