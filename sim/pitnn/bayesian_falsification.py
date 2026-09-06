"""Falsification contracts for PITNN model comparisons.

The repository historically exposed ``compare_models`` and reported an RSS
ratio as ``bayes_factor``. That value is retained for compatibility, but is
now explicitly labelled as an AICc/RSS proxy. A formal Bayes factor is only
available through :func:`bayes_factor_from_marginal_likelihoods`.

This module is deliberately conservative: synthetic or incomplete inputs can
produce descriptive metrics, but they cannot produce an empirical ``PASS``.
"""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np


PASS_THRESHOLD = 100.0
_EMPIRICAL_MODES = {"empirical", "empirical_local", "empirical_labeled", "empirical_remote"}
_FORMAL_METHODS = {"formal_marginal_likelihood", "marginal_likelihood"}


def _fit_linear(y: np.ndarray, design: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    return design @ beta, beta


def _fit_l1(
    y: np.ndarray,
    design: np.ndarray,
    penalty: float,
    iterations: int = 2000,
) -> tuple[np.ndarray, np.ndarray]:
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
            beta[column] = np.sign(rho) * max(abs(rho) - penalty, 0.0) / max(
                norm, np.finfo(float).tiny
            )
        if np.max(np.abs(beta - previous)) < 1e-12:
            break
    original = beta.copy()
    original[1:] /= scale
    return x @ original, original


def _aic(rss: float, n: int, k: int) -> float:
    """Return Gaussian least-squares AIC for ``k`` fitted parameters."""
    if n < 1 or k < 1 or n <= k or not np.isfinite(rss) or rss <= 0:
        return float("inf")
    return float(n * math.log(rss / n) + 2 * k)


def _aicc(rss: float, n: int, k: int) -> float:
    """Return finite-sample corrected Gaussian least-squares AIC."""
    if n <= k + 1 or rss <= 0 or not np.isfinite(rss):
        return float("inf")
    return float(_aic(rss, n, k) + (2 * k * (k + 1)) / (n - k - 1))


def _finite_positive(value: Any) -> bool:
    try:
        return bool(np.isfinite(float(value)) and float(value) > 0)
    except (TypeError, ValueError):
        return False


def bayes_factor_proxy_from_rss(
    rss_model: float,
    rss_null: float,
    n: int,
    k_model: int,
    k_null: int,
) -> dict[str, Any]:
    """Compute a clearly labelled RSS/AICc model-comparison proxy.

    This is *not* a formal Bayes factor. It is the exponential of the
    negative half AICc difference under a common Gaussian residual convention.
    No prior integration is performed. ``k_value`` is retained as the
    repository's historical evidence-scale name so callers can migrate while
    inspecting the explicit ``method`` field.
    """
    try:
        n_int = int(n)
        model_k = int(k_model)
        null_k = int(k_null)
    except (TypeError, ValueError) as exc:
        raise ValueError("n and parameter counts must be integers") from exc
    if n_int < 1 or model_k < 1 or null_k < 1:
        raise ValueError("n and parameter counts must be positive")
    if not _finite_positive(rss_model) or not _finite_positive(rss_null):
        raise ValueError("RSS values must be finite and strictly positive")

    rss_model_f = float(rss_model)
    rss_null_f = float(rss_null)
    aic_model = _aic(rss_model_f, n_int, model_k)
    aic_null = _aic(rss_null_f, n_int, null_k)
    aicc_model = _aicc(rss_model_f, n_int, model_k)
    aicc_null = _aicc(rss_null_f, n_int, null_k)
    if not np.isfinite(aicc_model) or not np.isfinite(aicc_null):
        raise ValueError("AICc is undefined for the supplied sample and parameter counts")

    log_k = float(-0.5 * (aicc_model - aicc_null))
    log_k = float(np.clip(log_k, -700.0, 700.0))
    k_value = float(math.exp(log_k))
    raw_log_rss_ratio = float(0.5 * n_int * math.log(rss_null_f / rss_model_f))
    return {
        "method": "rss_ratio_proxy",
        "formal": False,
        "k_value": k_value,
        "bayes_factor": k_value,
        "log_k_value": log_k,
        "log_bayes_factor": log_k,
        "rss_likelihood_log_ratio": raw_log_rss_ratio,
        "sample_count": n_int,
        "parameter_count": {"model": model_k, "null": null_k},
        "model": {"rss": rss_model_f, "aic": aic_model, "aicc": aicc_model},
        "null": {"rss": rss_null_f, "aic": aic_null, "aicc": aicc_null},
        "uncertainty": {
            "available": False,
            "reason": "RSS/AICc proxy has no integrated parameter or prior uncertainty",
        },
        "warnings": [
            "This is an RSS/AICc proxy, not a formal Bayes factor.",
            "No marginal likelihood integration or prior-sensitive model evidence was computed.",
        ],
        "errors": [],
    }


def bayes_factor_from_marginal_likelihoods(
    model_marginal_likelihood: float,
    null_marginal_likelihood: float,
    *,
    model_prior: float = 1.0,
    null_prior: float = 1.0,
    assumptions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a formal Bayes factor from supplied marginal likelihoods.

    The caller is responsible for obtaining the marginal likelihoods from an
    implemented model and declared priors. Priors are recorded as metadata and
    posterior odds are exposed separately; they are not silently folded into
    ``k_value``.
    """
    values = {
        "model marginal likelihood": model_marginal_likelihood,
        "null marginal likelihood": null_marginal_likelihood,
        "model prior": model_prior,
        "null prior": null_prior,
    }
    invalid = [name for name, value in values.items() if not _finite_positive(value)]
    if invalid:
        raise ValueError(f"{', '.join(invalid)} must be finite and strictly positive")
    model_ml = float(model_marginal_likelihood)
    null_ml = float(null_marginal_likelihood)
    model_prior_f = float(model_prior)
    null_prior_f = float(null_prior)
    k_value = model_ml / null_ml
    log_k = float(math.log(k_value))
    return {
        "method": "formal_marginal_likelihood",
        "formal": True,
        "k_value": float(k_value),
        "bayes_factor": float(k_value),
        "log_k_value": log_k,
        "log_bayes_factor": log_k,
        "marginal_likelihoods": {"model": model_ml, "null": null_ml},
        "priors": {"model": model_prior_f, "null": null_prior_f},
        "prior_odds": model_prior_f / null_prior_f,
        "posterior_odds": k_value * model_prior_f / null_prior_f,
        "assumptions": dict(assumptions or {}),
        "uncertainty": {"available": False, "reason": "No marginal-likelihood uncertainty supplied"},
        "warnings": [],
        "errors": [],
    }


def _is_empirical_mode(data_mode: str | None) -> bool:
    return str(data_mode or "").strip().lower() in _EMPIRICAL_MODES


def _provenance_status(data_mode: str, provenance: Mapping[str, Any] | str | None) -> str:
    if not _is_empirical_mode(data_mode):
        return "synthetic" if str(data_mode).lower().startswith("synthetic") else "unknown"
    if provenance == "complete":
        return "complete"
    if not isinstance(provenance, Mapping):
        return "missing"
    source = any(provenance.get(key) for key in ("source", "source_file", "source_path", "uri"))
    dataset = bool(provenance.get("dataset_id"))
    sample_rate = _finite_positive(provenance.get("sample_rate_hz"))
    return "complete" if source and dataset and sample_rate else "incomplete"


def validate_falsification_input(
    signal: Any,
    inversion: Mapping[str, Any] | None = None,
    *,
    data_mode: str = "unknown",
    provenance: Mapping[str, Any] | str | None = None,
    paired_subjects: int | None = None,
    min_paired_subjects: int = 2,
    require_empirical: bool = False,
) -> dict[str, Any]:
    """Validate data and provenance without raising for scientific invalidity.

    Missing, malformed, constant, or insufficient inputs are returned as
    ``INCONCLUSIVE`` so a caller can emit a complete contract rather than
    silently converting unusable data into ``NOT_SUPPORTED``.
    """
    errors: list[str] = []
    warnings: list[str] = []
    sample_count = 0
    feature_count = 0
    try:
        values = np.asarray(signal, dtype=float)
    except (TypeError, ValueError):
        values = np.asarray([], dtype=float)
        errors.append("signal is not numeric")
    if values.ndim == 1:
        sample_count = int(values.size)
        feature_count = 1
        feature_values = values[:, None]
    elif values.ndim == 2:
        sample_count, feature_count = map(int, values.shape)
        feature_values = values
    else:
        feature_values = np.empty((0, 1))
        errors.append("signal must be one- or two-dimensional")
    if sample_count < 8:
        errors.append("at least eight observations are required")
    if values.size and not np.all(np.isfinite(values)):
        errors.append("signal contains non-finite values")
    if feature_values.size and np.any(np.ptp(feature_values, axis=0) <= 1e-12):
        errors.append("constant or degenerate feature detected")
    if inversion is None or not isinstance(inversion, Mapping):
        errors.append("inversion/model comparison input is missing or malformed")
    elif not inversion:
        errors.append("inversion/model comparison input is empty")

    if paired_subjects is not None:
        try:
            if int(paired_subjects) < int(min_paired_subjects):
                errors.append(f"insufficient paired subjects: {paired_subjects} < {min_paired_subjects}")
        except (TypeError, ValueError):
            errors.append("paired subject count is malformed")

    mode = str(data_mode or "unknown").strip().lower()
    if require_empirical and not _is_empirical_mode(mode):
        errors.append("empirical data is required for this contract")
    provenance_state = _provenance_status(mode, provenance)
    if _is_empirical_mode(mode) and provenance_state != "complete":
        errors.append(f"empirical provenance is {provenance_state}")
    if mode == "unknown":
        errors.append("data_mode is missing or unknown")
    if mode.startswith("synthetic"):
        warnings.append("synthetic data cannot support an empirical PASS")

    return {
        "status": "VALID" if not errors else "INCONCLUSIVE",
        "valid": not errors,
        "data_mode": mode,
        "provenance_status": provenance_state,
        "sample_count": sample_count,
        "feature_count": feature_count,
        "warnings": warnings,
        "errors": errors,
    }


def _controls_pass(controls: Any) -> bool:
    if isinstance(controls, Mapping):
        if "passed" in controls:
            return bool(controls["passed"])
        if not controls:
            return False
        values = list(controls.values())
    elif isinstance(controls, (list, tuple)):
        if not controls:
            return False
        values = list(controls)
    else:
        return False
    for value in values:
        if isinstance(value, Mapping):
            passed = value.get("passed", value.get("status"))
            if passed not in (True, "PASS", "PASSED", "pass", "passed"):
                return False
            if "seed" not in value or not value.get("method"):
                return False
        elif value is not True:
            return False
    return True


def classify_falsification_status(
    k_value: float | Mapping[str, Any] | None,
    *,
    threshold: float = PASS_THRESHOLD,
    data_mode: str = "unknown",
    provenance_status: str = "unknown",
    analysis_interpretable: bool = True,
    controls: Any = None,
    method: str = "rss_ratio_proxy",
    model_comparison_supported: bool = True,
    validation_status: str = "VALID",
    execution_error: bool = False,
) -> str:
    """Map a comparison to ``PASS``, ``NOT_SUPPORTED``, ``INCONCLUSIVE``, or ``ERROR``."""
    if isinstance(k_value, Mapping):
        result = k_value
        k_value = result.get("k_value", result.get("bayes_factor"))
        method = str(result.get("method", method))
    if execution_error:
        return "ERROR"
    if not _finite_positive(threshold) or threshold <= 0:
        return "ERROR"
    if validation_status in {"ERROR", "error"}:
        return "ERROR"
    mode = str(data_mode or "unknown").lower()
    if mode.startswith("synthetic"):
        return "NOT_SUPPORTED"
    if not analysis_interpretable or validation_status not in {"VALID", "valid"}:
        return "INCONCLUSIVE"
    if not model_comparison_supported:
        return "INCONCLUSIVE"
    if mode == "unknown" or (_is_empirical_mode(mode) and provenance_status != "complete"):
        return "INCONCLUSIVE"
    if not _controls_pass(controls):
        return "INCONCLUSIVE"
    if not _finite_positive(k_value):
        return "INCONCLUSIVE"
    if method not in _FORMAL_METHODS:
        return "NOT_SUPPORTED"
    return "PASS" if float(k_value) > float(threshold) else "NOT_SUPPORTED"


def _comparison_error(
    *,
    data_mode: str,
    provenance_status: str,
    validation: Mapping[str, Any],
    error: str,
    status: str = "ERROR",
) -> dict[str, Any]:
    warnings = list(validation.get("warnings", []))
    errors = list(validation.get("errors", [])) + [error]
    return {
        "status": status,
        "method": "none",
        "k_value": None,
        "threshold": PASS_THRESHOLD,
        "data_mode": data_mode,
        "provenance_status": provenance_status,
        "sample_count": validation.get("sample_count", 0),
        "feature_count": validation.get("feature_count", 0),
        "uncertainty": {"available": False, "reason": "comparison did not execute"},
        "controls": {},
        "warnings": warnings,
        "errors": errors,
        "bayes_factor": 0.0,
        "log_bayes_factor": 0.0,
        "verdict": status,
        "signal_static": False,
        "evidence_eligible": False,
        "pitnn": {"rss": 0.0, "aicc": float("inf")},
        "classical_wilson_cowan": {"rss": 0.0, "aicc": float("inf")},
    }


def compare_models(
    signal: np.ndarray,
    inversion: dict,
    *,
    topological_l1_penalty: float = 1e-4,
    data_mode: str | None = None,
    provenance: Mapping[str, Any] | str | None = None,
    controls: Any = None,
    paired_subjects: int | None = None,
    method: str = "rss_ratio_proxy",
) -> dict[str, Any]:
    """Compare topological and classical models with a compatibility payload.

    ``verdict`` remains the legacy key and mirrors the authoritative ``status``.
    Existing callers that omit metadata are treated as deterministic synthetic
    exploratory runs, which preserves the historical ``NOT_SUPPORTED`` result;
    empirical callers must provide explicit ``data_mode`` and provenance.
    """
    mode = str(
        data_mode
        or (inversion.get("data_mode") if isinstance(inversion, Mapping) else None)
        or "synthetic"
    )
    provenance_value = provenance if provenance is not None else (
        inversion.get("provenance") if isinstance(inversion, Mapping) else None
    )
    validation = validate_falsification_input(
        signal,
        inversion,
        data_mode=mode,
        provenance=provenance_value,
        paired_subjects=paired_subjects,
    )
    if not validation["valid"] and (
        validation["sample_count"] == 0
        or not mode.lower().startswith("synthetic")
        or not isinstance(inversion, Mapping)
    ):
        return _comparison_error(
            data_mode=validation["data_mode"],
            provenance_status=validation["provenance_status"],
            validation=validation,
            error="comparison input is scientifically uninterpretable",
            status="INCONCLUSIVE",
        )
    try:
        y = np.asarray(signal, dtype=float).reshape(-1)
        if y.size < 8 or not np.all(np.isfinite(y)):
            raise ValueError("at least eight finite observations are required")
        x = np.linspace(0.0, 1.0, y.size)
        q_series = inversion.get("q_emp_series", inversion.get("topological_charge_series"))
        if q_series is None:
            topology = np.full(y.size, float(inversion.get("q_emp_mean", 0.0)))
        else:
            source = np.asarray(q_series, dtype=float).reshape(-1)
            if source.size < 2 or not np.all(np.isfinite(source)):
                raise ValueError("topological series must contain at least two finite values")
            topology = np.interp(x, np.linspace(0.0, 1.0, source.size), source)
        signal_static = bool(np.ptp(y) <= 1e-12)
        topology_static = bool(np.ptp(topology) <= 1e-12)
        topological = np.column_stack(
            [np.ones(y.size), x, np.sin(2 * np.pi * x), np.cos(2 * np.pi * x), topology]
        )
        classical = np.column_stack(
            [np.ones(y.size), x, np.sin(2 * np.pi * x), np.cos(2 * np.pi * x)]
        )
        pred_q, beta_q = _fit_l1(y, topological, topological_l1_penalty)
        pred_c, beta_c = _fit_linear(y, classical)
        rss_q = float(np.sum((y - pred_q) ** 2))
        rss_c = float(np.sum((y - pred_c) ** 2))
        active_q = int(1 + np.count_nonzero(np.abs(beta_q[1:]) > 1e-12))
        if rss_q <= 0 or rss_c <= 0:
            # A perfect/constant fit has no estimable residual variance. Keep
            # the descriptive legacy fields, but do not invent an infinite K.
            proxy = {
                "method": "rss_ratio_proxy",
                "formal": False,
                "k_value": None,
                "log_k_value": None,
                "rss_likelihood_log_ratio": None,
                "sample_count": y.size,
                "model": {"rss": rss_q, "aic": float("inf"), "aicc": float("inf")},
                "null": {"rss": rss_c, "aic": float("inf"), "aicc": float("inf")},
                "uncertainty": {"available": False, "reason": "zero residual variance is not identifiable"},
                "warnings": ["Residual variance is zero or degenerate; K is unavailable."],
            }
        else:
            # Gaussian residual variance is an estimated nuisance parameter in
            # both models, so it is included in each AIC/AICc parameter count.
            proxy = bayes_factor_proxy_from_rss(rss_q, rss_c, y.size, active_q + 1, classical.shape[1] + 1)
        topological_active = bool(not topology_static and abs(beta_q[-1]) > 1e-12)
        controls_value = controls or {}
        status = classify_falsification_status(
            proxy,
            threshold=PASS_THRESHOLD,
            data_mode=mode,
            provenance_status=validation["provenance_status"],
            analysis_interpretable=not signal_static and topological_active,
            controls=controls_value,
            # Only the method actually executed can affect the verdict. A
            # caller cannot relabel an RSS proxy as a formal comparison.
            method=proxy["method"],
            model_comparison_supported=True,
            validation_status=validation["status"],
        )
        warnings = list(validation["warnings"]) + list(proxy["warnings"])
        if method != proxy["method"]:
            warnings.append(f"declared method {method!r} was not executed; RSS proxy was computed")
        errors = list(validation["errors"])
        return {
            "status": status,
            "method": proxy["method"],
            "declared_method": method,
            "k_value": proxy["k_value"],
            "threshold": PASS_THRESHOLD,
            "data_mode": validation["data_mode"],
            "provenance_status": validation["provenance_status"],
            "sample_count": y.size,
            "feature_count": 1,
            "uncertainty": proxy["uncertainty"],
            "controls": controls_value,
            "warnings": warnings,
            "errors": errors,
            "pitnn": {
                "rss": rss_q,
                "aic": proxy["model"]["aic"],
                "aicc": proxy["model"]["aicc"],
                "topological_l1_penalty": topological_l1_penalty,
                "topological_weight": float(beta_q[-1]),
                "topological_feature_static": topology_static,
                "topological_feature_active": topological_active,
                "active_parameters": active_q,
                "parameter_count_including_noise_variance": active_q + 1,
            },
            "classical_wilson_cowan": {
                "rss": rss_c,
                "aic": proxy["null"]["aic"],
                "aicc": proxy["null"]["aicc"],
                "mean_parameter_count": classical.shape[1],
                "parameter_count_including_noise_variance": classical.shape[1] + 1,
                "coefficients": beta_c.tolist(),
            },
            "log_bayes_factor": proxy["log_k_value"] if proxy["log_k_value"] is not None else 0.0,
            "bayes_factor": proxy["k_value"] if proxy["k_value"] is not None else 0.0,
            "rss_likelihood_log_ratio": proxy["rss_likelihood_log_ratio"],
            "signal_static": signal_static,
            "evidence_eligible": status == "PASS",
            "verdict": status,
        }
    except (TypeError, ValueError, FloatingPointError, OverflowError) as exc:
        return _comparison_error(
            data_mode=validation["data_mode"],
            provenance_status=validation["provenance_status"],
            validation=validation,
            error=str(exc),
        )
