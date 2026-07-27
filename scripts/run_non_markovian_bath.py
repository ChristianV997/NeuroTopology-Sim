"""Run a bounded OQuPy Drude--Lorentz coherence falsification experiment.

This runner is deliberately conservative: it accepts a local SI Hamiltonian
snapshot but labels its result ``INCONCLUSIVE`` unless an independently
validated local QM/TD-DFT provenance record is supplied.  A surviving
coherence envelope is never emitted as affirmative biological evidence.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from physics.exact_dynamics.dynamics_solver import BathConfig, run_oqupy_pt_tempo
from physics.exact_dynamics.evaluate import FalsificationConfig, evaluate_falsification
from physics.exact_dynamics.hamiltonian_builder import HamiltonianModel
from physics.exact_dynamics.telemetry import write_telemetry


HC_J_M = 1.986445857e-25


def _model_from_snapshot(path: Path) -> HamiltonianModel:
    """Load a local SI Hamiltonian snapshot without inventing QM provenance."""
    with np.load(path, allow_pickle=False) as payload:
        if "H_sys_si" not in payload.files or "hamiltonian_unit" not in payload.files:
            raise ValueError("snapshot requires H_sys_si and hamiltonian_unit")
        if str(np.asarray(payload["hamiltonian_unit"]).item()) != "J":
            raise ValueError("snapshot Hamiltonian must declare joules")
        hamiltonian = np.asarray(payload["H_sys_si"], complex)
    if (hamiltonian.ndim != 2 or hamiltonian.shape[0] != hamiltonian.shape[1]
            or hamiltonian.shape[0] < 2 or not np.all(np.isfinite(hamiltonian))
            or not np.allclose(hamiltonian, hamiltonian.conj().T, atol=1e-30, rtol=1e-10)):
        raise ValueError("snapshot H_sys_si must be finite, square, and Hermitian")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    ids = tuple(f"snapshot_site_{index}" for index in range(hamiltonian.shape[0]))
    return HamiltonianModel(hamiltonian, ids, float("nan"), float("nan"), digest)


def _coherent_initial_state(dimension: int) -> np.ndarray:
    """Return (|0> + |1>)(<0| + <1|)/2 in the single-excitation basis."""
    vector = np.zeros(dimension, complex)
    vector[:2] = 1.0 / np.sqrt(2.0)
    return np.outer(vector, vector.conj())


def _run(model: HamiltonianModel, *, temperature_K: float, lambda_cm_inv: float,
         cutoff_ps_inv: float, step_fs: float, memory_fs: float, end_fs: float,
         epsrel: float) -> tuple[dict[str, object], object]:
    """Execute one SI-rescaled structured-bath run and return its metadata."""
    step_s = step_fs * 1e-15
    times = np.arange(0.0, end_fs * 1e-15 + step_s * 0.5, step_s)
    bath = BathConfig(
        reorganization_energy_J=lambda_cm_inv * 100.0 * HC_J_M,
        cutoff_rate_s=cutoff_ps_inv * 1e12,
        temperature_K=temperature_K,
        coupling_sites=(0,),
        time_step_s=step_s,
        memory_time_s=memory_fs * 1e-15,
        epsrel=epsrel,
    )
    result = run_oqupy_pt_tempo(model, _coherent_initial_state(model.hamiltonian_J.shape[0]), times, bath)
    return {
        "temperature_K": temperature_K,
        "reorganization_energy_cm_inv": lambda_cm_inv,
        "cutoff_ps_inv": cutoff_ps_inv,
        "time_step_fs": step_fs,
        "memory_time_fs": memory_fs,
        "end_time_fs": end_fs,
        "epsrel": epsrel,
        "trace_residual": result.trace_residual,
        "positivity_residual": result.positivity_residual,
        "backend": result.backend,
    }, result


def run(args: argparse.Namespace) -> dict[str, object]:
    """Perform a primary TEMPO run plus one independent grid-refinement check."""
    snapshot = args.snapshot.resolve()
    model = _model_from_snapshot(snapshot)
    primary_meta, primary = _run(
        model,
        temperature_K=args.temperature_K,
        lambda_cm_inv=args.reorganization_cm_inv,
        cutoff_ps_inv=args.cutoff_ps_inv,
        step_fs=args.step_fs,
        memory_fs=args.memory_fs,
        end_fs=args.end_fs,
        epsrel=args.epsrel,
    )
    refined_meta, refined = _run(
        model,
        temperature_K=args.temperature_K,
        lambda_cm_inv=args.reorganization_cm_inv,
        cutoff_ps_inv=args.cutoff_ps_inv,
        step_fs=args.step_fs / 2.0,
        memory_fs=args.memory_fs * 1.5,
        end_fs=args.end_fs,
        epsrel=args.epsrel / 10.0,
    )
    primary_eval = evaluate_falsification(primary, ab_initio_inputs=False, config=FalsificationConfig())
    refined_eval = evaluate_falsification(refined, ab_initio_inputs=False, config=FalsificationConfig())
    # Compare the coarse run at matching physical times in the refined result.
    stride = 2
    max_state_difference = float(np.max(np.abs(primary.density_matrices - refined.density_matrices[::stride])))
    convergence_passed = max_state_difference <= args.convergence_tolerance
    payload: dict[str, object] = {
        "schema": "ScienceR-Dsim.NonMarkovianBathFalsification.v1",
        "input_source": "local_si_snapshot_non_ab_initio",
        "snapshot_path": str(snapshot),
        "snapshot_checksum_sha256": model.checksum_sha256,
        "primary": {**primary_meta, "evaluation": primary_eval},
        "refined": {**refined_meta, "evaluation": refined_eval},
        "max_state_difference": max_state_difference,
        "convergence_tolerance": args.convergence_tolerance,
        "convergence_passed": convergence_passed,
        "verdict": "INCONCLUSIVE",
        "scientific_note": (
            "This is a two-site OQuPy TEMPO calculation with a phenomenological "
            "Drude--Lorentz bath. The local Hamiltonian lacks validated TD-DFT/QM "
            "provenance and the collective diagonal bath coupling is an assumption. "
            "The run can falsify only after independent input and convergence validation; "
            "it cannot establish biological quantum coherence."
        ),
    }
    write_telemetry(args.output_dir / "non_markovian_falsification.json", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/exact_dynamics/non_markovian_bath"))
    parser.add_argument("--temperature-K", type=float, default=310.0)
    parser.add_argument("--reorganization-cm-inv", type=float, default=100.0)
    parser.add_argument("--cutoff-ps-inv", type=float, default=50.0)
    parser.add_argument("--step-fs", type=float, default=0.5)
    parser.add_argument("--memory-fs", type=float, default=20.0)
    parser.add_argument("--end-fs", type=float, default=50.0)
    parser.add_argument("--epsrel", type=float, default=1e-6)
    parser.add_argument("--convergence-tolerance", type=float, default=1e-3)
    args = parser.parse_args()
    if min(args.temperature_K, args.reorganization_cm_inv, args.cutoff_ps_inv, args.step_fs, args.memory_fs, args.end_fs, args.epsrel, args.convergence_tolerance) <= 0:
        parser.error("all physical and convergence parameters must be positive")
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
