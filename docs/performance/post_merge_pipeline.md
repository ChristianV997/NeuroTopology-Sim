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

## Optimization policy

This harness **does not patch production**. `optimization_candidates` are
emitted only when a measured tracemalloc ratio > 1.15 (and peak ≥ 64 KiB), an
advisory runtime ratio > 1.25 (and ≥ 2 ms), or a live path writes a disk
footprint the baseline does not. Recommendations are engineering hypotheses
for a later dedicated patch.

## Guardrails

No clinical claims. No ontology promotion. No proof claims. No real-data
execution. No live APIs in tests. No API keys in tests. No Q/Qabs/fdress proof
framing. No TOE or consciousness claims.
