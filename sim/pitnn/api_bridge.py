"""Offline dashboard payload contracts for PITNN artifacts.

The bridge has no dependency on ScienceR-Dsim.  Vector fields remain binary
NPZ arrays; JSON payloads contain compact metadata and scalar dashboard series.
"""
from __future__ import annotations

import json
import math
from typing import Any, Iterable, Mapping
import numpy as np


def _finite_array(value: Any, name: str, ndim: int | None = None) -> np.ndarray:
    array = np.asarray(value, dtype=float)
    if (ndim is not None and array.ndim != ndim) or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be finite" + (f" with {ndim} dimensions" if ndim is not None else ""))
    return array


def _json_float(value: Any) -> float:
    number = float(value)
    if not np.isfinite(number):
        raise ValueError("payload values must be finite")
    return number


def _finite_or_none(value: Any) -> float | None:
    """Convert scalar values without emitting JSON NaN/Infinity."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def json_safe(value: Any) -> Any:
    """Recursively convert artifact values to strict-JSON-compatible values.

    Non-finite numeric values become JSON ``null``. Arrays are kept out of the
    dashboard metadata by the export functions and written to NPZ references.
    """
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [json_safe(item) for item in sorted(value, key=str)]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if hasattr(value, "__fspath__"):
        return str(value)
    return str(value)


def canonical_json(value: Any) -> str:
    """Serialize an artifact deterministically with strict JSON semantics."""
    return json.dumps(
        json_safe(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


_FORMAL_EVIDENCE_METHODS = {
    "formal_bayes_factor",
    "formal_marginal_likelihood",
    "formal_marginal_likelihoods",
    "marginal_likelihood",
}
_PROXY_EVIDENCE_METHODS = {
    "aic_proxy",
    "aicc_proxy",
    "bic_proxy",
    "rss_proxy",
    "proxy_regression",
    "wilson_cowan_proxy_regression",
    "legacy_proxy_regression",
}


def _report_value(report: Mapping[str, Any], comparison: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in report:
            return report[key]
        if key in comparison:
            return comparison[key]
    return None


def _normalise_data_mode(report: Mapping[str, Any]) -> tuple[str, bool]:
    explicit_demo = report.get("synthetic_demo")
    raw = report.get("data_mode", report.get("data_status", report.get("source_kind", "unknown")))
    value = str(raw or "unknown").strip().lower()
    synthetic = bool(explicit_demo) or value.startswith(("synthetic", "fixture", "null", "surrogate"))
    if synthetic:
        return "synthetic", True
    if value.startswith(("empirical", "observed", "real", "local")):
        return "empirical", False
    return "unknown", False


def _provenance(report: Mapping[str, Any], mode: str) -> tuple[dict[str, Any], bool]:
    raw = report.get("empirical_provenance", report.get("provenance", {}))
    details = dict(raw) if isinstance(raw, Mapping) else {}
    if mode != "empirical":
        return {"status": "not_applicable", **details}, True
    declared = str(report.get("provenance_status", details.get("status", ""))).lower()
    required = ("dataset_id", "source", "sample_rate_hz")
    has_source = bool(details.get("source_file") or details.get("source_path") or details.get("uri"))
    complete = declared in {"complete", "valid"} and all(details.get(key) for key in required) and has_source
    details["status"] = "complete" if complete else "incomplete"
    return details, complete


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _extract_evidence_method(report: Mapping[str, Any], comparison: Mapping[str, Any]) -> tuple[str, str]:
    raw = _report_value(report, comparison, "evidence_method", "method")
    if raw is None:
        classical = comparison.get("classical_wilson_cowan", {})
        pitnn = comparison.get("pitnn", {})
        if isinstance(classical, Mapping) and isinstance(pitnn, Mapping) and (
            classical.get("likelihood_status") == "not_implemented"
            or classical.get("model_type") == "wilson_cowan_proxy_regression"
            or ("rss" in classical and "rss" in pitnn and "aicc" in classical and "aicc" in pitnn)
        ):
            return "legacy_proxy_regression", "proxy"
        if "comparison" in report and "bayes_factor" in report:
            return "unknown_legacy_numeric", "unknown"
        return "unknown", "unknown"
    method = str(raw).strip().lower()
    if method in _FORMAL_EVIDENCE_METHODS or report.get("evidence_kind") == "formal":
        return method, "formal"
    if method in _PROXY_EVIDENCE_METHODS or report.get("evidence_kind") == "proxy":
        return method, "proxy"
    if report.get("is_formal") is True and method not in {"unknown", "unknown_legacy_numeric"}:
        return method, "formal"
    if report.get("is_proxy") is True:
        return method, "proxy"
    return method, "unknown"


def _control_status(report: Mapping[str, Any]) -> tuple[Any, bool]:
    raw = report.get("null_control_status", report.get("controls", report.get("null_control_summary")))
    if raw is None:
        return {"status": "not_provided"}, False
    if isinstance(raw, Mapping):
        status = str(raw.get("status", "")).lower()
        passed = raw.get("passed") is True or status in {"pass", "passed", "valid"}
        return dict(raw), passed
    if isinstance(raw, bool):
        return {"status": "passed" if raw else "failed", "passed": raw}, raw
    status = str(raw).lower()
    return {"status": status}, status in {"pass", "passed", "valid"}


def _multiplicity_status(report: Mapping[str, Any]) -> str:
    raw = report.get("multiplicity_status", report.get("multiplicity_correction_status"))
    if raw is None:
        validation = report.get("validation", {})
        if isinstance(validation, Mapping):
            raw = validation.get("multiplicity_status")
    if isinstance(raw, Mapping):
        raw = raw.get("status")
    return str(raw or "unknown").lower()


def _reason_codes(
    *, report: Mapping[str, Any], method_kind: str, mode: str, synthetic: bool,
    provenance_complete: bool, sample_count: int | None,
    effective_sample_count: int | None, null_control_passed: bool,
    multiplicity_status: str, model_status: str, formal_value: float | None,
    proxy_value: float | None, threshold: float, verdict: str,
) -> list[str]:
    reasons = {str(item) for item in report.get("reason_codes", []) if item}
    if method_kind == "proxy":
        reasons.update({"PROXY_ONLY", "FORMAL_BAYES_FACTOR_UNAVAILABLE"})
    elif method_kind == "formal":
        reasons.add("FORMAL_EVIDENCE_AVAILABLE")
    else:
        reasons.add("UNKNOWN_EVIDENCE_METHOD")
    if synthetic:
        reasons.update({"SYNTHETIC_DATA", "SYNTHETIC_PASS_REJECTED"})
    elif mode == "empirical":
        reasons.add("EMPIRICAL_DATA")
    else:
        reasons.add("UNKNOWN_DATA_MODE")
    if not provenance_complete:
        reasons.add("INCOMPLETE_PROVENANCE")
    if sample_count is None:
        reasons.add("SAMPLE_COUNT_UNDECLARED")
    if effective_sample_count is None:
        reasons.add("EFFECTIVE_SAMPLE_COUNT_UNDECLARED")
    elif effective_sample_count < 8:
        reasons.add("INSUFFICIENT_SAMPLE_SIZE")
    if multiplicity_status in {"unknown", "missing", "invalid", "not_provided"}:
        reasons.add("MULTIPLICITY_UNDECLARED")
    if not null_control_passed:
        reasons.add("NULL_CONTROL_NOT_PASSED")
    if model_status in {"unknown", "unsupported", "proxy_regression"}:
        reasons.add("MODEL_COMPARISON_UNSUPPORTED" if model_status == "unsupported" else "MODEL_COMPARISON_PROXY")
    value = formal_value if method_kind == "formal" else proxy_value
    if value is None:
        reasons.add("K_UNAVAILABLE")
    elif value > threshold:
        reasons.add("K_ABOVE_THRESHOLD")
    elif value == threshold:
        reasons.add("K_AT_THRESHOLD")
    else:
        reasons.add("K_BELOW_THRESHOLD")
    if method_kind == "proxy":
        reasons.add("WILSON_COWAN_PROXY")
    if verdict == "ERROR":
        reasons.add("EXECUTION_ERROR")
    if verdict == "PASS":
        reasons.add("PASS_GATE_SATISFIED")
    reasons.add("LEGACY_NUMERIC_BAYES_FACTOR_DEPRECATED")
    return sorted(reasons)


def serialize_falsification_result(falsification_report: Mapping[str, Any]) -> dict[str, Any]:
    """Return an additive, JSON-safe falsification consumer envelope."""
    if not isinstance(falsification_report, Mapping):
        return json_safe({
            "semantic_schema": "PITNN.FalsificationConsumer.v1",
            "verdict": "ERROR",
            "scientific_eligibility": False,
            "reason_codes": ["INVALID_REPORT"],
        })
    comparison_raw = falsification_report.get("comparison", falsification_report)
    comparison = comparison_raw if isinstance(comparison_raw, Mapping) else {}
    mode, synthetic = _normalise_data_mode(falsification_report)
    provenance, provenance_complete = _provenance(falsification_report, mode)
    method, method_kind = _extract_evidence_method(falsification_report, comparison)
    threshold = _finite_or_none(_report_value(falsification_report, comparison, "threshold")) or 100.0
    # This adapter receives a caller-supplied mapping, not an independently
    # verified likelihood artifact.  Keep a diagnostic ratio separate, but
    # never expose it as a formal Bayes factor or use it to authorize PASS.
    unverified_formal_value = _finite_or_none(_report_value(falsification_report, comparison, "formal_bayes_factor")) if method_kind == "formal" else None
    if unverified_formal_value is None and method_kind == "formal":
        unverified_formal_value = _finite_or_none(falsification_report.get("k_value"))
    formal_value = None
    proxy_value = None
    if method_kind == "proxy":
        proxy_value = _finite_or_none(_report_value(falsification_report, comparison, "proxy_bayes_factor", "proxy_value", "k_value", "bayes_factor"))
    legacy_value = _finite_or_none(_report_value(falsification_report, comparison, "bayes_factor"))
    if legacy_value is None:
        legacy_value = unverified_formal_value if method_kind == "formal" else proxy_value
    sample_count = _positive_int(_report_value(falsification_report, comparison, "sample_count", "n"))
    effective = _positive_int(_report_value(falsification_report, comparison, "effective_sample_count", "n_eff"))
    controls, controls_passed = _control_status(falsification_report)
    multiplicity = _multiplicity_status(falsification_report)
    explicit_model_status = falsification_report.get("model_comparison_status")
    model_supported = falsification_report.get("model_comparison_supported")
    if explicit_model_status is not None:
        model_status = str(explicit_model_status).lower()
    elif method_kind == "formal" and model_supported is not False:
        model_status = "formal"
    elif method_kind == "proxy":
        model_status = "proxy_regression"
    else:
        model_status = "unknown"
    if model_supported is False:
        model_status = "unsupported"
    interpretable = falsification_report.get("analysis_interpretable", falsification_report.get("evidence_eligible"))
    if interpretable is None:
        interpretable = model_status == "formal"
    incoming_verdict = str(falsification_report.get("verdict", falsification_report.get("status", "INCONCLUSIVE"))).upper()
    if incoming_verdict not in {"PASS", "NOT_SUPPORTED", "INCONCLUSIVE", "ERROR"}:
        incoming_verdict = "ERROR"
    # No PASS route exists until an artifact-backed verifier is wired in.
    all_formal_gates = False
    if incoming_verdict == "ERROR":
        verdict = "ERROR"
    elif synthetic:
        verdict = "NOT_SUPPORTED"
    elif method_kind == "proxy":
        verdict = "NOT_SUPPORTED"
    elif method_kind != "formal":
        # Preserve an explicit legacy NOT_SUPPORTED classification when the
        # old artifact supplied no data-mode claim. A legacy PASS is never
        # preserved because a naked numeric field is not interpretable as
        # formal evidence.
        verdict = "NOT_SUPPORTED" if incoming_verdict == "NOT_SUPPORTED" and mode == "unknown" else "INCONCLUSIVE"
    elif unverified_formal_value is None:
        verdict = "INCONCLUSIVE"
    elif unverified_formal_value <= 100.0:
        verdict = "NOT_SUPPORTED"
    else:
        verdict = "INCONCLUSIVE"
    if incoming_verdict == "PASS" and verdict != "PASS" and synthetic:
        falsification_report = dict(falsification_report)
        falsification_report.setdefault("reason_codes", []).append("SYNTHETIC_PASS_REJECTED")
    reasons = _reason_codes(
        report=falsification_report, method_kind=method_kind, mode=mode,
        synthetic=synthetic, provenance_complete=provenance_complete,
        sample_count=sample_count, effective_sample_count=effective,
        null_control_passed=controls_passed, multiplicity_status=multiplicity,
        model_status=model_status, formal_value=formal_value,
        proxy_value=proxy_value, threshold=threshold, verdict=verdict,
    )
    if incoming_verdict == "PASS" and verdict != "PASS":
        reasons.append("INCOMING_PASS_REJECTED")
    semantic = {
        "semantic_schema": "PITNN.FalsificationConsumer.v1",
        "evidence_method": method,
        "proxy_bayes_factor": proxy_value,
        "formal_bayes_factor": None,
        "unverified_formal_ratio": unverified_formal_value,
        "bayes_factor_legacy_compatibility": {
            "value": legacy_value,
            "status": "deprecated_numeric_compatibility_alias",
            "deprecated": True,
            "interpretation": "formal" if method_kind == "formal" else "proxy" if method_kind == "proxy" else "unknown",
            "warning": "Do not interpret bayes_factor or unverified_formal_ratio as formal evidence; formal_bayes_factor remains null until independent artifact verification.",
        },
        "verdict": verdict,
        "scientific_eligibility": all_formal_gates,
        "synthetic_demo": synthetic,
        "empirical_provenance": provenance,
        "sample_count": sample_count,
        "effective_sample_count": effective,
        "null_control_status": controls,
        "multiplicity_status": multiplicity,
        "model_comparison_status": model_status,
        "reason_codes": sorted(set(reasons)),
        # Aliases retain the vocabulary used by PR #226 consumers.
        "evidence_kind": "formal" if method_kind == "formal" else "proxy" if method_kind == "proxy" else "unknown",
        "is_formal": method_kind == "formal",
        "is_proxy": method_kind == "proxy",
        "proxy_value": proxy_value,
        "legacy_bayes_factor_status": "deprecated_numeric_compatibility_alias",
        "legacy_bayes_factor_warning": "Do not interpret bayes_factor or unverified_formal_ratio as formal evidence; formal_bayes_factor remains null until independent artifact verification.",
        "data_status": mode,
        "provenance_status": provenance.get("status", "missing_or_incomplete"),
        "model_comparison_supported": model_status == "formal" or (method_kind == "proxy" and model_status == "proxy_regression"),
    }
    return json_safe(semantic)


def export_rg_magnetization_payload(
    M_field_history: np.ndarray,
    timestamps: np.ndarray,
    downsample_factor: int = 1,
) -> dict[str, Any]:
    """Create a JSON-safe heatmap/vector-field descriptor.

    ``M_field_history`` has shape ``(frames, sites, 3)`` and is downsampled on
    the frame axis only.  The returned payload deliberately omits the full
    vector tensor; callers write that tensor to NPZ through ``binary_arrays``.
    """
    field = _finite_array(M_field_history, "M_field_history", 3)
    times = _finite_array(timestamps, "timestamps", 1)
    if field.shape[2] != 3 or field.shape[0] != times.size:
        raise ValueError("field must have shape (frames, sites, 3) matching timestamps")
    if downsample_factor < 1:
        raise ValueError("downsample_factor must be positive")
    sampled = field[::downsample_factor]
    sampled_times = times[::downsample_factor]
    return {
        "schema": "PITNN.DSIM.RGMagnetization.v1",
        "units": {"time": "s", "magnetization": "model_unit"},
        "downsample_factor": int(downsample_factor),
        "frame_count": int(sampled.shape[0]),
        "site_count": int(sampled.shape[1]),
        "vector_components": 3,
        "timestamps_s": sampled_times.tolist(),
        "heatmap_sz": sampled[:, :, 2].T.tolist(),
        "binary_arrays": {"magnetization": "magnetization", "timestamps_s": "timestamps_s", "heatmap_sz": "heatmap_sz"},
    }


def rg_binary_arrays(M_field_history: np.ndarray, timestamps: np.ndarray, downsample_factor: int = 1) -> dict[str, np.ndarray]:
    """Return bounded, downsampled arrays for NPZ serialization."""
    field = _finite_array(M_field_history, "M_field_history", 3)
    times = _finite_array(timestamps, "timestamps", 1)
    if field.shape[2] != 3 or field.shape[0] != times.size or downsample_factor < 1:
        raise ValueError("invalid RG field, timestamps, or downsample factor")
    sampled = field[::downsample_factor]
    return {"magnetization": sampled, "timestamps_s": times[::downsample_factor], "heatmap_sz": sampled[:, :, 2].T}


def export_topology_trace_payload(topology_trace: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Format winding, charge, and beta-1 observations as dashboard series."""
    entries = list(topology_trace)
    if not entries:
        raise ValueError("topology_trace must not be empty")
    winding = [_json_float(item.get("winding_number", item.get("W", 0.0))) for item in entries]
    charge = [_json_float(item.get("topological_charge", item.get("Q", 0.0))) for item in entries]
    beta1 = [int(item.get("beta1_loops", item.get("beta_1", 0))) for item in entries]
    if any(value < 0 for value in beta1):
        raise ValueError("beta_1 values must be non-negative")
    timestamps = [_json_float(item.get("time_s", index)) for index, item in enumerate(entries)]
    payload = {"schema": "PITNN.DSIM.TopologyTrace.v1", "timestamps_s": timestamps,
               "winding_number": winding, "topological_charge": charge,
               "beta1_loops": beta1, "graph_beta1": beta1,
               "sample_count": len(entries)}
    if any("scalar_chirality" in item for item in entries):
        payload["scalar_chirality"] = [_finite_or_none(item.get("scalar_chirality")) for item in entries]
    return payload


