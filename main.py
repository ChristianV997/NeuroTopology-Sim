from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd

from validation.synthetic import (
    single_vortex, double_vortex, validate_vortex_charges,
    validate_dynamical_ground_truth,
)
from core.topology import compute_Qz
from pipelines.run_qzt import run as run_qzt_pipeline
from pipelines.run_eeg import run as run_eeg
from pipelines.run_physics import run_from_npy
from pipelines.run_cross_domain import run as run_cross_domain
from pipelines.run_physionet import run as run_physionet
from pipelines.run_external import run as run_external
from pipelines.run_neurolib import run as run_neurolib
from pipelines.run_fast_tr_validation import run as run_fast_tr_validation
from runs.run_record import RunRecordV1, write_json
from database.database import connect, start_run, finish_run, add_metric, add_artifact

# Synthetic vortex / dynamical ground-truth checks are engineering demos only.
_SYNTHETIC_EVIDENCE_CLASS = "synthetic_vortex_charge_demonstration"
_SYNTHETIC_RUN_MODE = "synthetic"
_SYNTHETIC_METRIC_KIND = "synthetic_known_charge_check"


def synthetic_evidence_watermarks() -> dict:
    """Fail-closed provenance stamps for main.py --mode synthetic outputs."""
    return {
        "evidence_class": _SYNTHETIC_EVIDENCE_CLASS,
        "run_mode": _SYNTHETIC_RUN_MODE,
        "metrics_are_empirical": False,
        "scientific_pass": False,
        "metric_kind": _SYNTHETIC_METRIC_KIND,
    }


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def run_synthetic():
    """Run synthetic validation checks and save summary metrics.

    Two families: the original STATIC known-charge fields (single/double
    vortex, unchanged contract below) and the DYNAMICAL ground-truth
    generators (Kuramoto lattice + CGL PDE) that give a time-evolving,
    tunable-defect-density oracle -- see validation/synthetic.py module
    docstring for why the static fields alone are insufficient.
    """
    out = Path("results/synthetic")
    out.mkdir(parents=True, exist_ok=True)
    psi = single_vortex()
    Qz1, Qabs1 = compute_Qz(psi)
    psi2 = double_vortex()
    Qz2, Qabs2 = compute_Qz(psi2)
    df = pd.DataFrame([
        {"case":"single_vortex", "Q_mean": float(Qz1.mean()), "Qabs_mean": float(Qabs1.mean())},
        {"case":"double_vortex", "Q_mean": float(Qz2.mean()), "Qabs_mean": float(Qabs2.mean())},
    ])
    validation = validate_vortex_charges()
    expected = {"single_vortex": 1.0, "double_vortex": 2.0}
    passes = {
        "single_vortex": bool(validation["single_vortex_pass"]),
        "double_vortex": bool(validation["double_vortex_pass"]),
    }
    df["Q_expected"] = df["case"].map(expected)
    # Engineering charge-check only — never promote to scientific_pass.
    df["pass_charge_check"] = df["case"].map(passes)
    df["metrics_are_empirical"] = False
    df["scientific_pass"] = False
    df["evidence_class"] = _SYNTHETIC_EVIDENCE_CLASS
    df["run_mode"] = _SYNTHETIC_RUN_MODE
    df["metric_kind"] = _SYNTHETIC_METRIC_KIND
    summary_csv = out / "synthetic_summary.csv"
    df.to_csv(summary_csv, index=False)
    print(df)

    dyn = validate_dynamical_ground_truth()
    dyn_df = pd.DataFrame([dyn])
    dyn_df["metrics_are_empirical"] = False
    dyn_df["scientific_pass"] = False
    dyn_df["evidence_class"] = _SYNTHETIC_EVIDENCE_CLASS
    dyn_df["run_mode"] = _SYNTHETIC_RUN_MODE
    dyn_df["metric_kind"] = "synthetic_dynamical_ground_truth"
    dyn_csv = out / "dynamical_ground_truth_summary.csv"
    dyn_df.to_csv(dyn_csv, index=False)
    print(dyn_df)

    marks = synthetic_evidence_watermarks()
    meta = {
        "records": int(len(df)),
        "csv": str(summary_csv),
        "dynamical_csv": str(dyn_csv),
        "note": (
            "pass_charge_check is an engineering vortex-charge gate only; "
            "scientific_pass remains false."
        ),
        **marks,
    }
    (out / "evidence_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    metrics = {
        "n_cases": int(len(df)),
        "metric_kind": marks["metric_kind"],
        "single_vortex_pass": bool(passes.get("single_vortex")),
        "double_vortex_pass": bool(passes.get("double_vortex")),
    }
    blob = json.dumps({"metrics": metrics}, sort_keys=True, separators=(",", ":"))
    run_id = hashlib.sha256(blob.encode()).hexdigest()[:16]
    record = RunRecordV1.make(
        run_id=run_id,
        run_kind="synthetic",
        data_mode="synthetic",
        metrics=metrics,
        artifacts={
            "synthetic_summary": str(summary_csv),
            "dynamical_summary": str(dyn_csv),
            "evidence_meta": str(out / "evidence_meta.json"),
        },
        source="main.run_synthetic",
        evidence_class=marks["evidence_class"],
        run_mode=marks["run_mode"],
        metrics_are_empirical=marks["metrics_are_empirical"],
        scientific_pass=marks["scientific_pass"],
        metric_kind=marks["metric_kind"],
    )
    write_json(record, out / "RunRecord.json")

