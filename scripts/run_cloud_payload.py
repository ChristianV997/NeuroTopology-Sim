"""Wire a validated local NPZ snapshot into DM1 and artifact telemetry."""
from __future__ import annotations
import argparse
from dataclasses import replace
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from physics.exact_dynamics.cloud_snapshot import load_cloud_snapshot
from physics.exact_dynamics.aws_routing import resolve_s3_routing
from physics.exact_dynamics.lindblad_reference import LindbladReferenceConfig, propagate_lindblad
from physics.exact_dynamics.qpu_cloud_runner import HBAR_J_S, QpuCloudConfig, QuantumCloudEvaluator
from physics.exact_dynamics.telemetry import write_telemetry


def _local_reference(snapshot, times_s: np.ndarray, config: QpuCloudConfig, reason: str) -> dict[str, object]:
    """Return an explicit local engineering reference after a cloud failure."""
    initial = np.zeros_like(snapshot.hamiltonian_J, dtype=complex); initial[0, 0] = 1.0
    tau = config.relaxation_time_s or 0.95e-9
    states = propagate_lindblad(snapshot.hamiltonian_J, initial, times_s, LindbladReferenceConfig(tau, config.phase_relaxation_ratio))
    density = []
    currents = []
    for state in states:
        density.append({"trace": float(np.trace(state).real), "hermiticity_residual": float(np.linalg.norm(state - state.conj().T)), "minimum_eigenvalue": float(np.min(np.linalg.eigvalsh(state).real)), "matrix_real": state.real.tolist(), "matrix_imag": state.imag.tolist()})
        currents.append([float(2.0 * np.imag(snapshot.hamiltonian_J[left, right] * state[right, left]) / HBAR_J_S) for left, right in snapshot.active_site_pairs])
    return {"verdict": "LOCAL_REFERENCE_ONLY", "execution_mode": "local_lindblad_fallback", "fallback_reason": reason,
            "time_span_s": [float(times_s.min()), float(times_s.max())], "time_points_s": times_s.tolist(),
            "density_matrix_telemetry": density, "chiral_current_expectation_values": currents,
            "execution_cost": {"simulator_cost_usd": 0.0, "qpu_cost_usd": 0.0, "task_statistics": {}},
            "scientific_note": "Local fallback following unavailable live DM1 execution. It is not cloud evidence and does not include non-Markovian memory."}


def run(snapshot_path: Path, times_s: np.ndarray, output_dir: Path, config: QpuCloudConfig = QpuCloudConfig(), *, preflight_s3: bool = True, s3_bucket: str | None = None, s3_prefix: str = "sciencerd/dm1", allow_local_fallback: bool = True) -> dict[str, object]:
    """Serialize validated input manifest, then cloud result telemetry after task completion."""
    try:
        snapshot = load_cloud_snapshot(snapshot_path)
        input_payload: dict[str, object] = {"schema": "ScienceR-Dsim.CloudInput.v1", "snapshot_path": str(snapshot.source_path),
            "snapshot_checksum_sha256": snapshot.checksum_sha256, "site_count": int(snapshot.hamiltonian_J.shape[0]),
            "boundary_configuration": snapshot.boundary_configuration, "active_site_pairs": [list(pair) for pair in snapshot.active_site_pairs],
            "time_points_s": np.asarray(times_s, float).tolist()}
        write_telemetry(output_dir / "cloud_input.json", input_payload)
    except Exception as exc:
        write_telemetry(output_dir / "cloud_failure.json", {"schema": "ScienceR-Dsim.CloudTelemetryFailure.v1", "snapshot_path": str(snapshot_path), "error_type": type(exc).__name__, "error": str(exc)})
        raise
    try:
        routing_payload: dict[str, object] | None = None
        if preflight_s3:
            routing = resolve_s3_routing(bucket=s3_bucket, prefix=s3_prefix, run_label="payload")
            config = replace(config, s3_destination_folder=routing.destination_folder)
            routing_payload = {"bucket": routing.bucket, "prefix": routing.prefix, "region": routing.region, "account_id": routing.account_id, "bucket_created": routing.bucket_created}
        evaluator = QuantumCloudEvaluator(snapshot.source_path, replace(config, chiral_pairs=snapshot.active_site_pairs))
        telemetry = evaluator.run(times_s)
        payload = {"schema": "ScienceR-Dsim.CloudTelemetry.v1", "input": input_payload, "s3_routing": routing_payload, "telemetry": telemetry}
        write_telemetry(output_dir / "cloud_telemetry.json", payload)
        return payload
    except Exception as exc:
        write_telemetry(output_dir / "cloud_failure.json", {"schema": "ScienceR-Dsim.CloudTelemetryFailure.v1", "snapshot_path": str(snapshot_path),
            "error_type": type(exc).__name__, "error": str(exc)})
        if not allow_local_fallback:
            raise
        telemetry = _local_reference(snapshot, np.asarray(times_s, float), config, str(exc))
        payload = {"schema": "ScienceR-Dsim.CloudTelemetry.v1", "input": input_payload, "s3_routing": {"status": "unavailable"}, "telemetry": telemetry}
        write_telemetry(output_dir / "cloud_telemetry.json", payload)
        return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--times-s", required=True, nargs="+", type=float); parser.add_argument("--output-dir", type=Path, default=Path("artifacts/telemetry"))
    parser.add_argument("--s3-bucket"); parser.add_argument("--s3-prefix", default="sciencerd/dm1"); args = parser.parse_args()
    run(args.snapshot, np.asarray(args.times_s), args.output_dir, QpuCloudConfig(), s3_bucket=args.s3_bucket, s3_prefix=args.s3_prefix)
