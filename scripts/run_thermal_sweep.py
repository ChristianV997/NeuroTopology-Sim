"""Run a fail-closed DM1 thermal sweep with clearly labelled local fallback.

Cloud execution is attempted only after AWS credentials and the configured S3
bucket pass preflight.  When that is unavailable, this script writes a local
Lindblad-reference result for engineering comparison; it is never labelled as
cloud evidence or as a hypothesis verdict.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys
import time
from typing import Any, Iterable

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from physics.exact_dynamics.aws_routing import resolve_s3_routing
from physics.exact_dynamics.cloud_snapshot import CloudSnapshot, load_cloud_snapshot
from physics.exact_dynamics.lindblad_reference import LindbladReferenceConfig, propagate_lindblad
from physics.exact_dynamics.qpu_cloud_runner import HBAR_J_S, QpuCloudConfig, QuantumCloudEvaluator
from physics.exact_dynamics.telemetry import write_telemetry


def relaxation_time_s(temperature_K: float) -> float:
    """Phenomenological relaxation interpolation in SI seconds: 1.76 ns to 0.95 ns."""
    if not np.isfinite(temperature_K) or temperature_K <= 0:
        raise ValueError("temperature_K must be finite and positive")
    fraction = float(np.clip((temperature_K - 10.0) / 300.0, 0.0, 1.0))
    return 1.76e-9 * (1.0 - fraction) + 0.95e-9 * fraction


def _density_record(density: np.ndarray) -> dict[str, object]:
    eigenvalues = np.linalg.eigvalsh(density).real
    return {
        "trace": float(np.trace(density).real),
        "hermiticity_residual": float(np.linalg.norm(density - density.conj().T)),
        "minimum_eigenvalue": float(np.min(eigenvalues)),
        "matrix_real": density.real.tolist(),
        "matrix_imag": density.imag.tolist(),
    }


def _current_values(snapshot: CloudSnapshot, density: np.ndarray) -> list[float]:
    """Return tight-binding probability-current proxies in s^-1 for active edges."""
    values: list[float] = []
    for left, right in snapshot.active_site_pairs:
        values.append(float(2.0 * np.imag(snapshot.hamiltonian_J[left, right] * density[right, left]) / HBAR_J_S))
    return values


def _local_reference(snapshot: CloudSnapshot, times_s: np.ndarray, tau_s: float, reason: str) -> dict[str, object]:
    initial = np.zeros_like(snapshot.hamiltonian_J, dtype=complex)
    initial[0, 0] = 1.0
    states = propagate_lindblad(snapshot.hamiltonian_J, initial, times_s, LindbladReferenceConfig(tau_s))
    currents = [_current_values(snapshot, state) for state in states]
    return {
        "verdict": "LOCAL_REFERENCE_ONLY",
        "execution_mode": "local_lindblad_fallback",
        "fallback_reason": reason,
        "time_span_s": [float(times_s.min()), float(times_s.max())],
        "time_points_s": times_s.tolist(),
        "density_matrix_telemetry": [_density_record(state) for state in states],
        "chiral_current_expectation_values": currents,
        "chiral_current_degradation_proxy": float(np.linalg.norm(currents[-1])) if currents else 0.0,
        "execution_cost": {"simulator_cost_usd": 0.0, "qpu_cost_usd": 0.0, "task_statistics": {}},
        "scientific_note": "Local Lindblad reference fallback after failed AWS/S3 preflight or DM1 task. It is not cloud execution and does not model non-Markovian memory.",
    }


def run_thermal_sweep(snapshot_path: Path, temperatures_K: Iterable[float], output_dir: Path, *, s3_bucket: str | None = None, s3_prefix: str = "sciencerd/dm1", allow_local_fallback: bool = True, poll_timeout_s: float = 900.0) -> dict[str, object]:
    """Run each requested temperature; record cloud/fallback provenance per node."""
    snapshot = load_cloud_snapshot(snapshot_path)
    temperatures = np.asarray(list(temperatures_K), dtype=float)
    if temperatures.ndim != 1 or not temperatures.size or not np.all(np.isfinite(temperatures)) or np.any(temperatures <= 0):
        raise ValueError("temperatures_K must be a non-empty sequence of positive finite kelvin values")
    try:
        routing = resolve_s3_routing(bucket=s3_bucket, prefix=s3_prefix, run_label="thermal-sweep")
        routing_payload: dict[str, object] = {"bucket": routing.bucket, "prefix": routing.prefix, "region": routing.region, "account_id": routing.account_id, "bucket_created": routing.bucket_created}
        preflight_error: str | None = None
    except Exception as exc:
        routing = None
        routing_payload = {"status": "failed"}
        preflight_error = str(exc)
        if not allow_local_fallback:
            write_telemetry(output_dir / "cloud_failure.json", {"schema": "ScienceR-Dsim.CloudThermalFailure.v1", "error": preflight_error})
            raise
    records: list[dict[str, object]] = []
    for index, temperature in enumerate(temperatures):
        tau_s = relaxation_time_s(float(temperature))
        times = np.array([0.0, tau_s], dtype=float)
        started = time.monotonic()
        if routing is None:
            telemetry = _local_reference(snapshot, times, tau_s, preflight_error or "AWS preflight unavailable")
        else:
            config = QpuCloudConfig(temperature_K=float(temperature), relaxation_time_s=tau_s, s3_destination_folder=routing.destination_folder, chiral_pairs=snapshot.active_site_pairs, poll_timeout_s=poll_timeout_s)
            try:
                telemetry = QuantumCloudEvaluator(snapshot.source_path, config).run(times)
            except Exception as exc:
                if not allow_local_fallback:
                    write_telemetry(output_dir / "cloud_failure.json", {"schema": "ScienceR-Dsim.CloudThermalFailure.v1", "temperature_K": float(temperature), "error": str(exc)})
                    raise
                telemetry = _local_reference(snapshot, times, tau_s, str(exc))
        records.append({"index": index, "temperature_K": float(temperature), "relaxation_time_s": tau_s, "wall_duration_s": float(time.monotonic() - started), "telemetry": telemetry})
    payload: dict[str, object] = {
        "schema": "ScienceR-Dsim.CloudThermalSweep.v1",
        "snapshot_path": str(snapshot.source_path),
        "snapshot_checksum_sha256": snapshot.checksum_sha256,
        "s3_routing": routing_payload,
        "records": records,
        "scientific_note": "Temperature anchors are phenomenological. QPU results validate the requested DM1 circuit only; fallback results are local references and neither establishes biological coherence nor bypasses falsification.",
    }
    write_telemetry(output_dir / "thermal_sweep_summary.json", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/telemetry"))
    parser.add_argument("--steps", type=int, default=16)
    parser.add_argument("--s3-bucket")
    parser.add_argument("--s3-prefix", default="sciencerd/dm1")
    parser.add_argument("--poll-timeout-s", type=float, default=900.0)
    parser.add_argument("--no-local-fallback", action="store_true")
    args = parser.parse_args()
    if args.steps < 2:
        parser.error("--steps must be at least two")
    payload = run_thermal_sweep(args.snapshot, np.linspace(10.0, 310.0, args.steps), args.output_dir, s3_bucket=args.s3_bucket, s3_prefix=args.s3_prefix, allow_local_fallback=not args.no_local_fallback, poll_timeout_s=args.poll_timeout_s)
    print(payload["records"][-1]["telemetry"]["verdict"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