def run_qzt(checkpoint_dir: str):
    """Run QZT pipeline and write outputs into results root."""
    out = Path("results")
    qzt, events = run_qzt_pipeline(checkpoint_dir, out)
    print(f"wrote {out} (qzt={len(qzt)}, events={len(events)})")

def main():
    ap = argparse.ArgumentParser()
    # NOTE: CLI argument contracts by mode are documented in docs/mode_contracts.md.
    ap.add_argument("--mode", required=True, choices=["synthetic", "qzt", "eeg", "physionet", "physics", "cross-domain", "external", "neural_mass", "fast_tr_validation", "db"])
    # --input is mode-dependent: directory for qzt/eeg/physionet, but a required .npy file for physics.
    ap.add_argument("--input", default="data/checkpoints")
    # "results/out.csv" is a sentinel default; eeg/physionet reinterpret it to mode-specific output paths.
    ap.add_argument("--output", default="results/out.csv")
    ap.add_argument("--dataset", default="ds002094")
    ap.add_argument("--results-root", default="results")
    ap.add_argument("--compute-pci", action="store_true")
    ap.add_argument("--compute-phase-grid-topology", action="store_true")
    ap.add_argument("--compute-kuramoto", action="store_true")
    ap.add_argument("--compute-leida", action="store_true")
    ap.add_argument("--n-nodes", type=_positive_int, default=32)
    ap.add_argument(
        "--neurolib-model",
        choices=["kuramoto", "hopf", "wilson_cowan", "aln"],
        default="kuramoto",
    )
    ap.add_argument("--t-max", type=_positive_float, default=10.0)
    ap.add_argument("--coupling", type=float, default=0.1)
    ap.add_argument("--n-voxels", type=_positive_int, default=32)
    ap.add_argument("--n-timepoints", type=_positive_int, default=500)
    ap.add_argument("--tr", type=_positive_float, default=0.645)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--db", default="data/runs.sqlite")
    ap.add_argument("--config", default="config/defaults.yaml")
    ap.add_argument("--max-records", type=int, default=None)
    args = ap.parse_args()

    # Dispatch behavior and artifacts differ per mode; see docs/mode_contracts.md for canonical contracts.
    if args.mode == "synthetic":
        run_synthetic()
    elif args.mode == "qzt":
        run_qzt(args.input)
    elif args.mode == "eeg":
        # When --output is left at the sentinel default, derive a dataset-scoped metrics path.
        default_out = Path("results") / args.dataset / f"metrics_{args.dataset}.csv"
        out_path = args.output if args.output != "results/out.csv" else str(default_out)
        df = run_eeg(
            args.input,
            out_path,
            dataset=args.dataset,
            compute_pci=args.compute_pci,
            compute_phase_grid_topology=args.compute_phase_grid_topology,
            compute_kuramoto=args.compute_kuramoto,
            compute_leida=args.compute_leida,
        )
        print(df.head())
    elif args.mode == "physionet":
        # Same sentinel behavior as eeg mode: use a mode-specific default metrics output path.
        default_out = Path("results") / "physionet_gaba" / "metrics_physionet_gaba.csv"
        out_path = args.output if args.output != "results/out.csv" else str(default_out)
        df = run_physionet(args.input, out_path)
        print(df.head())
    elif args.mode == "physics":
        input_path = Path(args.input)
        if not input_path.exists() or not input_path.is_file():
            ap.error(f"--mode physics requires --input to point to an existing .npy file (got: {args.input})")
        if input_path.suffix != ".npy":
            ap.error(f"--mode physics requires a .npy input file (got: {args.input})")
        df = run_from_npy(args.input, args.output)
        print(df.head())
    elif args.mode == "neural_mass":
        record = run_neurolib(
            output_csv=args.output,
            n_nodes=args.n_nodes,
            model_type=args.neurolib_model,
            t_max=args.t_max,
            coupling=args.coupling,
            seed=args.seed,
        )
        print(f"RunRecord: {record.run_id}")
    elif args.mode == "fast_tr_validation":
        record = run_fast_tr_validation(
            output_csv=args.output,
            n_voxels=args.n_voxels,
            n_timepoints=args.n_timepoints,
            tr=args.tr,
            seed=args.seed,
        )
        print(f"Fast-TR validation: {record.run_id}")
    elif args.mode == "cross-domain":
        df = run_cross_domain(args.results_root, args.output)
        print(df.head())
    elif args.mode == "external":
        df = run_external(args.config, args.output, args.db, max_records=args.max_records)
        print(df.head())
    elif args.mode == "db":
        conn = connect(args.db)
        rid = start_run(conn, "manual", "demo", params={"mode": "db"})
        add_metric(conn, rid, "demo_metric", 1.0, units="arb")
        add_artifact(conn, rid, args.output, kind="csv")
        finish_run(conn, rid)
        print("db ok")

if __name__ == "__main__":
    main()
