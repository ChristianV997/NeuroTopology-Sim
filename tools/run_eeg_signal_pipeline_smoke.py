#!/usr/bin/env python3
"""End-to-end fixture-safe EEG signal pipeline smoke runner (P8.1 → P11).

Runs each pipeline stage with --mock-fixture in order. Does not generate real
EEG data, download datasets, infer labels, or fabricate targets. Intended for
CI/operator use to verify the complete P8.1/P8.2/P9/P10/P11 artifact chain.

Does NOT run P12 label contracts or any label alignment step.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


_STAGES = (
    "feed_eeg_study_dataset",
    "probe_eeg_signal_blocks",
    "run_eeg_level_m_signal",
    "run_eeg_level_t_signal",
    "run_eeg_signal_mt",
)


def _build_commands(dataset_id: str, root: str) -> list[tuple[str, list[str]]]:
    ds_lower = dataset_id.lower()
    return [
        (
            "feed_eeg_study_dataset",
            [
                sys.executable, "-m",
                "sciencer_d.btc_icft.pipelines.feed_eeg_study_dataset",
                "--dataset-id", dataset_id,
                "--out", f"{root}/eeg_studies/{dataset_id}",
                "--mock-fixture",
            ],
        ),
        (
            "probe_eeg_signal_blocks",
            [
                sys.executable, "-m",
                "sciencer_d.btc_icft.pipelines.probe_eeg_signal_blocks",
                "--out", f"{root}/{ds_lower}/signal_blocks",
                "--mock-fixture",
            ],
        ),
        (
            "run_eeg_level_m_signal",
            [
                sys.executable, "-m",
                "sciencer_d.btc_icft.pipelines.run_eeg_level_m_signal",
                "--dataset-id", dataset_id,
                "--out", f"{root}/eeg_level_m/{dataset_id}",
                "--mock-fixture",
            ],
        ),
        (
            "run_eeg_level_t_signal",
            [
                sys.executable, "-m",
                "sciencer_d.btc_icft.pipelines.run_eeg_level_t_signal",
                "--dataset-id", dataset_id,
                "--out", f"{root}/eeg_level_t/{dataset_id}",
                "--mock-fixture",
            ],
        ),
        (
            "run_eeg_signal_mt",
            [
                sys.executable, "-m",
                "sciencer_d.btc_icft.pipelines.run_eeg_signal_mt",
                "--dataset-id", dataset_id,
                "--out", f"{root}/eeg_signal_mt/{dataset_id}",
                "--mock-fixture",
            ],
        ),
    ]


def _run_stage(name: str, cmd: list[str]) -> subprocess.CompletedProcess:
    print(f"  Running {name} ...", flush=True)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout.strip():
        for line in result.stdout.strip().splitlines():
            print(f"    {line}")
    if result.returncode != 0:
        print(f"  FAIL: {name} exited with code {result.returncode}", file=sys.stderr)
        if result.stderr.strip():
            for line in result.stderr.strip().splitlines()[:20]:
                print(f"    stderr: {line}", file=sys.stderr)
    return result


def _read_promotion_status(root: str, dataset_id: str) -> dict | None:
    metrics_path = Path(root) / "eeg_signal_mt" / dataset_id / "metrics_signal_mt.json"
    if not metrics_path.is_file():
        return None
    try:
        data = json.loads(metrics_path.read_text(encoding="utf-8"))
        return {
            "promoted": data.get("promoted"),
            "promotion_reason": data.get("promotion_reason"),
        }
    except (json.JSONDecodeError, OSError):
        return None


def run_smoke(
    dataset_id: str = "DS005620",
    root: str = "outputs/btc_icft",
    validate: bool = False,
) -> int:
    print(f"EEG signal pipeline smoke run — dataset_id={dataset_id} root={root}")
    print(f"Stages: {', '.join(_STAGES)}")
    print()

    commands = _build_commands(dataset_id, root)
    for name, cmd in commands:
        cp = _run_stage(name, cmd)
        if cp.returncode != 0:
            print(
                f"\nSmoke run FAILED at stage '{name}'. "
                "Remaining stages not executed.",
                file=sys.stderr,
            )
            return 1
        print(f"  OK: {name}")

    print()
    promotion = _read_promotion_status(root, dataset_id)
    if promotion is not None:
        print(
            f"P11 promotion status: "
            f"promoted={promotion['promoted']} | {promotion['promotion_reason']}"
        )

    if validate:
        print()
        print("Running artifact validator ...")
        validate_cmd = [
            sys.executable,
            "tools/validate_eeg_signal_artifacts.py",
            "--root", root,
            "--dataset-id", dataset_id,
            "--allow-missing",
        ]
        cp = subprocess.run(validate_cmd, capture_output=True, text=True)
        for line in cp.stdout.strip().splitlines():
            print(f"  {line}")
        if cp.returncode != 0:
            for line in cp.stderr.strip().splitlines():
                print(f"  {line}", file=sys.stderr)
            print("Artifact validation FAILED.", file=sys.stderr)
            return 1
        print("Artifact validation PASSED.")

    print()
    print("Smoke run COMPLETE.")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="End-to-end EEG signal pipeline smoke runner (P8.1–P11)."
    )
    parser.add_argument(
        "--dataset-id",
        default="DS005620",
        help="Dataset identifier.",
    )
    parser.add_argument(
        "--root",
        default="outputs/btc_icft",
        help="BTC/ICFT output root directory.",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run validate_eeg_signal_artifacts.py after all stages complete.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or sys.argv[1:]))
    return run_smoke(
        dataset_id=args.dataset_id,
        root=args.root,
        validate=args.validate,
    )


if __name__ == "__main__":
    raise SystemExit(main())
