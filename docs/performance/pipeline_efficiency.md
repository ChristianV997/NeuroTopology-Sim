# Pipeline Efficiency Benchmarks

Local-only, additive harness for **performance evidence** on research-cycle,
bounded-cache planning, artifact-lineage scanning, and simulation-planning
paths. Fixtures are synthetic. The harness does not download OpenNeuro, AWS,
DANDI, or any other remote data, does not import Awareness Studio, and does
not modify production simulation, cache, or ledger implementations.

- Package: `tools/benchmarking/pipeline_efficiency/`
- CLI: `scripts/benchmark_pipeline_efficiency.py`
- Tests: `tests/benchmarking/pipeline_efficiency/`
- Makefile: `tools/benchmarking/pipeline_efficiency/Makefile`

Evidence class is always `performance_only`. Missing metrics are `null`, never
fabricated `0`.

## Targets

| Target | Live path (read-only) | What is measured |
|---|---|---|
| `manifest_planning` | `tools.integration_bridge.artifact_manifest.build_manifest` | Explicit-list hashing vs a naive materializing hash |
| `bounded_cache_planning` | `BoundedChunkCache.plan` (no `fetch`) | Dry-run eviction/capacity planning vs an in-memory policy |
| `artifact_manifest_scanning` | `tools.simulation_artifacts.extractor.extract_run` | Lineage scan of a synthetic run directory |
| `duplicate_detection` | `extract_run` duplicate_content | Duplicate SHA-256 groups |
| `evidence_graph_projection` | `tools.research_record.graph.recommended_merge_order` | Merge-order projection (not Awareness Studio) |
| `release_evidence_evaluation` | `evaluate_release_evidence` + research-cycle evaluator | Decision-enum collection vs full report materialization |
| `checkpoint_recovery_planning` | `compute_configuration_hash` plus resume-set planning | Config hash + todo/checkpoint layout |
| `simulation_runner_overhead` | `tools.streaming.process_runner.run_one` | Child-isolation overhead of a trivial local child |

Baseline and candidate return the same deterministic checksum. Telemetry
(runtime, tracemalloc, RSS, disk) is stored separately.

## Schema

`schema = "pipeline_efficiency/v1"`. Top level: `schema`, `evidence_class`
(`performance_only`), `synthetic`, `config` (`seed`, `size`, `repetitions`,
`targets`, `max_workers=1`), `budgets`, `telemetry_environment`,
`production_probe`, `summary`, `all_equivalent`, `all_within_budget`,
`bottleneck_ranking`, `optimization_candidates`, `results`, `notes`.

Each result separates **deterministic** fields from **telemetry**. Status is
one of `ok`, `checksum_mismatch`, `malformed_record`, `error`,
`budget_overrun`, plus `timeout` / `child_crash` / `infrastructure_failure` in
isolated mode.

## Resource budgets

`ResourceBudgets(memory_bytes, disk_bytes, runtime_s, rss_bytes)`. `None`
disables a check. Missing metric → unknown (`null`), never a pass-by-omission.
Tracemalloc and disk are authoritative; runtime and RSS are advisory.

## Usage

```bash
python scripts/benchmark_pipeline_efficiency.py --size 24 --repetitions 1
python scripts/benchmark_pipeline_efficiency.py --json --output /tmp/pe.json \
    --memory-budget-mb 64 --disk-budget-mb 16
python scripts/benchmark_pipeline_efficiency.py --isolated --per-target-timeout-s 30 --size 16
python scripts/benchmark_pipeline_efficiency.py generate \
    --out tools/benchmarking/pipeline_efficiency/outputs --size 24 --repetitions 1
python scripts/benchmark_pipeline_efficiency.py validate \
    --root tools/benchmarking/pipeline_efficiency/outputs
make -C tools/benchmarking/pipeline_efficiency cycle
```

## Optimization policy

The harness **does not patch production code**. `optimization_candidates` are
emitted only when a measured tracemalloc ratio > 1.15, an advisory runtime
ratio > 1.25, or a live path writes a disk footprint the baseline does not.
Recommendations are engineering hypotheses for a later dedicated patch, not
proof of a faster algorithm and not scientific evidence.

## Limitations

- Fixtures are synthetic performance scaffolding.
- `tracemalloc` is Python-domain allocation; RSS is host/allocator dependent
  and stays `null` when `psutil` and `/proc` are unavailable.
- Runtime ratios are advisory. Do not change production from a single-host
  sample.
- `BoundedChunkCache.plan` is exercised with `MockTransferAdapter` and
  `file:///local/synthetic/...` URIs. `fetch` is never called.
- Simulation-runner overhead uses a trivial local child, not a solver.
