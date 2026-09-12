# Post-merge pipeline measurements

Local-only harness that measures **current `origin/main` after the streaming
ingest merge** (PR #329 / integration #338). Fixtures are synthetic.
`evidence_class` is always `performance_only`. This package does not download
remote datasets, does not call AWS, does not import Awareness Studio, and does
not modify production cache, streaming, solver, or CI code.

| Item | Path |
| --- | --- |
| Package | `tools/benchmarking/post_merge_pipeline/` |
| CLI | `scripts/benchmark_post_merge_pipeline.py` |
| Tests | `tests/benchmarking/post_merge_pipeline/` |
| Makefile | `tools/benchmarking/post_merge_pipeline/Makefile` |

Missing metrics are `null`, never fabricated `0`.

## Targets

| Target | Live path (read-only) | What is measured |
| --- | --- | --- |
| `metadata_planning` | `policy_enforcement.scanner.scan_paths` | Inventory hash of synthetic sources; live AST policy scan on the candidate |
| `bounded_cache_operations` | `BoundedChunkCache.plan` (no `fetch`) | Manifest-first plan with planted local files vs an in-memory policy |
| `cache_eviction` | `BoundedChunkCache.evict` | LRU eviction of planted local chunks vs the same byte plan |
| `manifest_recovery` | `tools.streaming.base_runner.save_manifest` / `load_manifest` | Atomic fsync checkpoint plus corrupt-dest `.tmp` recovery |
| `artifact_scanning` | `simulation_artifacts.extractor.extract_run` | Lineage scan of a synthetic run directory |
| `literature_evidence_validation` | `literature_evidence.validation.validate_record` | Fail-closed identifier/status validation (no network resolve) |
| `research_cycle_smoke_execution` | `research_cycle_smoke.runner.run_smoke_suite` | Synthetic smoke scenarios vs fixture checksums |
| `release_evidence_evaluation` | `evaluate_release_evidence` + research-cycle evaluator | Decision enums vs full report materialization |

Baseline and candidate return the same deterministic checksum. Telemetry
(runtime, tracemalloc, RSS, disk, worker count, input size) is stored
separately from correctness.

## Streaming baseline comparison

Compatible probe: streaming `save_manifest` cost recorded in
`tests/performance/streaming_optimization/recorded_baseline.json` (unmodified
`55edf5c`, before fsync) versus current `manifest_recovery` on this host.

Not compared here (incompatible or would require AWS/MNE): BIDS window
preprocess timings, `list_s3_task_labels` bucket listing, preprocess
`_read_raw` reuse counts.

## Schema

`schema = "post_merge_pipeline/v1"`. Top level includes `streaming_baseline_comparison`.
Each result splits **deterministic** fields from **telemetry**. Status is one of
`ok`, `checksum_mismatch`, `malformed_record`, `error`, `budget_overrun`, plus
`timeout` / `child_crash` / `infrastructure_failure` in isolated mode.

## Usage

```bash
python scripts/benchmark_post_merge_pipeline.py --size 16 --repetitions 1
python scripts/benchmark_post_merge_pipeline.py --json --output /tmp/pmp.json
python scripts/benchmark_post_merge_pipeline.py --isolated --per-target-timeout-s 45 --size 8
python scripts/benchmark_post_merge_pipeline.py generate \
    --out tools/benchmarking/post_merge_pipeline/outputs --size 16 --repetitions 1
python scripts/benchmark_post_merge_pipeline.py validate \
    --root tools/benchmarking/post_merge_pipeline/outputs
make -C tools/benchmarking/post_merge_pipeline cycle
```

## Host run (synthetic, `performance_only`)

Recorded on this Cloud Agent host against live `origin/main`
`ed3a6f03806785ed724ef501a4aa0f41b932e805` (size=16, repetitions=1, max_workers=1).
RSS is available here; treat it as advisory. Runtime is host-dependent.
Checksums matched on all eight targets (`all_equivalent=true`). Budgets were
unset (`all_within_budget=null`).

| Target | checksum_match | candidate runtime_best_s | candidate tracemalloc_peak_bytes | candidate rss_after_bytes | candidate disk_bytes | workers | n_items |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `cache_eviction` | true | 0.011627 | 1_097_718 | 22_577_152 | 19_571 | 1 | 16 |
| `bounded_cache_operations` | true | 0.007203 | 1_067_907 | 22_446_080 | 9_665 | 1 | 16 |
| `metadata_planning` | true | 0.005036 | 85_438 | 36_835_328 | 788 | 1 | 16 |
| `research_cycle_smoke_execution` | true | 0.004118 | 123_242 | 38_354_944 | null | 1 | 4 |
| `manifest_recovery` | true | 0.003283 | 15_457 | 36_589_568 | 1_070 | 1 | 16 |
| `artifact_scanning` | true | 0.002637 | 1_082_709 | 21_876_736 | 1_893 | 1 | 16 |
| `release_evidence_evaluation` | true | 0.000594 | 17_015 | 37_249_024 | null | 1 | 16 |
| `literature_evidence_validation` | true | 0.000073 | 2_216 | 22_720_512 | null | 1 | 16 |

Baseline vs candidate (same checksum; baseline is a local fixture checksum, not a slower production path):

| Target | baseline runtime_best_s | candidate/baseline runtime (advisory) | baseline tracemalloc | candidate/baseline tm |
| --- | --- | --- | --- | --- |
| `cache_eviction` | 0.000013 | 896.88 | 1_358 | 808.33 |
| `bounded_cache_operations` | 0.000038 | 189.20 | 2_180 | 489.87 |
| `metadata_planning` | 0.001511 | 3.33 | 85_689 | 1.00 |
| `research_cycle_smoke_execution` | 0.000955 | 4.31 | 23_307 | 5.29 |
| `manifest_recovery` | 0.000508 | 6.46 | 13_106 | 1.18 |
| `artifact_scanning` | 0.001506 | 1.75 | 84_212 | 12.86 |
| `release_evidence_evaluation` | 0.001670 | 0.36 | 100_825 | 0.17 |
| `literature_evidence_validation` | 0.000031 | 2.31 | 1_789 | 1.24 |

Streaming recorded baseline (`55edf5c`, pre-fsync `save_manifest` 200 writes = 0.026994 s) vs current `manifest_recovery` 0.003283 s on this host is **not a like-for-like speedup**: the recorded probe wrote 200 manifests; this probe writes one checkpoint and recovers a corrupt dest. Ratio `0.122` is therefore not an optimization claim.

## Optimization policy

This harness **does not patch production**. `optimization_candidates` are
emitted only when a measured tracemalloc ratio > 1.15 (and peak ≥ 64 KiB), an
advisory runtime ratio > 1.25 (and ≥ 2 ms), or a live path writes a disk
footprint the baseline does not. Recommendations are engineering hypotheses
for a later dedicated patch.

Measured candidates on this host (do not patch from this PR):

1. Batch `BoundedChunkCache.register_manifest_item` / `evict()` manifest rewrites (runtime + disk; highest measured I/O).
2. Streaming or incremental `extract_run` metadata (tracemalloc peak ~1.08 MiB vs ~84 KiB fixture baseline).
3. Skip `run_smoke_suite` extra scenario-0 determinism re-run when callers already checksum fixtures.
4. Do **not** revert `save_manifest` fsync; durability is intentional after the streaming merge.

## Guardrails

No clinical claims. No ontology promotion. No proof claims. No real-data
execution. No live APIs in tests. No API keys in tests. No Q/Qabs/fdress proof
framing. No TOE or consciousness claims.
