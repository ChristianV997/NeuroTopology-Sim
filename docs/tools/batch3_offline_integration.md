# Batch 3 Offline Integration Harness

Status: **implemented**. Deterministic, offline fixture runner that composes
merged-main research-cycle stages into one synthetic end-to-end workflow for
**execution-order and failure-propagation** testing.

It does **not** reimplement adapters, benchmark scientific performance, download
data, install packages, execute harvested code, or run arbitrary commands from a
manifest.

Owned paths:

- `tools/batch3_offline_integration/`
- `tests/tools/batch3_offline_integration/`
- `docs/tools/batch3_offline_integration.md`
- `scripts/run_batch3_offline_integration.py`

## Related harnesses (not forked)

Audited and left alone because they solve different problems:

| Path | Purpose |
|---|---|
| `tools/release_readiness/research_cycle_smoke/` | Release-decision matrix over static stage fixtures |
| `ops/research_cycle/runner.py` | Subprocess catalog operator pack (argv allowlist) |
| `tests/integration/research_cycle/` | File-chain contract inspector |
| `tools/research_cycle_preflight/` | Single preflight gate (reused here as a stage) |
| `scripts/assemble_ecosystem_run.py` | Topology ecosystem assembly |

## Fixed allowlist (in-process callables)

1. `load_synthetic_fixture` — local fixture producer
2. `plan_quality` → `tools.research_plan_quality.rubric.evaluate_plan`
3. `claim_gate` → `tools.research_claim_gate.gate.evaluate_claim`
4. `preflight` → `tools.research_cycle_preflight.compose.run_preflight`
5. `registry_probe` → `tools.research_cycle.registry.ResearchCycleRegistry`
6. `release_evaluate` → `tools.research_cycle_release.evaluator.evaluate_research_cycle_release`
7. `optional_artifact_lineage` → `tools.simulation_artifacts.extractor.extract_run` (optional)

Missing optional upstream components are replaced only by a clearly marked
fixture substitute. The report records `missing_dependency` and
`actual_upstream_producer_ran=false`.

## Result semantics

- `evidence_class = batch3_offline_integration_engineering`
- `result_label = ENGINEERING_ONLY` (release stage may surface `SYNTHETIC_ONLY`)
- `workflow_executed_successfully` is distinct from scientific validity
- `scientific_validity_claimed` / `scientific_pass_emitted` always false
- No network, no installs, no dataset downloads

## CLI

```bash
python -m tools.batch3_offline_integration \
  --fixture-name workflow_request.json \
  --output /tmp/batch3_offline_integration_report.json

# or
python scripts/run_batch3_offline_integration.py --json-stdout
```

Exit code `0` only when required stages succeed in allowlist order.
