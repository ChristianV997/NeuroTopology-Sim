"""Run a bounded coupled-microtubule dipolar benchmark offline."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
import csv
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from physics.open_quantum import LatticeConfig, ThermalBathConfig, solve_gap
from physics.open_quantum.multi_lattice import MultiLatticeConfig, coupled_lattice


def _safe(value: Any) -> Any:
    if isinstance(value, Path): return str(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.integer): return int(value)
    if isinstance(value, dict): return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_safe(v) for v in value]
    return value


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.stem, suffix=".tmp")
    os.close(descriptor)
    try:
        Path(temporary).write_text(json.dumps(_safe(payload), indent=2, allow_nan=False) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _evaluate(task: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one isolated finite lattice point; called in a worker process."""
    bath = ThermalBathConfig.from_temperature(
        task["temperature_K"], task["transition_energy_eV"],
        thermal_relaxation_s=task["thermal_relaxation_s"], radiative_rate_s=task["radiative_rate_s"],
        dephasing_rate_s=task["dephasing_rate_s"], metabolic_pump_rate_s=task["pump_rate"],
        pump_sites=task["pump_sites"],
    )
    config = LatticeConfig(n_layers=task["n_layers"], interaction_cutoff_m=task["cutoff_nm"] * 1e-9,
                           dielectric_constant=task["dielectric_constant"], transition_energy_eV=task["transition_energy_eV"], bath=bath)
    model = coupled_lattice(config, MultiLatticeConfig(task["spacing_nm"] * 1e-9))
    try:
        result = solve_gap(model, dense_max_dimension=task["dense_max_dimension"], k=task["krylov_k"], maxiter=task["maxiter"])
        failure = None
    except Exception as exc:
        result, failure = None, f"{type(exc).__name__}: {exc}"
    record = {"spacing_nm": task["spacing_nm"], "dielectric_constant": task["dielectric_constant"],
              "dephasing_rate_s": task["dephasing_rate_s"], "pump_orientation": task["pump_orientation"],
              "dimension": model.dimension, "method": result.method if result else "unresolved",
              "converged": bool(result and result.converged), "gap_s": result.gap_s if result else None,
              "tau_subradiant_s": result.tau_subradiant_s if result else None,
              "tau_superradiant_s": result.tau_superradiant_s if result else None,
              "trace_preservation_residual_s": result.trace_preservation_residual_s if result else None,
              "exhibits_chiral_current": result.exhibits_chiral_current if result else None,
              "stationary_eigenvalue_real_s": result.stationary_eigenvalue_s.real if result else None,
              "stationary_eigenvalue_imag_s": result.stationary_eigenvalue_s.imag if result else None,
              "stationary_modes": result.stationary_modes if result else None, "failure": failure}
    tau = record["tau_subradiant_s"]
    record["accepted"] = bool(record["converged"] and tau is not None and task["tau_min_s"] <= tau <= task["tau_max_s"])
    record["rejection_reason"] = None if record["accepted"] else (failure or "tau_subradiant outside configured acceptance window")
    return record


def run(args: argparse.Namespace) -> dict[str, Any]:
    """Evaluate finite coupled systems over configured spacings in nm."""
    output = Path(args.output_dir); output.mkdir(parents=True, exist_ok=True)
    if args.workers < 1 or args.tau_min_s <= 0 or args.tau_max_s < args.tau_min_s:
        raise ValueError("workers and lifetime acceptance bounds are invalid")
    if any(x <= 0 or not np.isfinite(x) for x in args.spacings_nm + args.dielectric_constants + args.dephasing_rates_s):
        raise ValueError("spacing, dielectric, and dephasing values must be finite and positive")
    if any(x > args.max_spacing_nm for x in args.spacings_nm) or any(x > args.max_dielectric for x in args.dielectric_constants):
        raise ValueError("configured parameter exceeds declared safety bound")
    records: list[dict[str, Any]] = []
    base_sites = 13 * args.n_layers
    orientations = {"axial": (0,), "lateral": (6,), "helical": tuple(range(0, base_sites, 13))}
    tasks: list[dict[str, Any]] = []
    for spacing_nm in args.spacings_nm:
        for dielectric in args.dielectric_constants:
                for dephasing in args.dephasing_rates_s:
                    for orientation in args.pump_orientations:
                        if orientation not in orientations: raise ValueError(f"unknown pump orientation: {orientation}")
                        tasks.append({**vars(args), "spacing_nm": spacing_nm, "dielectric_constant": dielectric,
                                      "dephasing_rate_s": dephasing, "pump_orientation": orientation,
                                      "pump_sites": orientations[orientation]})
    if args.workers == 1:
        records = [_evaluate(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            records = list(pool.map(_evaluate, tasks))
    accepted = [record for record in records if record["accepted"]]
    discarded = [record for record in records if not record["accepted"]]
    payload = {"schema": "ScienceR-Dsim.MultiLatticeBenchmark.v1", "source": "algorithmic_coupled_pbc_demo",
               "configuration": vars(args), "records": accepted, "discarded_records": discarded,
               "scientific_note": "This finite dipolar model tests numerical collective modes; it does not establish biological subradiance."}
    _atomic_json(output / "multi_lattice_benchmark.json", payload)
    with (output / "multi_lattice_benchmark.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0])); writer.writeheader(); writer.writerows(_safe(records))
    valid = [record for record in accepted if record["tau_subradiant_s"]]
    figure, axis = plt.subplots(figsize=(7, 4))
    if valid: axis.semilogy([r["spacing_nm"] for r in valid], [r["tau_subradiant_s"] for r in valid], "o-")
    axis.set(xlabel="Inter-lattice separation (nm)", ylabel="Subradiant lifetime (s)", title="Coupled lattice benchmark"); axis.grid(alpha=.3, which="both")
    figure.tight_layout(); figure.savefig(output / "multi_lattice_benchmark.png", dpi=200); plt.close(figure)
    return payload


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--spacings-nm", nargs="+", type=float, default=[2., 20.]); p.add_argument("--n-layers", type=int, default=1)
    p.add_argument("--temperature-K", type=float, default=310.); p.add_argument("--pump-rate", type=float, default=2e6)
    p.add_argument("--transition-energy-eV", type=float, default=4.43); p.add_argument("--cutoff-nm", type=float, default=30.)
    p.add_argument("--dielectric-constants", nargs="+", type=float, default=[4., 10.]); p.add_argument("--thermal-relaxation-s", type=float, default=1e9)
    p.add_argument("--radiative-rate-s", type=float, default=1e8); p.add_argument("--dephasing-rates-s", nargs="+", type=float, default=[1e8])
    p.add_argument("--pump-orientations", nargs="+", choices=["axial", "lateral", "helical"], default=["axial", "helical"])
    p.add_argument("--tau-min-s", type=float, default=1.661129583e-9); p.add_argument("--tau-max-s", type=float, default=1.661129599e-9)
    p.add_argument("--workers", type=int, default=1); p.add_argument("--max-spacing-nm", type=float, default=50.); p.add_argument("--max-dielectric", type=float, default=20.)
    p.add_argument("--dense-max-dimension", type=int, default=32); p.add_argument("--krylov-k", type=int, default=6); p.add_argument("--maxiter", type=int, default=2000)
    p.add_argument("--output-dir", type=Path, default=Path("artifacts/open_quantum/multi_lattice_coupling")); return p


if __name__ == "__main__":
    print(json.dumps({"records": len(run(parser().parse_args())["records"])}))
