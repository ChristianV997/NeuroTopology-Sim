"""Test correlated radiative dissipation against a pre-registered null."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from physics.open_quantum import LatticeConfig, ThermalBathConfig, coupled_lattice, MultiLatticeConfig, solve_gap


def _evaluate(task: dict[str, float]) -> dict[str, Any]:
    base = ThermalBathConfig.from_temperature(310.0, 4.43, thermal_relaxation_s=1e9,
        dephasing_rate_s=task["dephasing_rate_s"], radiative_rate_s=1e8)
    bath = replace(base, collective_radiative_rate_s=task["collective_rate_s"],
                   collective_correlation_length_m=task["correlation_length_nm"] * 1e-9)
    config = LatticeConfig(n_layers=1, interaction_cutoff_m=30e-9, dielectric_constant=7.0, bath=bath)
    model = coupled_lattice(config, MultiLatticeConfig(task["spacing_nm"] * 1e-9))
    result = solve_gap(model, dense_max_dimension=32, k=6, maxiter=2000)
    return {**task, "dimension": model.dimension, "method": result.method, "converged": result.converged,
            "tau_subradiant_s": result.tau_subradiant_s, "gap_s": result.gap_s,
            "trace_preservation_residual_s": result.trace_preservation_residual_s}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spacings-nm", type=float, nargs="+", default=[3., 6., 10., 18.])
    parser.add_argument("--collective-rates-s", type=float, nargs="+", default=[0., 1e7, 1e8])
    parser.add_argument("--correlation-length-nm", type=float, default=8.)
    parser.add_argument("--dephasing-rate-s", type=float, default=1e8)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/campaign/correlated_dissipation"))
    args = parser.parse_args()
    if args.workers < 1 or args.correlation_length_nm <= 0 or any(rate < 0 for rate in args.collective_rates_s):
        parser.error("rates, correlation length, and workers are invalid")
    tasks = [{"spacing_nm": spacing, "collective_rate_s": rate, "correlation_length_nm": args.correlation_length_nm,
              "dephasing_rate_s": args.dephasing_rate_s} for spacing in args.spacings_nm for rate in args.collective_rates_s]
    if args.workers == 1:
        records = [_evaluate(task) for task in tasks]
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            records = list(pool.map(_evaluate, tasks))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    payload = {"schema": "ScienceR-Dsim.CorrelatedDissipationStudy.v1", "pre_registered_null": {"collective_rate_s": 0.0,
        "claim": "No separation-dependent collective lifetime shift beyond the independent-bath model."},
        "hypothesis": {"mechanism": "completely positive exponentially correlated radiative bath",
                       "primary_outcome": "tau_subradiant_s as a function of spacing_nm"},
        "configuration": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}, "records": records,
        "scientific_note": "This is a finite phenomenological model. A nonzero effect supports only sensitivity of this model to the stated bath assumption."}
    (args.output_dir / "correlated_dissipation_study.json").write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"records": len(records), "output": str(args.output_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
