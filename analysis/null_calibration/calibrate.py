"""Run a seeded null calibration and emit a descriptive report.

The report is never a scientific PASS. It does not write K or a
falsification verdict.
"""
from __future__ import annotations

import math
import random
from typing import Any, Mapping

from . import models
from .json_util import NonFiniteJsonError, assert_finite_or_null, finite_or_none
from .metrics import mean_difference, mean_statistic, normalize_metric_family
from .schema import (
    AUDITOR_ID,
    AUDITOR_VERSION,
    CALIBRATION_STATUS,
    CORRECTION_METHODS,
    MIN_REPLICATES_HARD,
    MIN_REPLICATES_WARN,
    NULL_MODELS,
    SCHEMA_ID,
)
from .statistics import (
    correct_p,
    effective_sample_size,
    empirical_percentile,
    exceedance_count,
    permutation_p_value,
)


def _as_float_list(values: Any, name: str) -> list[float]:
    if values is None:
        raise ValueError(f"{name} is required")
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"{name} must be a list")
    out: list[float] = []
    for item in values:
        number = finite_or_none(item)
        if number is None:
            raise ValueError(f"{name} contains a non-finite or non-numeric value")
        out.append(number)
    return out


def _warnings_for_model(model: str) -> list[str]:
    notes: list[str] = []
    if not models.PRESERVES_VARIANCE.get(model, False):
        notes.append(f"{model} does not preserve observed variance")
    if not models.PRESERVES_AUTOCORR.get(model, False):
        notes.append(f"{model} does not preserve lag-1 autocorrelation")
    return notes


def _error_report(spec: Mapping[str, Any], errors: list[str], *, seed=None, model=None, metric=None) -> dict[str, Any]:
    report = {
        "ok": False,
        "schema": SCHEMA_ID,
        "auditor": AUDITOR_ID,
        "version": AUDITOR_VERSION,
        "status": "ERROR",
        "scientific_pass": False,
        "formal_biological_evidence": False,
        "k_value": None,
        "falsification_verdict": None,
        "metric_family": metric or normalize_metric_family(spec.get("metric_family")),
        "null_model": model or spec.get("null_model"),
        "n_replicates": 0,
        "n_replicates_requested": spec.get("n_replicates"),
        "n_failed": 0,
        "n_skipped": 0,
        "seed": seed if seed is not None else spec.get("seed"),
        "observed_statistic": finite_or_none(spec.get("observed_statistic")),
        "null_mean": None,
        "null_variance": None,
        "empirical_percentile": None,
        "exceedance_count": None,
        "permutation_p_value": None,
        "correction_method": spec.get("correction_method") or "none",
        "n_tests": spec.get("n_tests"),
        "multiplicity_status": "unknown",
        "p_value_corrected": None,
        "effective_sample_size": None,
        "finite_value_status": False,
        "provenance": spec.get("provenance"),
        "synthetic_demo": bool(spec.get("synthetic_demo", True)),
        "parameters": {},
        "failed_replicates": [],
        "skipped_replicates": [],
        "warnings": [],
        "errors": errors,
        "limitations": [
            "Null calibration is a synthetic demonstration of test behavior.",
            "It cannot create a scientific PASS.",
        ],
    }
    assert_finite_or_null(report)
    return report


