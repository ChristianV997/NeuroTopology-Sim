# Empirical higher-order execution harness

This runner executes a declared, local-only feature manifest. It never downloads OpenNeuro data, follows URLs, contacts a network service, or silently fabricates empirical input. Real data were not supplied as part of this implementation; local fixtures are not evidence for a scientific claim.

## Input contract

The JSON manifest uses schema `NeuroTopologySim.EmpiricalHigherOrderManifest.v1` and declares `dataset_path`, its SHA-256 `dataset_checksum`, `source_type`, complete `provenance`, and a list of recordings. Each recording explicitly identifies `subject_id`, `session_id`, `run_id`, `condition_label`, `pairing_key`, `sampling_rate_hz`, `channel_count`, finite `montage_coordinates`, `recording_quality_state`, `origin`, `feature_paths` for PSD, pairwise FC, triadic FC, and directed hypergraph features, and a binary `target_path`. Each consumed artifact (including target and timestamps) requires an `artifact_checksums` SHA-256 binding. Optional `higher_order_spectra` is classified as missing when absent. Paths must be local NPY/NPZ files contained beneath the manifest directory; URLs, absolute-outside-root, and `..` escape paths are rejected.

`channel_count` is a positive integer (a JSON boolean is not an integer for this contract). Only an explicit `recording_quality_state: PASS` is eligible for forecasting; `UNKNOWN` remains incomplete provenance and `FAIL` is invalid. Required provenance strings must be nonblank after trimming.

The validator streams each declared artifact into a private temporary snapshot while computing its SHA-256, then validates and scores from that same snapshot rather than reopening the mutable source path. It also validates identities, labels, pairing, finite values, monotonic timestamps, and feature/target row alignment. Missing respiration is reported explicitly and is never treated as observed physiology.

## Execution and safeguards

High-dimensional feature arrays are loaded one subject/session/run at a time and released before the next recording is loaded; scoring does not retain all recordings or build dataset-wide feature matrices. The runner retains one-dimensional target/prediction vectors for exact metrics, so memory for those vectors still scales with the number of scored rows. Subject-held-out and forward-time splits use training-only normalization. The harness rejects future-window timestamps, target-derived preprocessing, malformed pairing labels, non-finite JSON, synthetic empirical claims, and missing required feature artifacts. Label permutation, circular shift, block shuffle, matched-variance, and available matched-autocorrelation controls are recorded as required nulls; this contract does not calculate a Bayes factor.

The ladder reports proper scoring rules (log loss and Brier score, with AUROC/AUPRC only where both classes exist), calibration error, and incremental loss relative to the previous rung. AUROC uses average ranks for tied scores rather than constructing pairwise score matrices. AUPRC groups equal-score observations at the same threshold, so row order within a tied group cannot change average precision. A rung that does not improve held-out loss is `NO_INCREMENTAL_GAIN`; an improvement is `INCONCLUSIVE` pending independent review, never `FORMAL_FORECAST_EVIDENCE`, causation, consciousness, liberation, or biological proof.

Readiness states are `READY_FOR_DESCRIPTIVE_ANALYSIS`, `READY_FOR_FORECASTING`, `INSUFFICIENT_PAIRED_SUBJECTS`, `INCOMPLETE_PROVENANCE`, `MISSING_OPTIONAL_DEPENDENCY`, `NO_DATA`, `SYNTHETIC_DEMO_ONLY`, and `INCONCLUSIVE`. Every report includes `formal_bayes_factor: null`, `scientific_pass: false`, and `evidence_class: empirical_forecasting_runner`.
