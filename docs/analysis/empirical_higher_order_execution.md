# Empirical higher-order execution harness

This runner executes a declared, local-only feature manifest. It never downloads OpenNeuro data, follows URLs, contacts a network service, or silently fabricates empirical input. Real data were not supplied as part of this implementation; local fixtures are not evidence for a scientific claim.

## Input contract

The JSON manifest uses schema `NeuroTopologySim.EmpiricalHigherOrderManifest.v1` and declares `dataset_path`, its SHA-256 `dataset_checksum`, `source_type`, complete `provenance`, and a list of recordings. Each recording explicitly identifies `subject_id`, `session_id`, `run_id`, `condition_label`, `pairing_key`, `sampling_rate_hz`, `channel_count`, finite `montage_coordinates`, `recording_quality_state`, `origin`, `feature_paths` for PSD, pairwise FC, triadic FC, and directed hypergraph features, and a binary `target_path`. Optional `higher_order_spectra` is classified as missing when absent. Paths must be local NPY/NPZ files relative to the manifest.

The runner validates checksums, identities, labels, pairing, finite values, monotonic timestamps, and feature/target row alignment. Missing respiration is reported explicitly and is never treated as observed physiology.

## Execution and safeguards

Recordings are loaded one subject/session/run at a time. Subject-held-out and forward-time splits use training-only normalization. The harness rejects future-window timestamps, target-derived preprocessing, malformed pairing labels, non-finite JSON, synthetic empirical claims, and missing required feature artifacts. Label permutation, circular shift, block shuffle, matched-variance, and available matched-autocorrelation controls are recorded as required nulls; this contract does not calculate a Bayes factor.

The ladder reports proper scoring rules (log loss and Brier score, with AUROC/AUPRC only where both classes exist), calibration error, and incremental loss relative to the previous rung. A rung that does not improve held-out loss is `NO_INCREMENTAL_GAIN`; an improvement is forecast evidence only, never causation, consciousness, liberation, or biological proof.

Readiness states are `READY_FOR_DESCRIPTIVE_ANALYSIS`, `READY_FOR_FORECASTING`, `INSUFFICIENT_PAIRED_SUBJECTS`, `INCOMPLETE_PROVENANCE`, `MISSING_OPTIONAL_DEPENDENCY`, `NO_DATA`, `SYNTHETIC_DEMO_ONLY`, and `INCONCLUSIVE`. Every report includes `formal_bayes_factor: null`, `scientific_pass: false`, and `evidence_class: empirical_forecasting_runner`.
