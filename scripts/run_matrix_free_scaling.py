"""Isolated matrix-free Liouvillian scaling benchmark for expanded PBC lattices."""
from __future__ import annotations

import argparse, csv, json, os, sys, tempfile, time
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from physics.open_quantum import LatticeConfig, LindbladLattice, ThermalBathConfig, solve_gap


def _safe(value: Any) -> Any:
    if isinstance(value, Path): return str(value)
    if isinstance(value, float) and not np.isfinite(value): return None
    if isinstance(value, dict): return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_safe(v) for v in value]
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    fd, temp = tempfile.mkstemp(prefix=path.stem + "_", suffix=".tmp", dir=path.parent); os.close(fd)
    try: Path(temp).write_text(json.dumps(_safe(payload), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"); os.replace(temp, path)
    finally:
        if Path(temp).exists(): Path(temp).unlink()


def run(args: argparse.Namespace) -> dict[str, Any]:
    """Benchmark only matrix-free paths; all rates are SI s^-1 and times are seconds."""
    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True); records: list[dict[str, Any]] = []
    for layers in args.n_layers:
        bath = ThermalBathConfig.from_temperature(args.temperature_K, args.transition_energy_eV, thermal_relaxation_s=args.thermal_relaxation_s, dephasing_rate_s=args.dephasing_rate_s, radiative_rate_s=args.radiative_rate_s, metabolic_pump_rate_s=args.pump_rate, pump_sites=tuple(args.pump_sites))
        model = LindbladLattice.from_pbc(LatticeConfig(n_layers=layers, interaction_cutoff_m=args.cutoff_nm * 1e-9, transition_energy_eV=args.transition_energy_eV, bath=bath))
        started = time.perf_counter()
        try:
            result = solve_gap(model, dense_max_dimension=args.dense_max_dimension, k=args.krylov_k, maxiter=args.maxiter)
            failure = None
        except Exception as exc:
            result = None; failure = f"{type(exc).__name__}: {exc}"
        elapsed = time.perf_counter() - started
        probe = np.eye(model.dimension, dtype=complex) / model.dimension
        records.append({"n_layers": layers, "dimension": model.dimension, "liouvillian_dimension": model.dimension ** 2, "method": "unresolved" if result is None else result.method, "converged": bool(result and result.converged), "iteration_count": None if result is None else result.iteration_count, "gap_s": None if result is None else result.gap_s, "tau_subradiant_s": None if result is None else result.tau_subradiant_s, "tau_superradiant_s": None if result is None else result.tau_superradiant_s, "stationary_residual_s": None if result is None else result.stationary_residual_s, "trace_preservation_residual_s": model.trace_residual(probe) if result is None else result.trace_preservation_residual_s, "elapsed_s": elapsed, "failure": failure})
    payload = {"schema": "ScienceR-Dsim.MatrixFreeScaling.v1", "source": "algorithmic_pbc_demo", "configuration": vars(args), "records": records, "scientific_note": "Krylov matvec calls are reported as an implementation-level work counter, not a physical observable."}
    report_stem=args.report_name
    _write_json(out / f"{report_stem}.json", payload)
    with (out / f"{report_stem}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0])); writer.writeheader(); writer.writerows(_safe(records))
    fig, axis = plt.subplots(figsize=(7, 4)); valid = [r for r in records if r["tau_subradiant_s"] is not None and r["tau_subradiant_s"] > 0]
    if valid: axis.semilogy([r["n_layers"] for r in valid], [r["tau_subradiant_s"] for r in valid], "o-", label="subradiant lifetime"); axis.legend()
    axis.set(xlabel="PBC axial layers", ylabel="Time (s)", title="Matrix-free subradiant scaling"); axis.grid(True, which="both", alpha=.3); fig.tight_layout(); fig.savefig(out / f"{report_stem}.png", dpi=200); plt.close(fig)
    return payload


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n-layers", nargs="+", type=int, default=[2, 3]); p.add_argument("--temperature-K", type=float, default=310.0); p.add_argument("--pump-rate", type=float, default=2e6); p.add_argument("--pump-sites", nargs="+", type=int, default=[0]); p.add_argument("--transition-energy-eV", type=float, default=4.43); p.add_argument("--cutoff-nm", type=float, default=8.0); p.add_argument("--thermal-relaxation-s", type=float, default=1e9); p.add_argument("--dephasing-rate-s", type=float, default=1e9); p.add_argument("--radiative-rate-s", type=float, default=1e8); p.add_argument("--dense-max-dimension", type=int, default=32); p.add_argument("--krylov-k", type=int, default=6); p.add_argument("--maxiter", type=int, default=2000); p.add_argument("--report-name",default="scaling_benchmark"); p.add_argument("--output-dir", type=Path, default=Path("artifacts/open_quantum/matrix_free_scaling")); return p


if __name__ == "__main__":
    print(json.dumps({"records": len(run(parser().parse_args())["records"])}))
