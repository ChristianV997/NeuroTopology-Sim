# Handoff → Cursor Agent C (statistical simulations)

**From:** Cursor Agent B (estimator / synthetic failure lane)  
**Generator used:** `agent_b_minimal_independent_synthetic_v1` (**FALLBACK** — Agent A shared generator unavailable)  
**Hold:** HOLD / SYNTHETIC_ONLY — not biological validation

## What Agent C can reuse

| Artifact | Path | Use |
|---|---|---|
| Trial index + seeds | `outputs/trial_index.json` | Scenario inventory; seed disjointness |
| Per-trial arrays | `scratch/<scenario_id>.npz` | amp/phase/xy/faces (+ time series when `n_times>1`) |
| Scored matrix | `outputs/results_matrix.json` / `.csv` | Estimator×scenario×density rows |
| Benchmark table | `outputs/benchmark_table.json` | Compact panel for sims |
| Calibrated thresholds | `outputs/calibration_thresholds.json` | **Do not refit on held-out**; protocol documented |
| Contracts | `outputs/estimator_contracts.json` | Estimand definitions |
| Failure cases | `outputs/failure_cases/` | Convincing-but-wrong examples |
| Ranking | `docs/RANKING.md` | Panel vs defer |

## Outputs suitable as simulation inputs

For each trial, Agent C can treat these as **fixed estimator functionals** of synthetic fields:

1. `mean_power`, `coherence_ratio` — power baseline.
2. `mean_plv`, `mean_pli` — paired sync; PLI NaN when abstained.
3. `speed_proxy`, `direction` — wavevector proxy (high FP on non-plane fields).
4. Per-face `face_charge` with abstention mask + `net_charge` / `abs_charge`.
5. `n_components_at_threshold` — Betti-0 proxy only (defer causal use).

## Suggested statistical simulation targets

- **Calibration curves:** P(detect | has_winding_defect) vs noise / missing_frac / n_channels.
- **Type I on plane_wave & independent_noise snapshots:** winding FPR under irregular meshes.
- **PLV–PLI dissociation:** bootstrap CI for (PLV high ∧ PLI low) under common_source.
- **Sign accuracy** on analytic_triangle ±1 only (algebraic gold); separate from kNN abs_charge.
- **Abstention rate** vs amp_abstain / residual_abstain (sensitivity analysis — new cal seeds if retuning).

## Do not

- Pool densities without weights (see `aggregation_note` in summaries).
- Treat abs_charge on kNN faces as integer topological invariants.
- Infer cortical source topology from sensor-space TPR.
- Claim Agent A–compatible results until trials validate against `docs/AGENT_A_GENERATOR_INTERFACE.md`.

## Reproduce

```bash
cd /opt/cursor/artifacts/batch2_agent_b_alpha_estimators
python3 src/selftest.py
python3 src/run_benchmark.py
python3 src/dump_failure_cases.py
```

## Interface if Agent A arrives

Validate trials with `src/generator_interface.py::validate_trial_dict`, assert seed disjointness, recalibrate thresholds on Agent A calibration split only, then re-score evaluation/heldout. Flag any metric that moves substantially as **generator dependence**.
