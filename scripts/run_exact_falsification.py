"""Offline preflight/runner for structural non-Markovian falsification studies."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from physics.exact_dynamics import load_pdb_ensemble, load_electronic_inputs, build_single_excitation_hamiltonian, evaluate_falsification
from physics.exact_dynamics.dynamics_solver import BathConfig, calibration_reference, run_oqupy_pt_tempo


def _safe(value: object) -> object:
    if isinstance(value, float): return value if np.isfinite(value) else None
    if isinstance(value, dict): return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, list): return [_safe(item) for item in value]
    return value


def run(args: argparse.Namespace) -> dict[str, object]:
    ensemble = load_pdb_ensemble(args.pdb)
    electronic = load_electronic_inputs(args.electronic_inputs)
    records: list[dict[str, object]] = []
    for conformer_id, sites in zip(ensemble.conformer_ids, ensemble.sites_by_conformer, strict=True):
        model = build_single_excitation_hamiltonian(sites, electronic, dielectric_constant=args.dielectric_constant, cutoff_m=args.cutoff_nm * 1e-9)
        times = np.linspace(0.0, args.end_time_ns * 1e-9, args.steps); rho = np.zeros((len(sites), len(sites)), complex); rho[0, 0] = 1.0
        if args.backend == "oqupy_pt_tempo":
            dynamics = run_oqupy_pt_tempo(model, rho, times, BathConfig(args.reorganization_energy_J, args.cutoff_rate_s, args.temperature_K, tuple(range(len(sites)))))
        elif not args.allow_calibration_reference:
            raise ValueError("calibration reference requires --allow-calibration-reference and cannot yield a falsification verdict")
        else:
            dynamics = calibration_reference(model, rho, times, dephasing_rate_s=args.calibration_dephasing_s)
        records.append({"conformer_id": conformer_id, "hamiltonian_checksum": model.checksum_sha256,
                        "result": evaluate_falsification(dynamics, ab_initio_inputs=True)})
    all_falsified = bool(records) and all(record["result"]["verdict"] == "FALSIFIED: NOISE_DOMINANT" for record in records)
    payload = {"schema": "ScienceR-Dsim.ExactDynamicsFalsification.v1", "pdb_checksums": ensemble.checksums_sha256,
               "electronic_checksum": electronic.checksum_sha256, "records": records,
               "campaign_verdict": "FALSIFIED: NOISE_DOMINANT" if all_falsified else "INCONCLUSIVE"}
    args.output.write_text(json.dumps(_safe(payload), indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--pdb", nargs="+", type=Path, required=True); p.add_argument("--electronic-inputs", type=Path, required=True)
    p.add_argument("--backend", choices=["oqupy_pt_tempo", "calibration_reference"], default="oqupy_pt_tempo"); p.add_argument("--allow-calibration-reference", action="store_true")
    p.add_argument("--dielectric-constant", type=float, default=4.0); p.add_argument("--cutoff-nm", type=float, default=2.0); p.add_argument("--temperature-K", type=float, default=310.0)
    p.add_argument("--reorganization-energy-J", type=float, default=1e-21); p.add_argument("--cutoff-rate-s", type=float, default=5e13); p.add_argument("--calibration-dephasing-s", type=float, default=1e12)
    p.add_argument("--end-time-ns", type=float, default=10.0); p.add_argument("--steps", type=int, default=1001); p.add_argument("--seed", type=int, default=20260726); p.add_argument("--output", type=Path, default=Path("artifacts/open_quantum/exact_dynamics/falsification.json")); args = p.parse_args(); args.output.parent.mkdir(parents=True, exist_ok=True); print(json.dumps(run(args)))
