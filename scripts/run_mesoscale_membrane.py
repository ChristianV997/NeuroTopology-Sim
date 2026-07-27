"""Run the explicit phenomenological quantum-metric to membrane-noise bridge."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from sim.pitnn.mesoscale_membrane import MesoscaleConfig, membrane_current_variance, simulate_fluctuation_biased_fhn


def _safe(value: Any) -> Any:
    if isinstance(value, np.ndarray): return _safe(value.tolist())
    if isinstance(value, (float, np.floating)): return float(value) if np.isfinite(value) else None
    if isinstance(value, dict): return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_safe(v) for v in value]
    return value


def run(tau_s: float, coupling: float, seed: int, output_dir: Path) -> dict[str, Any]:
    """Create an auditable mesoscale sensitivity artifact; all values are local model outputs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    variance = membrane_current_variance(tau_s, coupling=coupling)
    result = simulate_fluctuation_biased_fhn(variance, MesoscaleConfig(coupling=coupling, seed=seed))
    payload = {"schema": "PITNN.MesoscaleMembraneBridge.v1", "source": "finite_model_metric",
               "input_decoherence_time_s": tau_s, "current_variance_proxy": variance,
               "baseline_threshold_crossing_fraction": float(np.mean(result["baseline_voltage_V"] >= -0.020)),
               "perturbed_threshold_crossing_fraction": result["threshold_crossing_fraction"],
               "threshold_crossing_shift": float(result["threshold_crossing_fraction"] - np.mean(result["baseline_voltage_V"] >= -0.020)),
               "scientific_note": "Phenomenological sensitivity mapping only; it neither derives neural voltage noise from quantum mechanics nor constitutes biological evidence."}
    fd, temporary = tempfile.mkstemp(dir=output_dir, prefix="mesoscale_", suffix=".tmp"); os.close(fd)
    try:
        Path(temporary).write_text(json.dumps(_safe(payload), indent=2, allow_nan=False) + "\n", encoding="utf-8")
        os.replace(temporary, output_dir / "mesoscale_membrane_summary.json")
    finally: Path(temporary).unlink(missing_ok=True)
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--tau-s", type=float, default=0.95e-9)
    parser.add_argument("--coupling", type=float, default=1e-7); parser.add_argument("--seed", type=int, default=20260726)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/pitnn/mesoscale_membrane")); args = parser.parse_args()
    print(json.dumps(run(args.tau_s, args.coupling, args.seed, args.output_dir)))
