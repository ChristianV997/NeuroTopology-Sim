# Higher-Order Adversarial Validation

Engineering adversarial suite for the integrated higher-order signal stack.
Uses synthetic data-generating processes (DGPs) and nulls to exercise positive
controls, negative controls, false-positive risks, sensitivity checks, and
explicit warnings.

> **Scientific-integrity note.** This is **engineering evidence**, not empirical
> neuroscience. The suite **never** emits a scientific `PASS` or a formal Bayes
> factor. Synthetic DGPs do not confirm biology, consciousness, or mechanism.

| Artifact | Path |
| --- | --- |
| Package | `tools/higher_order_validation/` |
| CLI | `scripts/run_higher_order_validation.py` |
| Tests | `tests/higher_order_validation/` |

Higher-order feature / forecasting / null-calibration / Bayesian falsification
implementations are **read-only**. This suite soft-imports
`topo_monitor.higher_order` and `validation.surrogate_testing` when present.

## Data-generating processes

- `pure_pairwise_dependence`
- `pure_triadic_dependence`
- `amplitude_modulation`
- `common_driver_confounding`
- `temporal_smoothing`
- `volume_conduction_like_mixing`
- `independent_gaussian_noise`
- held-out subject pair (train pairwise / held-out noise)

## Null controls

- `phase_shuffle_null`
- `block_shuffle_null`
- `matched_variance_null`
- `matched_autocorrelation_null`

## Validation coverage

Positive/negative controls, false positives (volume conduction), preprocessing /
window / sample-size sensitivity, channel-reorder invariance, common-driver
control, held-out subject behavior, and surrogate calibration.

## Explicit warnings

- Triadic (or pairwise) gain disappears after confound control
- Trispectral / higher-order gain disappears under surrogates
- Topology adds no information beyond spectra (under noise controls)
- Gain is training-only (held-out failure)
- Sample size inadequate
- Multiple comparisons unresolved

## JSON schema (`1.0`)

Each case includes: `schema_version`, `data_generating_process`,
`expected_result`, `observed_result`, `random_seed`, `source_checksum`,
`evidence_class` (`engineering_adversarial_synthetic`), `synthetic=true`,
`limitations`, plus metrics/warnings. Suite rollups set
`scientific_pass_emitted=false` and `formal_bayes_factor_emitted=false`.

## CLI

```bash
PYTHONPATH=. python scripts/run_higher_order_validation.py \
  --seed 0 --output artifacts/higher_order_validation
```

## Scientific limitations

- Probes are engineering heuristics (Pearson / third-order moment / bandpower),
  not validated scientific estimators of triadic connectivity or trispectra.
- Surrogate counts in the suite are small by design for CI speed.
- Multiple-comparison corrections are unresolved by default.
- No path from this suite to empirical scientific PASS.
