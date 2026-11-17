# Missingness and Cohort Completeness Gates

## Overview

In EEG/MEG topology extraction (`sciencer_d/btc_icft/level_t/base_real_topology.py`), missing source files, missing multi-file format companions (e.g., BrainVision `.eeg` or `.vmrk` alongside `.vhdr`), out-of-range windows, or unreadable channels must **never** be silently imputed as zero-valued topology observations (`0.0`). Silent zero imputation creates artificial zero-charge observations (`q_net=0.0`, `q_abs=0.0`, `f_dress=0.0`) that bias downstream permutation tests and inflate sample sizes.

## Key Safeguards

- **No Silent Zero Imputation**: Missing or unreadable windows return `None` for all topology metric fields (`q_net`, `q_abs`, `f_dress`, `defect_density`, `topology_quality`) and serialize as empty strings (`""`) in `features_t.csv`. Genuine zero-valued observations (`0.0`) are preserved when computed from valid signal channels.
- **Explicit Missingness Schema**: `LevelTRealTopologyRow` explicitly tracks `topology_status` (`computed` | `skipped`), `missingness_state` (`computed` | `missing_source_file` | `missing_companion_file` | `failed_read` | `partial_run` | `unobserved`), `missingness_reason`, `is_valid` (`bool`), `run_status` (`complete` | `partial` | `failed`), and `replicate_count`. Missing-source rows use `missing_source_file`, have `None` metric fields, `is_valid=False`, `topology_status="skipped"`, `run_status="failed"`, and `replicate_count=0`. Rows with boolean, out-of-range, or non-finite metrics/bounds or inconsistent triangle counts (`n_valid_triangles > n_triangles` or negative counts) are demoted to `is_valid=False`, `topology_status="skipped"`, `missingness_state="unobserved"`, and `run_status="failed"`.
- **Cohort Missingness Gate (`audit_cohort_missingness`)**:
  - Fails closed (`BLOCKED`) when window skip rate exceeds `max_skip_rate` (default `0.20`).
  - Fails closed (`INSUFFICIENT_POWER`) when paired subject count in a 2-condition cohort falls below `min_paired_subjects` (default `5`).
  - Fails closed (`INCOMPLETE`) when any expected subject, companion file, condition label, or window is missing, when synthetic fixture rows (`null_method="fixture_none"`) are present, or when joined condition/subject metadata is contradictory across Level T and Level M rows.
  - Passes (`PASS`) only when all included windows, companion files, conditions, and subjects are complete, consistent, and valid.
- **Downstream eligibility**: `build_topology_quality_report`, `build_group_significance_report`, `build_ml_decoding_report`, and the row-aligned optional signal reports (`build_phase_based_topology_report`, `build_connectivity_report`, `build_null_gate_report`) exclude invalid, warning-bearing, non-finite, synthetic fixture, and incomplete-status rows (`run_status` other than `complete`, `missingness_state` other than `computed`, or `replicate_count <= 0`) from valid metric evidence. Group, ML, and cohort gates fail closed on missing or contradictory grouping metadata. Exclusions remain visible in per-report skip/exclusion counts; the cohort audit also lists row-level details in `missing_records`. Missing metrics are never zero-filled.
- **Artifact alignment diagnostic**: `build_artifact_alignment_report` preserves matched Level M `artifact_score` metadata even when its paired Level T row is invalid, because that score is a separate diagnostic input. Its Level T topology-quality summary uses only eligible rows and lists ineligible topology rows in `missing_topology_rows`; a retained artifact score is not a valid topology observation.

## Verification

```bash
pytest tests/test_base_real_topology_missingness.py tests/test_cohort_missingness.py -q
```