def export_liouvillian_ep_payload(ep_results: Mapping[str, Any]) -> dict[str, Any]:
    """Format either a full EP grid or a scalar full-spectrum diagnostic."""
    pumps = ep_results.get("pump_values", ep_results.get("gamma_pump_values", []))
    losses = ep_results.get("loss_values", ep_results.get("gamma_loss_values", []))
    gaps = ep_results.get("gaps", ep_results.get("global_gaps"))
    payload: dict[str, Any] = {"schema": "PITNN.DSIM.LiouvillianEP.v1", "units": "s^-1"}
    if gaps is not None:
        gap_array = _finite_array(gaps, "gaps")
        if gap_array.ndim != 2:
            raise ValueError("EP gap grid must be two-dimensional")
        pump_array, loss_array = _finite_array(pumps, "pump_values", 1), _finite_array(losses, "loss_values", 1)
        if gap_array.shape != (pump_array.size, loss_array.size):
            raise ValueError("EP grid shape must match pump/loss axes")
        payload.update({"gamma_pump_s": pump_array.tolist(), "gamma_loss_s": loss_array.tolist(), "gap": gap_array.tolist(), "grid_shape": list(gap_array.shape)})
        if "fidelities" in ep_results:
            fidelity = _finite_array(ep_results["fidelities"], "fidelities", 2)
            if fidelity.shape != gap_array.shape: raise ValueError("fidelity grid shape mismatch")
            payload["eigenvector_fidelity"] = fidelity.tolist()
    else:
        payload.update({"gamma_pump_s": _json_float(ep_results.get("pump_s", 0.0)), "gamma_loss_s": _json_float(ep_results.get("loss_s", 0.0)),
                        "global_gap": _json_float(ep_results.get("global_gap", ep_results.get("gap", 0.0))),
                        "liouvillian_gap_proxy": _json_float(ep_results.get("liouvillian_gap_proxy", ep_results.get("gap", 0.0))),
                        "fidelity": _json_float(ep_results.get("fidelity", 0.0)),
                        "closest_pair": [int(value) for value in ep_results.get("closest_pair", [])]})
    return payload


