"""Fail-closed evidence contracts for the exploratory PITNN comparison.

The historical implementation compared RSS values and called the resulting
ratio a Bayes factor. That quantity is retained as a compatibility field,
but is now explicitly labelled a proxy. A PASS verdict is intentionally
unavailable to proxy comparisons: it requires formal marginal-likelihood
evidence plus empirical provenance and declared controls.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np


PASS_THRESHOLD = 100.0
MIN_EFFECTIVE_SAMPLE_COUNT = 8
TOPOLOGY_METRICS = ("graph_beta1", "spatial_winding_q", "scalar_chirality")


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _finite_or_zero(value: Any) -> float:
    result = _finite(value)
    return 0.0 if result is None else result


def _normalise_mode(data_mode: Any) -> str:
    value = str(data_mode or "unknown").strip().lower()
    if value.startswith(("synthetic", "fixture", "null", "surrogate")):
        return "synthetic"
    if value.startswith(("empirical", "observed", "real", "local")):
        return "empirical"
    return value or "unknown"


def _fit_linear(y: np.ndarray, design: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    return design @ beta, beta


def _fit_l1(y: np.ndarray, design: np.ndarray, penalty: float, iterations: int = 2000) -> tuple[np.ndarray, np.ndarray]:
    """Coordinate-descent L1 fit; intercept is the first unpenalized column."""
    if penalty < 0 or not np.isfinite(penalty):
        raise ValueError("l1 penalty must be finite and non-negative")
    x = np.asarray(design, float)
    beta = np.zeros(x.shape[1])
    beta[0] = float(np.mean(y))
    scale = np.sqrt(np.sum(x[:, 1:] ** 2, axis=0))
    scale[scale == 0] = 1.0
    xs = x.copy()
    xs[:, 1:] /= scale
    for _ in range(iterations):
        previous = beta.copy()
        beta[0] = float(np.mean(y - xs[:, 1:] @ beta[1:]))
        for column in range(1, xs.shape[1]):
            residual = y - xs @ beta + xs[:, column] * beta[column]
            rho = float(xs[:, column] @ residual)
            norm = float(xs[:, column] @ xs[:, column])
            beta[column] = np.sign(rho) * max(abs(rho) - penalty, 0.0) / max(norm, np.finfo(float).tiny)
        if np.max(np.abs(beta - previous)) < 1e-12:
            break
    original = beta.copy()
    original[1:] /= scale
    return x @ original, original


def _aic(rss: float, n: int, k: int) -> float | None:
    if n <= 0 or k < 1 or rss <= 0 or not math.isfinite(rss):
        return None
    value = n * math.log(rss / n) + 2 * k
    return value if math.isfinite(value) else None


def _aicc(rss: float, n: int, k: int) -> float:
    """Backward-compatible AICc helper; invalid cases retain ``inf``."""
    if n <= k + 1 or rss <= 0 or not math.isfinite(rss):
        return float("inf")
    value = n * math.log(rss / n) + 2 * k + (2 * k * (k + 1)) / (n - k - 1)
    return float(value) if math.isfinite(value) else float("inf")


def _aicc_optional(rss: float, n: int, k: int) -> float | None:
    value = _aicc(rss, n, k)
    return None if not math.isfinite(value) else value


def _bic(rss: float, n: int, k: int) -> float | None:
    if n <= 0 or k < 1 or rss <= 0 or not math.isfinite(rss):
        return None
    value = n * math.log(rss / n) + k * math.log(n)
    return value if math.isfinite(value) else None


def _empty_evidence(*, method: str, n: int | None, effective_n: int | None, errors: list[str], warnings: list[str] | None = None) -> dict[str, Any]:
    return _consumer_semantics({
        "status": "INCONCLUSIVE",
        "method": method,
        "formal": method == "formal_marginal_likelihood",
        "k_value": None,
        "bayes_factor": 0.0,
        "log_bayes_factor": None,
        "threshold": PASS_THRESHOLD,
        "sample_count": n,
        "effective_sample_count": effective_n,
        "selected_evidence_metric": method,
        "uncertainty": None,
        "warnings": list(warnings or []),
        "errors": list(errors),
    })


def _multiplicity_status(n_tests: int | None, correction: str | None) -> tuple[str, list[str]]:
    if n_tests is not None and (not isinstance(n_tests, (int, np.integer)) or n_tests < 1):
        return "invalid", ["n_tests must be a positive integer"]
    if n_tests in (None, 0):
        return "unknown", ["number of tested hypotheses is not declared"]
    if n_tests == 1:
        return "not_needed", []
    if correction is None:
        return "missing", ["multiple tests require a declared correction method"]
    if str(correction).lower() not in {"bonferroni", "holm", "none"}:
        return "invalid", [f"unsupported multiplicity correction: {correction}"]
    if str(correction).lower() == "none":
        return "missing", ["multiple tests cannot declare correction='none'"]
    return "corrected", []


_REASON_CODES = {
    "PROXY_ONLY",
    "FORMAL_EVIDENCE_AVAILABLE",
    "EMPIRICAL_DATA",
    "SYNTHETIC_DATA",
    "UNKNOWN_DATA_MODE",
    "INVALID_INPUT",
    "INSUFFICIENT_SAMPLE_SIZE",
    "SAMPLE_SIZE_UNDECLARED",
    "INCOMPLETE_PROVENANCE",
    "MULTIPLICITY_UNDECLARED",
    "CONTROL_NOT_PASSED",
    "ANALYSIS_NOT_INTERPRETABLE",
    "MODEL_COMPARISON_UNSUPPORTED",
    "K_UNAVAILABLE",
    "K_BELOW_THRESHOLD",
    "K_AT_THRESHOLD",
    "K_ABOVE_THRESHOLD",
    "WILSON_COWAN_PROXY",
    "LEGACY_NUMERIC_BAYES_FACTOR_DEPRECATED",
    "PASS_GATE_SATISFIED",
    "EXECUTION_ERROR",
}


def _controls_passed(result: Mapping[str, Any]) -> bool:
    controls = result.get("controls", result.get("null_control_status", {}))
    if not isinstance(controls, Mapping):
        return False
    if controls.get("passed") is True:
        return True
    return controls.get("status") in {"PASS", "passed", "valid"}


def _consumer_semantics(
    result: Mapping[str, Any],
    *,
    data_mode: Any = None,
    reason_codes: list[str] | None = None,
) -> dict[str, Any]:
    """Attach an unambiguous semantic envelope to a legacy result mapping."""
    output = dict(result)
    method = str(output.get("method", output.get("evidence_method", "unknown")))
    formal = bool(output.get("formal") is True or method == "formal_marginal_likelihood")
    evidence_kind = "formal" if formal else "proxy" if method.endswith("_proxy") or output.get("formal") is False else "unknown"
    mode = _normalise_mode(data_mode if data_mode is not None else output.get("data_mode", "unknown"))
    k_value = _finite(output.get("k_value"))
    threshold = _finite(output.get("threshold")) or PASS_THRESHOLD
    validation = output.get("validation", {})
    if not isinstance(validation, Mapping):
        validation = {}
    provenance_status = str(output.get("provenance_status", validation.get("provenance_status", "missing_or_incomplete")))
    effective_n = output.get("effective_sample_count", validation.get("effective_sample_count"))
    try:
        effective_n = int(effective_n) if effective_n is not None else None
    except (TypeError, ValueError):
        effective_n = None
    multiplicity = str(output.get("multiplicity_correction_status", validation.get("multiplicity_status", "unknown")))
    interpretable = bool(output.get("analysis_interpretable", output.get("evidence_eligible", validation.get("analysis_interpretable", False))))
    model_supported = bool(output.get("model_comparison_supported", True))
    controls_pass = _controls_passed(output)
    scientific_eligibility = bool(
        mode == "empirical"
        and formal
        and provenance_status == "complete"
        and effective_n is not None
        and effective_n >= MIN_EFFECTIVE_SAMPLE_COUNT
        and multiplicity not in {"unknown", "missing", "invalid"}
        and controls_pass
        and interpretable
        and model_supported
    )
    reasons = list(reason_codes or output.get("reason_codes", []))
    if evidence_kind == "proxy":
        reasons.append("PROXY_ONLY")
    elif evidence_kind == "formal":
        reasons.append("FORMAL_EVIDENCE_AVAILABLE")
    if mode == "empirical":
        reasons.append("EMPIRICAL_DATA")
    elif mode == "synthetic":
        reasons.append("SYNTHETIC_DATA")
    else:
        reasons.append("UNKNOWN_DATA_MODE")
    if output.get("status") == "INCONCLUSIVE":
        reasons.append("INVALID_INPUT")
    if provenance_status != "complete":
        reasons.append("INCOMPLETE_PROVENANCE")
    if effective_n is None and "sample_count" in output:
        reasons.append("SAMPLE_SIZE_UNDECLARED")
    elif effective_n is not None and effective_n < MIN_EFFECTIVE_SAMPLE_COUNT:
        reasons.append("INSUFFICIENT_SAMPLE_SIZE")
    if multiplicity in {"unknown", "missing", "invalid"}:
        reasons.append("MULTIPLICITY_UNDECLARED")
    if not controls_pass:
        reasons.append("CONTROL_NOT_PASSED")
    if not interpretable:
        reasons.append("ANALYSIS_NOT_INTERPRETABLE")
    if not model_supported:
        reasons.append("MODEL_COMPARISON_UNSUPPORTED")
    if k_value is None:
        reasons.append("K_UNAVAILABLE")
    elif k_value > threshold:
        reasons.append("K_ABOVE_THRESHOLD")
    elif k_value == threshold:
        reasons.append("K_AT_THRESHOLD")
    else:
        reasons.append("K_BELOW_THRESHOLD")
    if output.get("classical_wilson_cowan", {}).get("likelihood_status") == "not_implemented":
        reasons.append("WILSON_COWAN_PROXY")
    verdict = str(output.get("verdict", output.get("status", "INCONCLUSIVE")))
    if verdict == "PASS":
        reasons.append("PASS_GATE_SATISFIED")
    if verdict == "ERROR":
        reasons.append("EXECUTION_ERROR")
    reasons.append("LEGACY_NUMERIC_BAYES_FACTOR_DEPRECATED")
    deduplicated = [code for index, code in enumerate(reasons) if code in _REASON_CODES and code not in reasons[:index]]
    output.update(
        {
            "semantic_schema": "PITNN.FalsificationSemantics.v2",
            "evidence_method": method,
            "evidence_kind": evidence_kind,
            "is_proxy": evidence_kind == "proxy",
            "is_formal": formal,
            "data_status": mode,
            "empirical_status": mode,
            "verdict": verdict,
            "scientific_eligibility": scientific_eligibility,
            "proxy_value": k_value if evidence_kind == "proxy" else None,
            "formal_bayes_factor": k_value if formal else None,
            "reason_codes": deduplicated,
            "legacy_bayes_factor_status": "deprecated_numeric_compatibility_alias",
            "legacy_bayes_factor_warning": "Do not interpret bayes_factor as formal evidence; inspect evidence_method, evidence_kind, and formal_bayes_factor.",
        }
    )
    warnings = list(output.get("warnings", []))
    legacy_warning = output["legacy_bayes_factor_warning"]
    if legacy_warning not in warnings:
        warnings.append(legacy_warning)
    output["warnings"] = warnings
    return output


def serialize_falsification_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe consumer payload with semantic fields preserved.

    The legacy numeric ``bayes_factor`` remains for compatibility, but this
    serializer always carries its deprecation warning and the unambiguous
    proxy/formal fields alongside it.
    """
    semantic = _consumer_semantics(result)

    def json_safe(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [json_safe(item) for item in value]
        if isinstance(value, np.ndarray):
            return [json_safe(item) for item in value.tolist()]
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            return float(value) if np.isfinite(value) else None
        if isinstance(value, float):
            return value if math.isfinite(value) else None
        return value

    return json_safe(semantic)


def bayes_factor_proxy_from_rss(rss_model: float, rss_null: float, n: int, k_model: int, k_null: int, *, effective_sample_count: int | None = None, selected_metric: str = "bic", n_tests: int | None = None, multiplicity_correction: str | None = None) -> dict[str, Any]:
    """Return an information-criterion evidence ratio, never a formal BF.

    BIC is selected by default because it applies a stronger complexity
    penalty than the legacy AICc ratio. No clipping or rescaling is done.
    """
    n_int = int(n) if isinstance(n, (int, np.integer)) else -1
    effective = int(effective_sample_count) if isinstance(effective_sample_count, (int, np.integer)) else n_int
    metric = str(selected_metric).lower()
    errors: list[str] = []
    if n_int < 1:
        errors.append("sample count must be positive")
    if k_model < 1 or k_null < 1:
        errors.append("model parameter counts must be positive")
    rss_m, rss_n = _finite(rss_model), _finite(rss_null)
    if rss_m is None or rss_m <= 0 or rss_n is None or rss_n <= 0:
        errors.append("RSS values must be finite and strictly positive")
    if metric not in {"aic", "aicc", "bic"}:
        errors.append(f"unsupported evidence metric: {selected_metric}")
    mult_status, mult_errors = _multiplicity_status(n_tests, multiplicity_correction)
    if mult_status == "invalid":
        errors.extend(mult_errors)
    if errors:
        result = _empty_evidence(method=f"{metric}_proxy", n=n_int if n_int > 0 else None, effective_n=effective if effective > 0 else None, errors=errors)
        result.update({"selected_evidence_metric": metric, "aic": None, "aicc": None, "bic": None, "model_parameter_count": k_model, "null_parameter_count": k_null, "multiplicity_status": mult_status, "multiplicity_correction": multiplicity_correction})
        return result
    aic_model, aic_null = _aic(rss_m, n_int, k_model), _aic(rss_n, n_int, k_null)
    aicc_model, aicc_null = _aicc_optional(rss_m, n_int, k_model), _aicc_optional(rss_n, n_int, k_null)
    bic_model, bic_null = _bic(rss_m, n_int, k_model), _bic(rss_n, n_int, k_null)
    model_ic = {"aic": aic_model, "aicc": aicc_model, "bic": bic_model}[metric]
    null_ic = {"aic": aic_null, "aicc": aicc_null, "bic": bic_null}[metric]
    common = {"selected_evidence_metric": metric, "aic": {"model": aic_model, "null": aic_null}, "aicc": {"model": aicc_model, "null": aicc_null}, "bic": {"model": bic_model, "null": bic_null}, "model": {"rss": rss_m, "aic": aic_model, "aicc": aicc_model, "bic": bic_model}, "null": {"rss": rss_n, "aic": aic_null, "aicc": aicc_null, "bic": bic_null}, "model_parameter_count": k_model, "null_parameter_count": k_null, "multiplicity_status": mult_status, "multiplicity_correction": multiplicity_correction}
    if model_ic is None or null_ic is None:
        result = _empty_evidence(method=f"{metric}_proxy", n=n_int, effective_n=effective, errors=[f"{metric.upper()} is undefined for this sample/model-size combination"])
        result.update(common)
        return result
    log_k = 0.5 * (null_ic - model_ic)
    try:
        k_value = float(math.exp(log_k))
    except (OverflowError, ValueError):
        result = _empty_evidence(method=f"{metric}_proxy", n=n_int, effective_n=effective, errors=["evidence ratio overflow; K is intentionally left null"])
        result.update(common)
        return result
    result = {"status": "NOT_SUPPORTED", "method": f"{metric}_proxy", "formal": False, "k_value": k_value, "bayes_factor": k_value, "log_k_value": float(log_k), "log_bayes_factor": float(log_k), "threshold": PASS_THRESHOLD, "sample_count": n_int, "effective_sample_count": effective, "parameter_count": {"model": k_model, "null": k_null}, "uncertainty": None, "warnings": ["This is an information-criterion/RSS proxy, not a formal Bayes factor", "No likelihood normalization or prior integration was performed"], "errors": []}
    result.update(common)
    return _consumer_semantics(result)


def bayes_factor_from_marginal_likelihoods(model_marginal_likelihood: float, null_marginal_likelihood: float, *, model_prior: float = 1.0, null_prior: float = 1.0, assumptions: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Compute a formal BF only from finite positive marginal likelihoods."""
    model, null = _finite(model_marginal_likelihood), _finite(null_marginal_likelihood)
    prior_model, prior_null = _finite(model_prior), _finite(null_prior)
    errors: list[str] = []
    if model is None or model <= 0 or null is None or null <= 0:
        errors.append("marginal likelihoods must be finite and strictly positive")
    if prior_model is None or prior_model <= 0 or prior_null is None or prior_null <= 0:
        errors.append("model priors must be finite and strictly positive")
    if errors:
        return _empty_evidence(method="formal_marginal_likelihood", n=None, effective_n=None, errors=errors)
    log_k = math.log(model) - math.log(null)
    try:
        k_value = float(model / null)
        posterior = float(k_value * (prior_model / prior_null))
    except (OverflowError, ValueError):
        return _empty_evidence(method="formal_marginal_likelihood", n=None, effective_n=None, errors=["formal evidence ratio overflow; K is intentionally left null"])
    return _consumer_semantics({"status": "NOT_SUPPORTED", "method": "formal_marginal_likelihood", "formal": True, "k_value": k_value, "bayes_factor": k_value, "log_bayes_factor": float(log_k), "posterior_odds": posterior, "threshold": PASS_THRESHOLD, "selected_evidence_metric": "marginal_likelihood", "model_marginal_likelihood": model, "null_marginal_likelihood": null, "model_prior": prior_model, "null_prior": prior_null, "likelihood_assumptions": dict(assumptions or {}), "uncertainty": None, "warnings": [], "errors": []})


def validate_falsification_input(signal: Any, inversion: Mapping[str, Any] | None = None, *, data_mode: str = "unknown", provenance: Mapping[str, Any] | None = None, paired_subjects: int | None = None, min_paired_subjects: int = 2, effective_sample_count: int | None = None, min_effective_sample_count: int = MIN_EFFECTIVE_SAMPLE_COUNT, n_tests: int | None = None, multiplicity_correction: str | None = None, preregistered: bool | None = None) -> dict[str, Any]:
    """Validate data and provenance before a scientific verdict is possible."""
    mode = _normalise_mode(data_mode)
    errors: list[str] = []
    warnings: list[str] = []
    try:
        array = np.asarray(signal, dtype=float)
    except (TypeError, ValueError):
        array = np.asarray([], dtype=float)
        errors.append("signal is not numeric")
    if array.ndim == 0:
        array = array.reshape(1)
    sample_count = int(array.shape[0]) if array.ndim else 0
    feature_count = int(np.prod(array.shape[1:])) if array.ndim > 1 else 1
    finite = bool(array.size and np.all(np.isfinite(array)))
    if not finite:
        errors.append("signal is missing, empty, or contains non-finite values")
    if sample_count < 8:
        errors.append("at least eight observations are required")
    if finite and array.size and float(np.ptp(array)) <= 1e-12:
        errors.append("constant or degenerate signal cannot identify a comparison")
    effective = effective_sample_count
    if effective is None and isinstance(inversion, Mapping):
        effective = inversion.get("effective_sample_count", inversion.get("n_eff"))
    if effective is None:
        effective = sample_count
    try:
        effective = int(effective)
    except (TypeError, ValueError):
        effective = None
        errors.append("effective sample count is not an integer")
    if effective is not None and effective < min_effective_sample_count:
        errors.append(f"effective sample count {effective} is below minimum {min_effective_sample_count}")
    if paired_subjects is not None and paired_subjects < min_paired_subjects:
        errors.append("insufficient paired subjects")
    provenance_ok = True
    if mode == "empirical":
        required = {"dataset_id", "source", "sample_rate_hz"}
        if not isinstance(provenance, Mapping):
            provenance_ok = False
            errors.append("empirical provenance is missing")
        else:
            missing = [key for key in required if not provenance.get(key)]
            if not (provenance.get("source_file") or provenance.get("source_path") or provenance.get("uri")):
                missing.append("source_file")
            if missing:
                provenance_ok = False
                errors.append("incomplete empirical provenance: " + ", ".join(sorted(set(missing))))
            rate = _finite(provenance.get("sample_rate_hz"))
            if rate is None or rate <= 0:
                provenance_ok = False
                errors.append("empirical sample_rate_hz must be positive")
    else:
        if mode in {"unknown", ""}:
            warnings.append("data mode is not declared")
        if mode == "synthetic":
            warnings.append("synthetic/null data cannot support an empirical PASS")
    mult_status, mult_errors = _multiplicity_status(n_tests, multiplicity_correction)
    if mult_status in {"invalid", "missing"}:
        errors.extend(mult_errors)
    elif mult_status == "unknown":
        warnings.extend(mult_errors)
    prereg_status = "complete" if preregistered is True else "not_preregistered" if preregistered is False else "not_declared"
    status = "VALID" if not errors else "INCONCLUSIVE"
    provenance_status = "complete" if provenance_ok else (
        "incomplete" if mode == "empirical" and isinstance(provenance, Mapping)
        else "missing_or_incomplete"
    )
    return {"status": status, "valid": status == "VALID", "data_mode": mode, "sample_count": sample_count, "feature_count": feature_count, "effective_sample_count": effective, "provenance_status": provenance_status, "provenance_completeness": provenance_ok, "preregistration_status": prereg_status, "multiplicity_status": mult_status, "multiplicity_correction": multiplicity_correction, "paired_subjects": paired_subjects, "analysis_interpretable": not errors, "warnings": warnings, "errors": errors}


def _controls_pass(controls: Any) -> bool | None:
    """Return a tri-state result for declared deterministic null controls."""
    if controls is None:
        return None
    if isinstance(controls, Mapping):
        if "passed" in controls:
            return bool(controls["passed"])
        values = list(controls.values())
    elif isinstance(controls, (list, tuple)):
        values = list(controls)
    else:
        return False
    if not values:
        return None
    states: list[bool] = []
    for value in values:
        if isinstance(value, Mapping):
            passed = value.get("passed", value.get("status"))
            if passed not in (True, "PASS", "PASSED", "pass", "passed"):
                return False
            if "seed" not in value or not value.get("method"):
                return False
            states.append(True)
        elif isinstance(value, bool):
            states.append(value)
        else:
            return False
    return all(states)


def classify_falsification_status(k_value: Any, *, threshold: float = PASS_THRESHOLD, method: str = "unknown", data_mode: str = "unknown", validation_status: str = "VALID", provenance_status: str = "complete", analysis_interpretable: bool = True, controls: Mapping[str, Any] | None = None, controls_pass: bool | None = None, multiplicity_status: str = "unknown", effective_sample_count: int | None = None, min_effective_sample_count: int = MIN_EFFECTIVE_SAMPLE_COUNT, model_comparison_supported: bool = True, execution_error: bool = False) -> str:
    """Apply the scientific verdict gate without modifying K."""
    if isinstance(k_value, Mapping):
        evidence = k_value
        if method == "unknown":
            method = str(evidence.get("evidence_method", evidence.get("method", "unknown")))
        if data_mode == "unknown":
            data_mode = str(evidence.get("data_status", evidence.get("data_mode", "unknown")))
        if validation_status == "VALID":
            validation = evidence.get("validation", {})
            validation_status = str(validation.get("status", evidence.get("status", "INCONCLUSIVE"))) if isinstance(validation, Mapping) else str(evidence.get("status", "INCONCLUSIVE"))
        if provenance_status == "complete":
            provenance_status = str(evidence.get("provenance_status", "missing_or_incomplete"))
        if effective_sample_count is None:
            effective_sample_count = evidence.get("effective_sample_count")
        if multiplicity_status == "unknown":
            multiplicity_status = str(evidence.get("multiplicity_correction_status", evidence.get("multiplicity_status", "unknown")))
        if controls is None:
            candidate_controls = evidence.get("controls", evidence.get("null_control_status"))
            controls = candidate_controls if isinstance(candidate_controls, Mapping) else None
        if controls_pass is None and isinstance(controls, Mapping) and "passed" in controls:
            controls_pass = controls.get("passed") is True
        k_value = evidence.get("formal_bayes_factor") if method.startswith("formal_marginal_likelihood") else evidence.get("k_value")
    if execution_error:
        return "ERROR"
    if validation_status != "VALID" or not model_comparison_supported:
        return "INCONCLUSIVE"
    mode = _normalise_mode(data_mode)
    if mode == "synthetic":
        return "NOT_SUPPORTED"
    if mode != "empirical":
        return "INCONCLUSIVE"
    if not analysis_interpretable:
        return "INCONCLUSIVE"
    if provenance_status != "complete":
        return "INCONCLUSIVE"
    if effective_sample_count is None:
        return "INCONCLUSIVE"
    if effective_sample_count < min_effective_sample_count:
        return "INCONCLUSIVE"
    if multiplicity_status in {"unknown", "missing", "invalid"}:
        return "INCONCLUSIVE"
    # A regression/RSS comparison is a proxy by construction.  Once the
    # input contract itself is valid, absence of formal controls must not
    # relabel that non-evidence as an ambiguous failure: it is explicitly
    # unsupported for a scientific PASS verdict.  Formal evidence still
    # requires the control gate below.
    if not str(method).startswith("formal_marginal_likelihood"):
        return "NOT_SUPPORTED"
    if controls_pass is None:
        controls_pass = _controls_pass(controls)
    if controls_pass is not True:
        return "INCONCLUSIVE" if controls_pass is None else "NOT_SUPPORTED"
    k = _finite(k_value)
    if k is None or k < 0:
        return "INCONCLUSIVE"
    return "PASS" if k > threshold else "NOT_SUPPORTED"


def multiplicity_correction(p_values: Any, *, method: str = "holm") -> dict[str, Any]:
    """Return deterministic Bonferroni/Holm-adjusted p-values and metadata."""
    try:
        values = np.asarray(p_values, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        values = np.asarray([], dtype=float)
    name = str(method).lower()
    if values.size == 0 or not np.all(np.isfinite(values)) or np.any((values < 0) | (values > 1)):
        return {"status": "INCONCLUSIVE", "method": name, "n_tests": int(values.size), "adjusted_p_values": None, "errors": ["p-values must be finite and lie in [0, 1]"]}
    count = values.size
    if name == "bonferroni":
        adjusted = np.minimum(values * count, 1.0)
    elif name == "holm":
        order = np.argsort(values, kind="mergesort")
        sorted_values = values[order]
        adjusted_sorted = np.maximum.accumulate((count - np.arange(count)) * sorted_values)
        adjusted = np.empty_like(adjusted_sorted)
        adjusted[order] = np.minimum(adjusted_sorted, 1.0)
    else:
        return {"status": "INCONCLUSIVE", "method": name, "n_tests": int(count), "adjusted_p_values": None, "errors": ["method must be bonferroni or holm"]}
    return {"status": "PASS", "method": name, "n_tests": int(count), "adjusted_p_values": adjusted.tolist(), "errors": []}


def generate_null_controls(signal: Any, *, seed: int = 0, labels: Any | None = None, block_size: int | None = None) -> dict[str, dict[str, Any]]:
    """Generate deterministic, explicitly labelled null-control fixtures."""
    try:
        values = np.asarray(signal, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        values = np.asarray([], dtype=float)
    rng = np.random.default_rng(int(seed))
    if values.size and np.all(np.isfinite(values)):
        scale = float(np.std(values)) or 1.0
        gaussian = rng.normal(0.0, scale, size=values.size)
        centered = values - float(np.mean(values))
        spectrum = np.fft.rfft(centered)
        phases = rng.uniform(0.0, 2.0 * np.pi, size=max(0, spectrum.size - 2))
        shuffled_spectrum = spectrum.copy()
        if phases.size:
            shuffled_spectrum[1:-1] = np.abs(spectrum[1:-1]) * np.exp(1j * phases)
        phase_shuffled = np.fft.irfft(shuffled_spectrum, n=values.size) + float(np.mean(values))
        if block_size and block_size > 0:
            blocks = [values[i : i + block_size] for i in range(0, values.size, block_size)]
            rng.shuffle(blocks)
            stationary = np.concatenate(blocks)
        else:
            stationary = np.roll(values, int(rng.integers(0, values.size)))
        flat = np.full_like(values, float(np.mean(values)))
    else:
        flat = gaussian = phase_shuffled = stationary = None
    result: dict[str, dict[str, Any]] = {
        "flat_signal": {"values": flat, "method": "flat_signal", "seed": int(seed), "status": "PASS" if flat is not None else "INCONCLUSIVE"},
        "independent_gaussian": {"values": gaussian, "method": "independent_gaussian", "seed": int(seed), "status": "PASS" if gaussian is not None else "INCONCLUSIVE"},
        "phase_shuffled": {"values": phase_shuffled, "method": "phase_randomization", "seed": int(seed), "status": "PASS" if phase_shuffled is not None else "INCONCLUSIVE"},
        "stationary_surrogate": {"values": stationary, "method": "autocorrelation_preserving_block_permutation", "seed": int(seed), "block_size": block_size, "status": "PASS" if stationary is not None else "INCONCLUSIVE"},
    }
    if labels is not None:
        label_array = np.asarray(labels)
        permutation = rng.permutation(label_array.size)
        result["condition_label_permutation"] = {"labels": label_array[permutation].tolist(), "method": "condition_label_permutation", "seed": int(seed), "status": "PASS"}
    return result


def phase_randomized_surrogate(signal: Any, *, seed: int = 0) -> dict[str, Any]:
    return generate_null_controls(signal, seed=seed)["phase_shuffled"]


def condition_label_permutation(labels: Any, *, seed: int = 0) -> dict[str, Any]:
    return generate_null_controls(np.zeros(len(labels)), labels=labels, seed=seed)["condition_label_permutation"]


def stationary_null_surrogate(signal: Any, *, seed: int = 0, block_size: int | None = None) -> dict[str, Any]:
    return generate_null_controls(signal, seed=seed, block_size=block_size)["stationary_surrogate"]


def separate_topology_metrics(inversion: Mapping[str, Any] | None) -> dict[str, Any]:
    """Expose graph, spatial, and chirality quantities without conversion."""
    source = inversion if isinstance(inversion, Mapping) else {}
    aliases = {"graph_beta1": ("graph_beta1", "beta1_loops", "beta_1"), "spatial_winding_q": ("spatial_winding_q", "winding_number", "q_emp_mean"), "scalar_chirality": ("scalar_chirality", "chirality")}
    return {name: next((_finite(source[key]) for key in keys if key in source), None) for name, keys in aliases.items()}


def _contract_failure(message: str, *, data_mode: str = "unknown") -> dict[str, Any]:
    return _consumer_semantics({"status": "ERROR", "verdict": "ERROR", "method": "unsupported_model_comparison", "k_value": None, "bayes_factor": 0.0, "log_bayes_factor": None, "threshold": PASS_THRESHOLD, "data_mode": _normalise_mode(data_mode), "provenance_status": "missing_or_incomplete", "sample_count": None, "feature_count": None, "effective_sample_count": None, "uncertainty": None, "controls": {"status": "not_run"}, "warnings": [], "errors": [message], "model_comparison_supported": False})


def compare_models(signal: np.ndarray, inversion: dict, *, topological_l1_penalty: float = 1e-4, data_mode: str = "synthetic_demo", provenance: Mapping[str, Any] | None = None, effective_sample_count: int | None = None, paired_subjects: int | None = None, n_tests: int | None = None, multiplicity_correction: str | None = None, controls: Mapping[str, Any] | None = None, preregistered: bool | None = None, selected_evidence_metric: str = "bic") -> dict[str, Any]:
    """Compare regression surrogates while keeping the scientific gate closed.

    The classical arm is still a Wilson-Cowan proxy regression, not a
    Wilson-Cowan likelihood. Consequently its evidence method is never
    formal and cannot produce PASS.
    """
    try:
        y = np.asarray(signal, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        return _contract_failure("signal is not numeric", data_mode=data_mode)
    inversion = inversion if isinstance(inversion, Mapping) else None
    validation = validate_falsification_input(y, inversion, data_mode=data_mode, provenance=provenance, paired_subjects=paired_subjects, effective_sample_count=effective_sample_count, n_tests=n_tests, multiplicity_correction=multiplicity_correction, preregistered=preregistered)
    if inversion is None:
        return _consumer_semantics(_contract_failure("inversion must be a mapping", data_mode=data_mode) | {"validation": validation})
    if validation["status"] != "VALID":
        verdict = "INCONCLUSIVE" if _normalise_mode(data_mode) == "empirical" else "NOT_SUPPORTED"
        return _consumer_semantics({"status": "INCONCLUSIVE", "verdict": verdict, "method": "unsupported_model_comparison", "formal": False, "k_value": None, "bayes_factor": 0.0, "log_bayes_factor": None, "threshold": PASS_THRESHOLD, "data_mode": validation["data_mode"], "provenance_status": validation["provenance_status"], "provenance": dict(provenance or {}), "provenance_completeness": validation["provenance_completeness"], "sample_count": validation["sample_count"], "feature_count": validation["feature_count"], "effective_sample_count": validation["effective_sample_count"], "multiplicity_correction_status": validation["multiplicity_status"], "preregistration_status": validation["preregistration_status"], "uncertainty": None, "controls": dict(controls or {"status": "not_run"}), "warnings": validation["warnings"], "errors": validation["errors"], "validation": validation, "model_comparison_supported": False, "pitnn": {"rss": None, "aic": None, "aicc": None, "bic": None}, "classical_wilson_cowan": {"rss": None, "aic": None, "aicc": None, "bic": None}, "topology_metrics": separate_topology_metrics(inversion)})
    n = y.size
    x = np.linspace(0.0, 1.0, n)
    q_series = inversion.get("q_emp_series", inversion.get("topological_charge_series"))
    try:
        if q_series is None:
            topology = np.full(n, float(inversion.get("q_emp_mean", 0.0)))
        else:
            source = np.asarray(q_series, dtype=float).reshape(-1)
            if source.size < 2 or not np.all(np.isfinite(source)):
                raise ValueError("topological series must contain at least two finite values")
            topology = np.interp(x, np.linspace(0.0, 1.0, source.size), source)
        signal_static = bool(np.ptp(y) <= 1e-12)
        topology_static = bool(np.ptp(topology) <= 1e-12)
        topological = np.column_stack([np.ones(n), x, np.sin(2 * np.pi * x), np.cos(2 * np.pi * x), topology])
        classical = np.column_stack([np.ones(n), x, np.sin(2 * np.pi * x), np.cos(2 * np.pi * x)])
        pred_q, beta_q = _fit_l1(y, topological, topological_l1_penalty)
        pred_c, _ = _fit_linear(y, classical)
    except (TypeError, ValueError, np.linalg.LinAlgError) as exc:
        return _consumer_semantics(_contract_failure(str(exc), data_mode=data_mode) | {"validation": validation})
    rss_q, rss_c = float(np.sum((y - pred_q) ** 2)), float(np.sum((y - pred_c) ** 2))
    active_q = int(1 + np.count_nonzero(np.abs(beta_q[1:]) > 1e-12))
    q_parameters, c_parameters = int(active_q + 1), int(classical.shape[1] + 1)
    evidence = bayes_factor_proxy_from_rss(rss_q, rss_c, n, q_parameters, c_parameters, effective_sample_count=validation["effective_sample_count"], selected_metric=selected_evidence_metric, n_tests=n_tests, multiplicity_correction=multiplicity_correction)
    topological_active = bool(not topology_static and abs(beta_q[-1]) > 1e-12)
    evidence_eligible = bool(not signal_static and topological_active)
    control_status = dict(controls or {"status": "not_run"})
    status_input = dict(evidence)
    status_input.update({"data_mode": data_mode, "data_status": validation["data_mode"], "provenance_status": validation["provenance_status"], "effective_sample_count": validation["effective_sample_count"], "multiplicity_correction_status": validation["multiplicity_status"], "controls": control_status, "evidence_eligible": evidence_eligible, "validation": validation, "model_comparison_supported": True})
    status = classify_falsification_status(status_input, threshold=PASS_THRESHOLD, controls_pass=control_status.get("passed") if "passed" in control_status else None)
    return _consumer_semantics({"status": status, "verdict": status, "method": evidence["method"], "formal": False, "k_value": evidence.get("k_value"), "bayes_factor": _finite_or_zero(evidence.get("k_value")), "log_bayes_factor": evidence.get("log_bayes_factor"), "threshold": PASS_THRESHOLD, "data_mode": validation["data_mode"], "provenance_status": validation["provenance_status"], "provenance": dict(provenance or {}), "provenance_completeness": validation["provenance_completeness"], "sample_count": validation["sample_count"], "feature_count": validation["feature_count"], "effective_sample_count": validation["effective_sample_count"], "model_parameter_counts": {"pitnn": q_parameters, "classical_wilson_cowan_proxy": c_parameters}, "likelihood_method": "gaussian_regression_proxy", "null_control_status": control_status, "multiplicity_correction_status": validation["multiplicity_status"], "preregistration_status": validation["preregistration_status"], "selected_evidence_metric": selected_evidence_metric, "uncertainty": evidence.get("uncertainty"), "controls": control_status, "warnings": evidence.get("warnings", []) + ["No biological confirmation is asserted"], "errors": evidence.get("errors", []), "validation": validation, "model_comparison_supported": True, "signal_static": signal_static, "evidence_eligible": evidence_eligible, "topology_metrics": separate_topology_metrics(inversion), "topology_metric_semantics": {"graph_beta1": "graph cycle rank; not spatial charge", "spatial_winding_q": "coordinate-dependent spatial winding; not graph beta-1", "scalar_chirality": "local vector-triple-product observable; not winding"}, "pitnn": {"rss": rss_q, "aic": evidence["aic"]["model"], "aicc": evidence["aicc"]["model"], "bic": evidence["bic"]["model"], "topological_l1_penalty": float(topological_l1_penalty), "topological_weight": float(beta_q[-1]), "topological_feature_static": topology_static, "topological_feature_active": topological_active, "active_parameters": active_q, "parameter_count": q_parameters}, "classical_wilson_cowan": {"rss": rss_c, "aic": evidence["aic"]["null"], "aicc": evidence["aicc"]["null"], "bic": evidence["bic"]["null"], "parameter_count": c_parameters, "model_type": "wilson_cowan_proxy_regression", "likelihood_status": "not_implemented"}})


__all__ = ["PASS_THRESHOLD", "bayes_factor_proxy_from_rss", "bayes_factor_from_marginal_likelihoods", "validate_falsification_input", "classify_falsification_status", "multiplicity_correction", "generate_null_controls", "phase_randomized_surrogate", "condition_label_permutation", "stationary_null_surrogate", "separate_topology_metrics", "serialize_falsification_result", "compare_models"]
