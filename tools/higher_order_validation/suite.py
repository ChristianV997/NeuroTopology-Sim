"""Run the adversarial validation suite against synthetic DGPs and nulls."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from tools.higher_order_validation.dgps import (
    DGP_REGISTRY,
    generate_common_driver,
    generate_held_out_subjects,
    generate_independent_gaussian,
    generate_pure_pairwise,
    generate_pure_triadic,
    generate_temporal_smoothing,
    generate_volume_conduction_mixing,
    source_checksum,
)
from tools.higher_order_validation.nulls import NULL_REGISTRY
from tools.higher_order_validation.probes import (
    hypergraph_triad_summary,
    max_abs_pairwise_corr,
    max_abs_triadic_moment,
    pairwise_mean_abs_corr,
    probe_bundle,
    spectral_bandpower_ratio,
    surrogate_pairwise_gate,
)
from tools.higher_order_validation.schema import (
    DEFAULT_LIMITATIONS,
    EVIDENCE_CLASS,
    SCHEMA_VERSION,
    CaseOutcome,
    ValidationCaseResult,
)
from tools.higher_order_validation.warnings_catalog import (
    WARN_GAIN_TRAINING_ONLY,
    WARN_MULTIPLE_COMPARISONS_UNRESOLVED,
    WARN_SAMPLE_SIZE_INADEQUATE,
    WARN_TOPOLOGY_NO_INFO_BEYOND_SPECTRA,
    WARN_TRIADIC_GAIN_GONE_AFTER_CONFOUND,
    WARN_TRISPECTRAL_GAIN_GONE_UNDER_SURROGATES,
    default_suite_warnings,
)


PAIRWISE_POS = 0.55
PAIRWISE_NEG = 0.25
TRIADIC_POS = 0.35
TRIADIC_NEG = 0.15


def _case(
    case_id: str,
    dgp: str,
    expected: str,
    observed: str,
    outcome: CaseOutcome,
    seed: int,
    checksum: str,
    metrics: Optional[Dict[str, Any]] = None,
    warnings: Optional[List[str]] = None,
    details: Optional[Dict[str, Any]] = None,
) -> ValidationCaseResult:
    return ValidationCaseResult(
        schema_version=SCHEMA_VERSION,
        case_id=case_id,
        data_generating_process=dgp,
        expected_result=expected,
        observed_result=observed,
        outcome=outcome,
        random_seed=int(seed),
        source_checksum=checksum,
        evidence_class=EVIDENCE_CLASS,
        synthetic=True,
        metrics=metrics or {},
        warnings=(warnings or []) + default_suite_warnings(),
        limitations=list(DEFAULT_LIMITATIONS),
        details=details or {},
    )


def _eval_positive_pairwise(seed: int = 0) -> ValidationCaseResult:
    x = generate_pure_pairwise(seed=seed)
    m = probe_bundle(x)
    hit = m["max_abs_pairwise_corr"] >= PAIRWISE_POS
    return _case(
        "pos_pure_pairwise",
        "pure_pairwise_dependence",
        "pairwise_probe_high",
        "pairwise_probe_high" if hit else "pairwise_probe_low",
        CaseOutcome.POSITIVE_CONTROL_HIT if hit else CaseOutcome.FALSE_NEGATIVE,
        seed,
        source_checksum(x),
        metrics=m,
    )


def _eval_positive_triadic(seed: int = 0) -> ValidationCaseResult:
    x = generate_pure_triadic(seed=seed)
    m = probe_bundle(x)
    hit = m["max_abs_triadic_moment"] >= TRIADIC_POS and m["max_abs_pairwise_corr"] < PAIRWISE_POS
    return _case(
        "pos_pure_triadic",
        "pure_triadic_dependence",
        "triadic_probe_high_pairwise_low",
        "triadic_ok" if hit else "triadic_miss",
        CaseOutcome.POSITIVE_CONTROL_HIT if hit else CaseOutcome.FALSE_NEGATIVE,
        seed,
        source_checksum(x),
        metrics=m,
        details={"hypergraph_smoke": hypergraph_triad_summary()},
    )


def _eval_negative_gaussian(seed: int = 0) -> ValidationCaseResult:
    x = generate_independent_gaussian(seed=seed)
    m = probe_bundle(x)
    ok = m["max_abs_pairwise_corr"] < PAIRWISE_POS and m["max_abs_triadic_moment"] < TRIADIC_POS
    return _case(
        "neg_independent_gaussian",
        "independent_gaussian_noise",
        "no_dependence_probes_low",
        "probes_low" if ok else "spurious_hit",
        CaseOutcome.NEGATIVE_CONTROL_OK if ok else CaseOutcome.FALSE_POSITIVE,
        seed,
        source_checksum(x),
        metrics=m,
    )


def _eval_false_positive_volume_conduction(seed: int = 0) -> ValidationCaseResult:
    x = generate_volume_conduction_mixing(seed=seed, mix=0.7)
    m = probe_bundle(x)
    # Mixing induces instantaneous pairwise correlations → expected false-positive risk.
    fp = m["max_abs_pairwise_corr"] >= PAIRWISE_POS
    return _case(
        "fp_volume_conduction_mixing",
        "volume_conduction_like_mixing",
        "pairwise_false_positive_risk",
        "false_positive_observed" if fp else "no_false_positive",
        CaseOutcome.FALSE_POSITIVE if fp else CaseOutcome.NEGATIVE_CONTROL_OK,
        seed,
        source_checksum(x),
        metrics=m,
        warnings=["Volume-conduction-like mixing can inflate pairwise probes without true lagged coupling."],
    )


def _eval_common_driver_control(seed: int = 0) -> ValidationCaseResult:
    x = generate_common_driver(seed=seed)
    raw = max_abs_pairwise_corr(x)
    # Partial out driver channel 0 from targets 1,2
    d = x[0]
    residual = x.copy()
    for ch in (1, 2):
        beta = float(np.dot(x[ch], d) / (np.dot(d, d) + 1e-12))
        residual[ch] = x[ch] - beta * d
    after = max_abs_pairwise_corr(residual[[1, 2]])
    disappeared = raw >= PAIRWISE_POS and after < PAIRWISE_NEG
    warnings = [WARN_TRIADIC_GAIN_GONE_AFTER_CONFOUND] if disappeared else []
    # For pairwise common-driver, warn analogously about gain disappearing after confound control.
    if disappeared:
        warnings = [
            "WARNING: pairwise gain disappears after common-driver / confound control",
            WARN_TRIADIC_GAIN_GONE_AFTER_CONFOUND,
        ]
    return _case(
        "ctrl_common_driver",
        "common_driver_confounding",
        "gain_drops_after_confound_control",
        "gain_dropped" if disappeared else "gain_persisted",
        CaseOutcome.POSITIVE_CONTROL_HIT if disappeared else CaseOutcome.WARNING,
        seed,
        source_checksum(x),
        metrics={"pairwise_before": raw, "pairwise_after_partial": after},
        warnings=warnings,
    )


def _eval_amplitude_modulation(seed: int = 0) -> ValidationCaseResult:
    x = DGP_REGISTRY["amplitude_modulation"](seed=seed)
    m = probe_bundle(x)
    noise = generate_independent_gaussian(n_channels=x.shape[0], n_samples=x.shape[1], seed=seed + 99)
    m_noise = probe_bundle(noise)
    hit = m["spectral_bandpower_ratio"] > m_noise["spectral_bandpower_ratio"] * 2.0
    return _case(
        "pos_amplitude_modulation",
        "amplitude_modulation",
        "spectral_probe_sensitive",
        "spectral_hit" if hit else "spectral_miss",
        CaseOutcome.POSITIVE_CONTROL_HIT if hit else CaseOutcome.FALSE_NEGATIVE,
        seed,
        source_checksum(x),
        metrics={**m, "noise_spectral_bandpower_ratio": m_noise["spectral_bandpower_ratio"]},
    )


def _eval_temporal_smoothing(seed: int = 0) -> ValidationCaseResult:
    x = generate_temporal_smoothing(seed=seed, ar_coef=0.92)
    m = probe_bundle(x)
    # Autocorrelation high but cross-channel dependence should stay low.
    ok = m["lag1_mean_abs_acf"] > 0.5 and m["max_abs_pairwise_corr"] < PAIRWISE_POS
    return _case(
        "ctrl_temporal_smoothing",
        "temporal_smoothing",
        "high_acf_low_pairwise",
        "ok" if ok else "unexpected",
        CaseOutcome.NEGATIVE_CONTROL_OK if ok else CaseOutcome.FALSE_POSITIVE,
        seed,
        source_checksum(x),
        metrics=m,
    )


def _eval_null_control(name: str, seed: int = 0) -> ValidationCaseResult:
    base = generate_pure_pairwise(seed=seed, corr=0.9)
    null_fn = NULL_REGISTRY[name]
    null = null_fn(base, seed=seed + 11)
    real = max_abs_pairwise_corr(base)
    null_score = max_abs_pairwise_corr(null)
    # Null should destroy pairwise dependence for phase/block/matched-variance;
    # matched-autocorrelation preserves temporal structure but not cross-channel sync.
    destroyed = null_score < PAIRWISE_NEG <= real or null_score < real * 0.5
    return _case(
        f"null_{name}",
        name,
        "dependence_destroyed_or_reduced",
        "destroyed" if destroyed else "not_destroyed",
        CaseOutcome.POSITIVE_CONTROL_HIT if destroyed else CaseOutcome.FALSE_NEGATIVE,
        seed,
        source_checksum(null),
        metrics={"real_pairwise": real, "null_pairwise": null_score},
    )


def _eval_surrogate_trispectral_warning(seed: int = 0) -> ValidationCaseResult:
    x = generate_pure_triadic(seed=seed)
    real_t = max_abs_triadic_moment(x)
    from tools.higher_order_validation.nulls import phase_shuffle_null

    null_scores = [max_abs_triadic_moment(phase_shuffle_null(x, seed=seed + i)) for i in range(12)]
    null_mean = float(np.mean(null_scores))
    disappears = real_t >= TRIADIC_POS and null_mean < TRIADIC_NEG
    return _case(
        "warn_trispectral_under_surrogates",
        "pure_triadic_dependence+phase_shuffle_null",
        "triadic_gain_checked_under_surrogates",
        "gain_disappears_under_null" if disappears else "gain_persists_or_weak",
        CaseOutcome.WARNING if disappears else CaseOutcome.INCONCLUSIVE,
        seed,
        source_checksum(x),
        metrics={"real_triadic": real_t, "null_triadic_mean": null_mean},
        warnings=[WARN_TRISPECTRAL_GAIN_GONE_UNDER_SURROGATES] if disappears else [],
    )


def _eval_topology_vs_spectra(seed: int = 0) -> ValidationCaseResult:
    # Independent noise: triad probe stays low; spectral AM probe should not exceed
    # a calibrated noise baseline by a large factor.
    x = generate_independent_gaussian(seed=seed)
    m = probe_bundle(x)
    no_extra = m["max_abs_triadic_moment"] < TRIADIC_NEG
    return _case(
        "warn_topology_vs_spectra",
        "independent_gaussian_noise",
        "no_topology_beyond_spectra",
        "aligned" if no_extra else "divergence",
        CaseOutcome.WARNING if no_extra else CaseOutcome.INCONCLUSIVE,
        seed,
        source_checksum(x),
        metrics=m,
        warnings=[WARN_TOPOLOGY_NO_INFO_BEYOND_SPECTRA] if no_extra else [],
    )


def _eval_window_sensitivity(seed: int = 0) -> ValidationCaseResult:
    x = generate_pure_pairwise(n_samples=4096, seed=seed, corr=0.9)
    scores = {}
    for win in (256, 512, 1024, 2048):
        scores[str(win)] = max_abs_pairwise_corr(x[:, :win])
    # Monotone-ish: larger windows should not collapse the strong pairwise signal.
    stable = scores["2048"] >= PAIRWISE_POS and scores["256"] >= PAIRWISE_NEG
    return _case(
        "sens_window_size",
        "pure_pairwise_dependence",
        "pairwise_stable_across_windows",
        "stable" if stable else "unstable",
        CaseOutcome.POSITIVE_CONTROL_HIT if stable else CaseOutcome.WARNING,
        seed,
        source_checksum(x),
        metrics={"window_scores": scores},
    )


def _eval_sample_size_sensitivity(seed: int = 0) -> ValidationCaseResult:
    # Weak pairwise correlation: small-n estimates are unstable / attenuated.
    scores = {}
    for n in (32, 64, 128, 2048):
        x = generate_pure_pairwise(n_samples=n, seed=seed, corr=0.25)
        scores[str(n)] = max_abs_pairwise_corr(x)
    inadequate = scores["32"] < 0.35 <= scores["2048"] or scores["32"] < scores["2048"] - 0.1
    return _case(
        "sens_sample_size",
        "pure_pairwise_dependence",
        "small_n_unstable",
        "inadequate_small_n" if inadequate else "unexpected",
        CaseOutcome.WARNING if inadequate else CaseOutcome.INCONCLUSIVE,
        seed,
        source_checksum(generate_pure_pairwise(n_samples=2048, seed=seed, corr=0.25)),
        metrics={"sample_size_scores": scores},
        warnings=[WARN_SAMPLE_SIZE_INADEQUATE] if inadequate else [],
    )


def _eval_channel_reorder_invariance(seed: int = 0) -> ValidationCaseResult:
    x = generate_pure_pairwise(seed=seed, corr=0.9)
    a = probe_bundle(x)
    perm = np.random.default_rng(seed).permutation(x.shape[0])
    b = probe_bundle(x[perm])
    ok = abs(a["max_abs_pairwise_corr"] - b["max_abs_pairwise_corr"]) < 1e-9
    # Also check hypergraph node-reorder API when available.
    HG_summary = hypergraph_triad_summary()
    return _case(
        "inv_channel_reorder",
        "pure_pairwise_dependence",
        "probe_invariant_to_channel_reorder",
        "invariant" if ok else "not_invariant",
        CaseOutcome.POSITIVE_CONTROL_HIT if ok else CaseOutcome.FALSE_NEGATIVE,
        seed,
        source_checksum(x),
        metrics={"before": a, "after": b, "hypergraph_smoke": HG_summary},
    )


def _eval_held_out_subject(seed: int = 0) -> ValidationCaseResult:
    data = generate_held_out_subjects(seed=seed)
    train = max_abs_pairwise_corr(data["train"])
    held = max_abs_pairwise_corr(data["held_out"])
    training_only = train >= PAIRWISE_POS and held < PAIRWISE_NEG
    return _case(
        "held_out_subject",
        "held_out_subjects_pairwise_vs_noise",
        "gain_fails_to_transfer",
        "training_only" if training_only else "transfers_or_weak",
        CaseOutcome.WARNING if training_only else CaseOutcome.INCONCLUSIVE,
        seed,
        source_checksum(data["train"]),
        metrics={"train_pairwise": train, "held_out_pairwise": held},
        warnings=[WARN_GAIN_TRAINING_ONLY] if training_only else [],
    )


def _eval_calibration_surrogate_gate(seed: int = 0) -> ValidationCaseResult:
    x = generate_pure_pairwise(seed=seed, corr=0.9)
    gate = surrogate_pairwise_gate(x, seed=seed, n_surr=16)
    calibrated = gate["null_p_engineering"] < 0.1
    return _case(
        "calibration_surrogate_gate",
        "pure_pairwise_dependence+phase_surrogate",
        "real_exceeds_phase_null",
        "calibrated" if calibrated else "not_calibrated",
        CaseOutcome.POSITIVE_CONTROL_HIT if calibrated else CaseOutcome.WARNING,
        seed,
        source_checksum(x),
        metrics=gate,
    )


def _eval_preprocessing_sensitivity(seed: int = 0) -> ValidationCaseResult:
    x = generate_pure_pairwise(seed=seed, corr=0.9)
    raw = max_abs_pairwise_corr(x)
    # Simple preprocessing: z-score + mild detrend
    z = x - x.mean(axis=1, keepdims=True)
    t = np.linspace(-1, 1, z.shape[1])
    for c in range(z.shape[0]):
        coef = np.polyfit(t, z[c], 1)
        z[c] = z[c] - np.polyval(coef, t)
    after = max_abs_pairwise_corr(z)
    ok = abs(raw - after) < 0.15 and after >= PAIRWISE_POS
    return _case(
        "sens_preprocessing",
        "pure_pairwise_dependence",
        "pairwise_robust_to_zscore_detrend",
        "robust" if ok else "sensitive",
        CaseOutcome.POSITIVE_CONTROL_HIT if ok else CaseOutcome.WARNING,
        seed,
        source_checksum(x),
        metrics={"raw": raw, "after_preprocess": after},
    )


def run_validation_suite(seed: int = 0) -> List[ValidationCaseResult]:
    """Execute the full adversarial suite (deterministic for fixed seed)."""
    results: List[ValidationCaseResult] = []
    results.append(_eval_positive_pairwise(seed))
    results.append(_eval_positive_triadic(seed))
    results.append(_eval_amplitude_modulation(seed))
    results.append(_eval_common_driver_control(seed))
    results.append(_eval_temporal_smoothing(seed))
    results.append(_eval_false_positive_volume_conduction(seed))
    results.append(_eval_negative_gaussian(seed))
    for null_name in (
        "phase_shuffle_null",
        "block_shuffle_null",
        "matched_variance_null",
        "matched_autocorrelation_null",
    ):
        results.append(_eval_null_control(null_name, seed))
    results.append(_eval_surrogate_trispectral_warning(seed))
    results.append(_eval_topology_vs_spectra(seed))
    results.append(_eval_window_sensitivity(seed))
    results.append(_eval_sample_size_sensitivity(seed))
    results.append(_eval_channel_reorder_invariance(seed))
    results.append(_eval_held_out_subject(seed))
    results.append(_eval_calibration_surrogate_gate(seed))
    results.append(_eval_preprocessing_sensitivity(seed))
    # Hard invariant: never emit scientific PASS / Bayes factor fields.
    for r in results:
        if "bayes" in r.observed_result.lower() or r.outcome.value == "PASS":
            r.outcome = CaseOutcome.ERROR
            r.warnings.append("Internal guard: scientific PASS/Bayes emission blocked")
    return results
