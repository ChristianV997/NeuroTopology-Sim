# Level T Missingness and Cohort-Completeness Checks

This document describes the software behavior in `sciencer_d/btc_icft/level_t/base_real_topology.py`. These checks describe whether rows are structurally available to downstream computations. They do not verify signal provenance, participant identity, data-use rights, cohort composition, model correctness, measurement validity, or biological interpretation. `PASS` means only that the configured software completeness checks passed; it is not scientific validation or evidence promotion.

## Row-level behavior

`compute_real_topology_for_window` uses the Level M row's local source path and window bounds to request signal samples. Missing source/companion files, unreadable or partial windows, empty samples, non-finite samples, and invalid bounds produce a skipped row with `is_valid=false` and missing metrics rather than zero-filled topology values. Window bounds must be finite, non-negative, and satisfy `window_end_s > window_start_s`; missing, malformed, NaN, or infinite bounds are rejected before the signal reader is called.

`LevelTRealTopologyRow` also demotes rows with missing/non-finite metrics or invalid bounds. `None` metrics serialize as blank CSV cells. A numerical zero is distinct from a missing value in the data structure, but a zero returned by this software is not, by itself, evidence of an empirical observation or a biological effect.

The explicit `compute_fixture_topology_for_window` path generates deterministic hash-based synthetic values. Those values are test/fixture output, not signal-derived measurements. Incomplete or invalid window metadata yields an unobserved row. Rows marked with `null_method="fixture_none"` are excluded from valid cohort counts and force the cohort audit to return `INCOMPLETE`; they cannot establish empirical completeness.

## Reports and cohort checks

- `build_topology_quality_report` summarizes row validity and the configured skip rate. Its status is an engineering/data-completeness result only.
- `build_group_significance_report` and `build_ml_decoding_report` exclude invalid topology rows. If any otherwise eligible row lacks a matching Level M row or non-empty grouping value, the report returns `not_applicable` and does not analyze only the remaining subset.
- Phase, connectivity, and surrogate-null report builders keep unmatched Level T rows visible as skipped results; they do not call the signal reader for explicit hash fixtures. Empty/skipped reports use `not_applicable` and null aggregate metrics instead of claiming work was performed or emitting NaN JSON values.
- `audit_cohort_missingness` joins condition labels by `row_id`, treating missing and whitespace-only labels as absent. An unlabeled valid row or hash-based fixture prevents `PASS` and produces `INCOMPLETE` unless the skip-rate threshold takes precedence and produces `BLOCKED`. The audit also reports invalid windows, partial/failed subjects, unpaired subjects, missing expected subjects, and the configured skip-rate result. `max_skip_rate` must be finite and within `[0, 1]`.
- `cohort_missingness_report.json` is written only when a caller explicitly supplies a cohort report to `write_level_t_topology_outputs`. The current dataset pipeline entry points do not automatically call `audit_cohort_missingness` or pass this optional report.

The existing status vocabulary is preserved (`PASS`, `BLOCKED`, `INCOMPLETE`, `INSUFFICIENT_POWER`, and `EMPTY_DATASET` for the cohort audit). `PASS` is not a claim that the cohort is authentic, representative, scientifically adequate, or biologically meaningful. Missingness alone does not confirm or refute any hypothesis.

## Verification scope and limits

The focused tests use generated synthetic rows/signals, temporary marker files, and mocked signal reads; they do not require participant data. A successful test run establishes only the tested software behavior. It does not verify citations, provenance, permissions, cohort identity, model correctness, or scientific claims. The checker and reports must remain under `HOLD / SYNTHETIC_ONLY` unless separate evidence and governance gates authorize otherwise.
