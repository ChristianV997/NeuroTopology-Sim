# SU(2)/Skyrme experiment runner

Reproducible **experiment orchestration** for the SU(2)/Skyrme solver lane.

This package owns:

- config schema + validation
- provenance (seed, config hash, git revision, discretization, BCs, IC, model/solver settings)
- result contract (units/dimensionless, missing-data, failure/convergence, epistemic tags)
- thin solver adapter
- single-run and parameter-grid runners
- smoke configs and tests

This package does **not** own:

- Skyrme / SU(2) energy, gradient, charge, or evolution mathematics
- visualization UI
- consciousness, awareness, or biological claims

## Layout

| Path | Role |
|---|---|
| `schema.py` | Config validation (`su2_skyrme.experiment.config.v1`) |
| `provenance.py` | Seed / config hash / git revision capture |
| `result_contract.py` | Result envelope + epistemic tags |
| `adapter.py` | Optional import of `field_theory.su2` |
| `runner.py` | `run_single` / `run_grid` / `run_experiment` |
| `configs/` | Smoke single + grid configs |
| `__main__.py` | CLI entry |

## Quick start

```bash
# From repo root
python -m experiments.su2_skyrme --config experiments/su2_skyrme/configs/smoke_single.yaml

python -m experiments.su2_skyrme --config experiments/su2_skyrme/configs/smoke_grid.yaml
```

Artifacts land under `outputs/experiments/su2_skyrme/<run_id>/`:

- `config.canonical.json`
- `provenance.json`
- `result.json`
- `viz_handoff.json` (handoff only; no UI)
- `adapter_raw.json`
- for grids: `points_manifest.json` and `points/<point_run_id>/`

Large binary / trajectory dumps should stay under `outputs/experiments/su2_skyrme/` (gitignored).

## Solver availability

On bases where `field_theory.su2` is not present (including the missingness cohort base), the adapter resolves to `unavailable_stub` and labels diagnostics `availability: unavailable` instead of inventing numbers. Status becomes `completed_with_unavailable_solver`.

When `field_theory.su2.nearest_neighbor.relax_skyrme_field_nearest_neighbor` is importable, `solver.backend: auto` uses that backend and records computed diagnostics with epistemic tag `computed`.

`constrained_pair` and `lorentzian` backends are detected but not fabricated here; the runner records unavailability with an explicit reason so solver-owned IC/geometry remain outside this lane.

## Result contract highlights

- `units` default to `dimensionless`; physical conversion is `not_assessed`
- `missing_data` lists unavailable diagnostic keys
- `convergence.convergence_claim` is always `NOT_ESTABLISHED` at the runner layer
- `consciousness_score` is always `null`; `consciousness_implication` is always `none`
- every diagnostic carries `availability` + `epistemic_tag` ∈ `{computed, assumed, speculative}`

## Viz handoff

`viz_handoff.json` tells a separate visualization contributor where to find `result.json`. This runner never opens a UI.

## Tests

```bash
pytest tests/experiments/test_su2_skyrme_smoke.py \
       tests/experiments/test_su2_skyrme_replay.py \
       tests/experiments/test_su2_skyrme_invalid_config.py -q
```

## Guardrails

- No clinical / consciousness / TOE / proof framing
- No solver-math duplication
- No live APIs in tests
- No edits to PR #466 / #468 solver branches from this lane
