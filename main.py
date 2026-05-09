from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

from validation.synthetic import single_vortex, double_vortex, validate_vortex_charges
from core.topology import compute_Qz
from pipelines.run_qzt import run as run_qzt_pipeline
from pipelines.run_eeg import run as run_eeg
from pipelines.run_physics import run_from_npy
from pipelines.run_cross_domain import run as run_cross_domain
from pipelines.run_physionet import run as run_physionet
from pipelines.run_external import run as run_external
from database.database import connect, start_run, finish_run, add_metric, add_artifact

def run_synthetic():
    """Run synthetic validation checks and save summary metrics."""
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
    df["pass_charge_check"] = df["case"].map(passes)
    df.to_csv(out / "synthetic_summary.csv", index=False)
    print(df)

def run_qzt(checkpoint_dir: str):
    """Run QZT pipeline and write outputs into results root."""
    out = Path("results")
    qzt, events = run_qzt_pipeline(checkpoint_dir, out)
    print(f"wrote {out} (qzt={len(qzt)}, events={len(events)})")

def main():
    ap = argparse.ArgumentParser()
    # NOTE: CLI argument contracts by mode are documented in docs/mode_contracts.md.
    ap.add_argument("--mode", required=True, choices=["synthetic", "qzt", "eeg", "physionet", "physics", "cross-domain", "external", "db"])
    # --input is mode-dependent: directory for qzt/eeg/physionet, but a required .npy file for physics.
    ap.add_argument("--input", default="data/checkpoints")
    # "results/out.csv" is a sentinel default; eeg/physionet reinterpret it to mode-specific output paths.
    ap.add_argument("--output", default="results/out.csv")
    ap.add_argument("--dataset", default="ds002094")
    ap.add_argument("--results-root", default="results")
    ap.add_argument("--compute-pci", action="store_true")
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
        df = run_eeg(args.input, out_path, dataset=args.dataset, compute_pci=args.compute_pci)
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
