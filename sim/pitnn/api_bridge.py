"""Offline dashboard payload contracts for PITNN artifacts.

The bridge has no dependency on ScienceR-Dsim.  Vector fields remain binary
NPZ arrays; JSON payloads contain compact metadata and scalar dashboard series.
"""
from __future__ import annotations

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
    return {"schema": "PITNN.DSIM.TopologyTrace.v1", "timestamps_s": timestamps,
            "winding_number": winding, "topological_charge": charge, "beta1_loops": beta1,
            "sample_count": len(entries)}


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
    """Extract the falsification contract without changing its K>100 gate."""
    comparison = falsification_report.get("comparison", falsification_report)
    pitnn = comparison.get("pitnn", {})
    classical = comparison.get("classical_wilson_cowan", {})
    bayes_factor = _json_float(falsification_report.get("bayes_factor", comparison.get("bayes_factor", 0.0)))
    verdict = str(falsification_report.get("verdict", comparison.get("verdict", "NOT_SUPPORTED")))
    if verdict not in {"PASS", "NOT_SUPPORTED"}:
        raise ValueError("verdict must be PASS or NOT_SUPPORTED")
    return {"schema": "PITNN.DSIM.Falsification.v1", "verdict": verdict, "threshold": _json_float(comparison.get("threshold", 100.0)),
            "bayes_factor": bayes_factor, "log_bayes_factor": _json_float(comparison.get("log_bayes_factor", 0.0)),
            "pitnn": {"rss": _json_float(pitnn.get("rss", 0.0)), "aicc": _json_float(pitnn.get("aicc", 0.0))},
            "classical_wilson_cowan": {"rss": _json_float(classical.get("rss", 0.0)), "aicc": _json_float(classical.get("aicc", 0.0))},
            "delta_aicc": _json_float(falsification_report.get("delta_aicc", classical.get("aicc", 0.0) - pitnn.get("aicc", 0.0))),
            "source_kind": str(falsification_report.get("source_kind", "unknown"))}
