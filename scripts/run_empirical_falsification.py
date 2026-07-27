"""Run an offline empirical PITNN falsification workflow with optional RG flow."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from typing import Any
import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path: sys.path.insert(0, str(_ROOT))
from sim.pitnn.api_bridge import export_falsification_payload
from sim.pitnn.bayesian_falsification import compare_models
from sim.pitnn.empirical_pipeline import EmpiricalCondition, generate_mock_conditions, standardize_condition
from sim.pitnn.ingest_empirical import empirical_to_macro_signal, ingest_conditions
from sim.pitnn.mumax3_macro_tda import invert_macro_signal, invert_macro_signal_accelerated, invert_rg_magnetization
from sim.pitnn.rg_coarse_graining import block_spin_decimate, temporal_rescale
from sim.pitnn.topological_invariants import TopologicalInvariantTracker


def _rg_condition(condition: EmpiricalCondition, block_size: int) -> dict[str, Any]:
    """Map analytic EEG phase to a unit-vector field, then apply Kadanoff RG."""
    if block_size < 1: return {}
    phase, amplitude = condition.signal.phase, condition.signal.data
    field = np.stack((np.cos(phase), np.sin(phase), np.tanh(amplitude)), axis=2)
    field /= np.maximum(np.linalg.norm(field, axis=2, keepdims=True), np.finfo(float).eps)
    times = np.arange(field.shape[0], dtype=float) / condition.signal.sample_rate_hz
    coarse = block_spin_decimate(field, block_size, normalize=True)
    scaled_times = temporal_rescale(times, block_size)
    if coarse.shape[1] < 3: raise ValueError("RG block size leaves fewer than three sites")
    tracker = TopologicalInvariantTracker(coarse.shape[1])
    trace = [tracker.audit_snapshot(frame) for frame in coarse]
    inversion = invert_rg_magnetization(field, times, condition.signal.sample_rate_hz, block_size)
    return {"block_size": int(block_size), "coarse_shape": list(coarse.shape), "time_end_s": float(scaled_times[-1]),
            "mean_winding": float(np.mean([item["winding_number"] for item in trace])),
            "mean_q": float(np.mean([item["topological_charge"] for item in trace])),
            "mean_beta1": float(np.mean([item["beta1_loops"] for item in trace])),
            "inversion": inversion, "topology_trace": trace}


def _condition_result(condition: EmpiricalCondition, sample_rate_hz: float, fast_tda: bool, rg_block_size: int) -> dict[str, Any]:
    macro = empirical_to_macro_signal(condition.signal)
    inversion = (invert_macro_signal_accelerated if fast_tda else invert_macro_signal)(macro, sample_rate_hz)
    result = {"topology": condition.summary(), "inversion": inversion, "comparison": compare_models(macro, inversion)}
    if rg_block_size: result["rg"] = _rg_condition(condition, rg_block_size)
    return result


def run_empirical_falsification(input_file: str | Path | None = None, condition_a_label: str = "awake", condition_b_label: str = "sedated", sample_rate_hz: float = 250.0, output_dir: str | Path = "artifacts/pitnn", fast_tda: bool = False, seed: int = 0, rg_block_size: int = 0) -> dict[str, Any]:
    """Execute a reproducible two-condition report; PASS remains strictly K>100."""
    if sample_rate_hz <= 0 or rg_block_size < 0: raise ValueError("sample rate must be positive and RG block size non-negative")
    if input_file is None:
        conditions, source_kind = generate_mock_conditions(sample_rate_hz=sample_rate_hz, seed=seed), "synthetic_demo"
    else:
        first, second, source_kind = ingest_conditions(input_file, sample_rate_hz, condition_a_label, condition_b_label)
        conditions = {condition_a_label: standardize_condition(first, sample_rate_hz, condition_a_label, source_kind=source_kind), condition_b_label: standardize_condition(second, sample_rate_hz, condition_b_label, source_kind=source_kind)}
    labels = list(conditions)
    state_a, state_b = (_condition_result(conditions[label], sample_rate_hz, fast_tda, rg_block_size) for label in labels)
    combined = np.concatenate((empirical_to_macro_signal(conditions[labels[0]].signal), empirical_to_macro_signal(conditions[labels[1]].signal)))
    combined_inversion = (invert_macro_signal_accelerated if fast_tda else invert_macro_signal)(combined, sample_rate_hz)
    comparison = compare_models(combined, combined_inversion)
    report: dict[str, Any] = {"schema": "PITNN.EmpiricalFalsificationReport.v1", "source_kind": source_kind, "input_file": None if input_file is None else str(Path(input_file)), "sample_rate_hz": float(sample_rate_hz), "condition_labels": labels, "conditions": {labels[0]: state_a, labels[1]: state_b}, "comparison": comparison, "bayes_factor": float(comparison["bayes_factor"]), "delta_aicc": float(comparison["classical_wilson_cowan"]["aicc"] - comparison["pitnn"]["aicc"]), "verdict": comparison["verdict"], "rg_block_size": int(rg_block_size), "scientific_note": "Local computational metrics only; PASS is reserved strictly for K > 100."}
    destination = Path(output_dir); destination.mkdir(parents=True, exist_ok=True)
    report_path = destination / "empirical_falsification_report.json"; report["report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    (destination / "falsification_summary.json").write_text(json.dumps(export_falsification_payload(report), indent=2, sort_keys=True), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file", type=Path); parser.add_argument("--condition-a-label", default="awake"); parser.add_argument("--condition-b-label", default="sedated")
    parser.add_argument("--sample-rate-hz", type=float, default=250.0); parser.add_argument("--output-dir", type=Path, default=Path("artifacts/pitnn")); parser.add_argument("--fast-tda", action="store_true"); parser.add_argument("--seed", type=int, default=0); parser.add_argument("--rg-block-size", type=int, default=0)
    args = parser.parse_args(); report = run_empirical_falsification(**vars(args))
    print(json.dumps({"verdict": report["verdict"], "bayes_factor": report["bayes_factor"], "report_path": report["report_path"]}, sort_keys=True)); return 0
if __name__ == "__main__": raise SystemExit(main())