def export_falsification_payload(falsification_report: Mapping[str, Any]) -> dict[str, Any]:
    """Extract a backward-compatible falsification payload with semantic fields."""
    comparison = falsification_report.get("comparison", falsification_report)
    if not isinstance(comparison, Mapping):
        comparison = {}
    pitnn = comparison.get("pitnn", {})
    classical = comparison.get("classical_wilson_cowan", {})
    if not isinstance(pitnn, Mapping):
        pitnn = {}
    if not isinstance(classical, Mapping):
        classical = {}
    semantic = serialize_falsification_result(falsification_report)
    legacy_bayes_factor = semantic["bayes_factor_legacy_compatibility"]["value"]
    classical_aicc = _finite_or_none(classical.get("aicc"))
    pitnn_aicc = _finite_or_none(pitnn.get("aicc"))
    delta_default = classical_aicc - pitnn_aicc if classical_aicc is not None and pitnn_aicc is not None else None
    payload = {
        "schema": "PITNN.DSIM.Falsification.v1",
        "verdict": semantic["verdict"],
        "threshold": _finite_or_none(comparison.get("threshold")) or 100.0,
        "bayes_factor": legacy_bayes_factor,
        "log_bayes_factor": _finite_or_none(comparison.get("log_bayes_factor")),
        "pitnn": {"rss": _finite_or_none(pitnn.get("rss")), "aicc": pitnn_aicc},
        "classical_wilson_cowan": {"rss": _finite_or_none(classical.get("rss")), "aicc": classical_aicc},
        "delta_aicc": _finite_or_none(falsification_report.get("delta_aicc", delta_default)),
        "source_kind": str(falsification_report.get("source_kind", "unknown")),
    }
    payload.update(semantic)
    return json_safe(payload)
