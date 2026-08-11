"""Run a bounded preregistered theory-development campaign."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from scipy.stats import qmc

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from theory_campaign.core import CampaignConfig, dimensionless_groups, evaluate_lattice_point, stable_json
from theory_campaign.memory import MemoryConfig, simulate_memory_mode


def run(args: argparse.Namespace) -> dict[str, object]:
    if args.samples < 1 or args.disorder_samples < 2:
        raise ValueError("samples must be positive and disorder_samples must be at least two")
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    configs = []
    if args.design == "sobol":
        points = qmc.Sobol(d=3, scramble=False, seed=args.seed).random_base2(int(np.ceil(np.log2(args.samples))))[:args.samples]
    else:
        points = None
    for sample in range(args.samples):
        if points is None:
            spacing = args.spacings_nm[sample % len(args.spacings_nm)]
            rate = args.collective_rates_s[sample % len(args.collective_rates_s)]
            temperature = args.temperatures_K[sample % len(args.temperatures_K)]
        else:
            spacing = float(np.exp(np.log(min(args.spacings_nm)) + points[sample, 0] * (np.log(max(args.spacings_nm)) - np.log(min(args.spacings_nm)))))
            rate = float(np.exp(np.log(max(min(args.collective_rates_s), 1e5)) + points[sample, 1] * (np.log(max(args.collective_rates_s)) - np.log(max(min(args.collective_rates_s), 1e5)))))
            temperature = float(min(args.temperatures_K) + points[sample, 2] * (max(args.temperatures_K) - min(args.temperatures_K)))
        for disorder_sample in range(args.disorder_samples):
            configs.append(CampaignConfig(
                spacing_nm=spacing,
                collective_rate_s=rate,
                temperature_K=temperature,
                disorder_seed=args.seed + sample * args.disorder_samples + disorder_sample,
                disorder_sigma_nm=args.disorder_sigma_nm,
                correlation_length_nm=args.correlation_length_nm,
                dense_max_dimension=args.dense_max_dimension,
            ))
    manifest = {
        "schema": "NeuroTopologySim.TheoryCampaignManifest.v1",
        "seed": args.seed,
        "design": args.design,
        "cloud_submission": False,
        "nulls": ["independent_bath", "short_correlation_null"],
        "dimensionless_groups": ["kappa_collective_to_local", "rho_spacing_to_correlation", "delta_disorder_to_spacing", "chi_coherent_to_total_decay", "theta_transition_to_thermal"],
        "configuration": vars(args),
    }
    (output / "campaign_manifest.json").write_text(stable_json(manifest), encoding="utf-8")
    records = []
    for config in configs:
        try:
            records.append(evaluate_lattice_point(config))
        except Exception as exc:
            records.append({"schema": "NeuroTopologySim.TheoryLatticePoint.v1", "configuration": vars(config), "failure": f"{type(exc).__name__}: {exc}"})
    memory_records = []
    for memory_time in args.memory_times_s:
        memory_records.append(simulate_memory_mode(MemoryConfig(
            decay_rate_s=args.memory_decay_rate_s,
            memory_time_s=memory_time,
            memory_strength_s2=args.memory_strength_s2,
            duration_s=args.memory_duration_s,
            steps=args.memory_steps,
        )))
    (output / "records.jsonl").write_text("".join(json.dumps(record, sort_keys=True, allow_nan=False) + "\n" for record in records), encoding="utf-8")
    (output / "memory_records.json").write_text(stable_json({"records": memory_records}), encoding="utf-8")
    (output / "null_comparisons.json").write_text(stable_json({
        "schema": "NeuroTopologySim.NullComparisons.v1",
        "records": [record.get("primary_contrast") for record in records],
        "nulls": manifest["nulls"],
    }), encoding="utf-8")
    (output / "solver_telemetry.json").write_text(stable_json({
        "schema": "NeuroTopologySim.SolverTelemetry.v1",
        "records": [record.get("records", []) for record in records],
    }), encoding="utf-8")
    successful = [record for record in records if "failure" not in record]
    summary = {
        "schema": "NeuroTopologySim.TheoryCampaignSummary.v1",
        "n_requested": len(records),
        "n_successful": len(successful),
        "n_failed": len(records) - len(successful),
        "regime_counts": {"converged": len(successful), "numerically_unresolved": len(records) - len(successful)},
        "cloud_submission": False,
        "scientific_note": "Pilot model outputs constrain theoretical regimes only; they do not establish biological coherence or validate prior speculative claims.",
    }
    (output / "phase_diagram_summary.json").write_text(stable_json(summary), encoding="utf-8")
    report = """# Theory Development Campaign\n\nThis pilot evaluates dimensionless collective-mode regimes with matched nulls and an exponential-memory reference model. Results are model-development artifacts, not biological evidence.\n\n## Regime axes\n\n`kappa=collective/local decay`, `rho=spacing/correlation length`, `delta=disorder/spacing`, `chi=coherent coupling/decay`, `theta=transition energy/(kBT)`.\n\n## Interpretation\n\nCandidate effects require complete convergence and comparison with the independent-bath and short-correlation nulls. Memory results are accepted only after short-memory convergence and time-step refinement checks.\n"""
    (output / "theory_regime_report.md").write_text(report, encoding="utf-8")
    return {"manifest": manifest, "summary": summary}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/theory_campaign/pilot"))
    parser.add_argument("--samples", type=int, default=2)
    parser.add_argument("--design", choices=["pilot", "sobol"], default="pilot")
    parser.add_argument("--disorder-samples", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260728)
    parser.add_argument("--spacings-nm", nargs="+", type=float, default=[3.0, 18.0])
    parser.add_argument("--collective-rates-s", nargs="+", type=float, default=[0.0, 1e8])
    parser.add_argument("--temperatures-K", nargs="+", type=float, default=[10.0, 77.0, 310.0])
    parser.add_argument("--correlation-length-nm", type=float, default=8.0)
    parser.add_argument("--disorder-sigma-nm", type=float, default=0.15)
    parser.add_argument("--dense-max-dimension", type=int, default=32)
    parser.add_argument("--memory-times-s", nargs="+", type=float, default=[1e-12, 1e-9, 1e-7])
    parser.add_argument("--memory-decay-rate-s", type=float, default=1e8)
    parser.add_argument("--memory-strength-s2", type=float, default=1e16)
    parser.add_argument("--memory-duration-s", type=float, default=1e-7)
    parser.add_argument("--memory-steps", type=int, default=1000)
    args = parser.parse_args()
    print(stable_json(run(args)), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