def calibrate(spec: Mapping[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    model = str(spec.get("null_model") or spec.get("model") or "").strip()
    if model not in NULL_MODELS:
        return _error_report(spec, [f"unsupported null_model: {model or 'missing'}"])

    metric = normalize_metric_family(spec.get("metric_family") or spec.get("metric"))
    try:
        seed = int(spec.get("seed", 0))
    except (TypeError, ValueError):
        return _error_report(spec, [f"seed must be an integer, received {spec.get('seed')!r}"])
    try:
        n_replicates = int(spec.get("n_replicates") or spec.get("replicates") or 0)
    except (TypeError, ValueError):
        return _error_report(spec, ["n_replicates must be an integer"])

    tails = str(spec.get("tails") or "two").lower()
    if tails not in {"two", "greater", "less"}:
        tails = "two"
    correction = str(spec.get("correction_method") or spec.get("correction") or "none").lower()
    if correction not in CORRECTION_METHODS:
        warnings.append(f"unknown correction_method {correction!r}; recorded as none")
        correction = "none"
    n_tests = spec.get("n_tests")
    provenance = spec.get("provenance") or spec.get("provenance_reference")
    if provenance in ("", "unknown", "missing"):
        provenance = None
    synthetic_demo = bool(spec.get("synthetic_demo", True))
    observed = finite_or_none(spec.get("observed_statistic"))
    if spec.get("observed_statistic") is not None and observed is None:
        errors.append("observed_statistic is non-finite")

    rng = random.Random(seed)
    nulls: list[float] = []
    parameters = {
        "null_model": model,
        "seed": seed,
        "n_replicates_requested": n_replicates,
        "tails": tails,
        "block_size": spec.get("block_size", 4),
        "metric_family": metric,
    }
    try:
        if model == "label_permutation":
            group_a = _as_float_list(spec.get("group_a"), "group_a")
            group_b = _as_float_list(spec.get("group_b"), "group_b")
            if observed is None:
                observed = mean_difference(group_a, group_b)
            for index in range(max(n_replicates, 0)):
                try:
                    a_p, b_p = models.generate_label_permutation(group_a, group_b, rng)
                    stat = mean_difference(a_p, b_p)
                    if not math.isfinite(stat):
                        raise ValueError("non-finite replicate statistic")
                    nulls.append(float(stat))
                except Exception as exc:
                    failed.append({"replicate": index, "reason": str(exc)})
            series_for_ess = group_a + group_b
        else:
            series = _as_float_list(spec.get("observations") or spec.get("series"), "observations")
            if observed is None:
                observed = mean_statistic(series)
            generator = models.GENERATORS[model]
            extra = {}
            if model == "block_shuffle":
                extra["block_size"] = int(spec.get("block_size") or 4)
            for index in range(max(n_replicates, 0)):
                try:
                    surrogate = generator(series, rng, **extra)
                    stat = mean_statistic(surrogate)
                    if not math.isfinite(stat):
                        raise ValueError("non-finite replicate statistic")
                    nulls.append(float(stat))
                except Exception as exc:
                    failed.append({"replicate": index, "reason": str(exc)})
            series_for_ess = series
            if model == "matched_autocorrelation" and models.lag1_corr(series) is None:
                warnings.append("matched_autocorrelation fell back to matched-variance Gaussian noise")
    except ValueError as exc:
        return _error_report(spec, [str(exc)], seed=seed, model=model, metric=metric)

    if n_replicates < MIN_REPLICATES_HARD:
        warnings.append(f"n_replicates={n_replicates} is below the hard minimum {MIN_REPLICATES_HARD}")
    if n_replicates < MIN_REPLICATES_WARN:
        warnings.append(f"n_replicates={n_replicates} is below the recommended minimum {MIN_REPLICATES_WARN}")
    warnings.extend(_warnings_for_model(model))

    finite_status = all(math.isfinite(v) for v in nulls) and (observed is None or math.isfinite(observed))
    n_ok = len(nulls)
    null_mean = sum(nulls) / n_ok if n_ok else None
    if n_ok >= 2 and null_mean is not None:
        null_var = sum((v - null_mean) ** 2 for v in nulls) / (n_ok - 1)
    elif n_ok == 1:
        null_var = 0.0
    else:
        null_var = None
    lag1 = models.lag1_corr(series_for_ess) if series_for_ess else None
    ess = effective_sample_size(len(series_for_ess), lag1) if series_for_ess else None
    p_raw = permutation_p_value(observed, nulls, tails=tails)
    multiplicity = correct_p(p_raw, method=correction, n_tests=n_tests)

    if errors:
        status = "ERROR"
    elif n_ok < MIN_REPLICATES_HARD:
        status = "INSUFFICIENT"
        warnings.append("too few successful replicates to interpret the null distribution")
    else:
        status = "CALIBRATION_ONLY"
    if status not in CALIBRATION_STATUS:
        status = "ERROR"

    report = {
        "ok": status in {"CALIBRATION_ONLY", "INSUFFICIENT"} and not errors,
        "schema": SCHEMA_ID,
        "auditor": AUDITOR_ID,
        "version": AUDITOR_VERSION,
        "status": status,
        "scientific_pass": False,
        "formal_biological_evidence": False,
        "k_value": None,
        "falsification_verdict": None,
        "metric_family": metric,
        "null_model": model,
        "n_replicates": n_ok,
        "n_replicates_requested": n_replicates,
        "n_failed": len(failed),
        "n_skipped": len(skipped),
        "seed": seed,
        "observed_statistic": observed,
        "null_mean": finite_or_none(null_mean),
        "null_variance": finite_or_none(null_var),
        "empirical_percentile": empirical_percentile(observed, nulls),
        "exceedance_count": exceedance_count(observed, nulls, tails=tails),
        "permutation_p_value": p_raw,
        "correction_method": multiplicity["correction_method"],
        "n_tests": multiplicity["n_tests"],
        "multiplicity_status": multiplicity["multiplicity_status"],
        "p_value_corrected": multiplicity["p_value_corrected"],
        "effective_sample_size": ess,
        "finite_value_status": bool(finite_status and observed is not None),
        "provenance": provenance,
        "synthetic_demo": synthetic_demo,
        "parameters": parameters,
        "failed_replicates": failed,
        "skipped_replicates": skipped,
        "warnings": warnings,
        "errors": errors,
        "limitations": [
            "Null calibration is a synthetic demonstration of test behavior.",
            "It cannot create a scientific PASS.",
            "It does not modify K or falsification verdicts.",
            "graph_beta1, spatial_winding_q, and scalar_chirality remain distinct families.",
            "A small permutation p-value under a synthetic null is not biological confirmation.",
        ],
    }
    assert_finite_or_null(report)
    return report


def calibrate_payload(payload: Any) -> dict[str, Any]:
    assert_finite_or_null(payload, path="$.input")
    if not isinstance(payload, Mapping):
        raise ValueError("input must be a JSON object")
    if "calibrations" in payload and isinstance(payload["calibrations"], list):
        runs = [calibrate(item) for item in payload["calibrations"]]
        bundle = {
            "ok": all(item.get("ok") for item in runs),
            "schema": SCHEMA_ID,
            "auditor": AUDITOR_ID,
            "version": AUDITOR_VERSION,
            "scientific_pass": False,
            "k_value": None,
            "falsification_verdict": None,
            "n_runs": len(runs),
            "runs": runs,
        }
        assert_finite_or_null(bundle)
        return bundle
    return calibrate(payload)


def load_and_calibrate(text: str) -> dict[str, Any]:
    import json
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"input is not valid JSON: {exc}") from exc
    try:
        return calibrate_payload(payload)
    except NonFiniteJsonError as exc:
        raise ValueError(str(exc)) from exc
