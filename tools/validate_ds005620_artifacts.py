#!/usr/bin/env python3
"""Validate DS005620 BTC/ICFT artifact contracts.

This is a lightweight, stdlib-only operator utility. It checks whether the staged
DS005620 pipeline artifacts exist and whether key JSON/CSV/report contracts remain
safe enough for downstream orchestration.

It does not download data, train models, compute scientific evidence, or promote
ontology claims. It only validates local artifact shape and guardrail language.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


BANNED_PHRASES = (
    "proves consciousness",
    "consciousness proven",
    "soul proven",
    "afterlife proven",
    "liberation detected",
    "ontology solved",
    "ultimate reality",
    "q equals self",
    "q equals soul",
    "q_abs equals suffering",
    "f_dress equals karma",
)


@dataclass(frozen=True)
class StageContract:
    name: str
    relative_dir: str
    required_files: tuple[str, ...]
    required_csv_columns: dict[str, tuple[str, ...]]
    required_json_keys: dict[str, tuple[str, ...]]
    required_report_terms: tuple[str, ...]


STAGE_CONTRACTS: tuple[StageContract, ...] = (
    StageContract(
        name="bids_inspection",
        relative_dir="bids_inspection",
        required_files=(
            "file_inventory.json",
            "label_candidates.json",
            "contract_report.json",
            "report.md",
        ),
        required_csv_columns={},
        required_json_keys={
            "file_inventory.json": ("dataset_id",),
            "contract_report.json": ("valid", "errors", "warnings"),
        },
        required_report_terms=("operational", "residual testing"),
    ),
    StageContract(
        name="m_real",
        relative_dir="m_real",
        required_files=(
            "features_m.csv",
            "metrics_m.json",
            "artifact_report.json",
            "leakage_report.json",
            "omega_event.json",
            "report.md",
        ),
        required_csv_columns={
            "features_m.csv": (
                "row_id",
                "subject_id",
                "session_id",
                "run_id",
                "window_id",
                "task_label",
                "state_label",
                "behavior_label",
                "report_label",
                "spectral_power_proxy",
                "entropy_proxy",
                "lzc_proxy",
                "artifact_score",
                "source_file",
                "window_start_s",
                "window_end_s",
            ),
        },
        required_json_keys={
            "metrics_m.json": ("dataset_id", "task", "n_rows", "n_subjects"),
            "artifact_report.json": ("artifact_dominance",),
            "leakage_report.json": ("leakage_detected",),
            "omega_event.json": ("safe_claim",),
        },
        required_report_terms=("operational", "window-feature", "future residual testing"),
    ),
    StageContract(
        name="t_real",
        relative_dir="t_real",
        required_files=(
            "features_t.csv",
            "topology_quality_report.json",
            "null_placeholder_report.json",
            "artifact_alignment_report.json",
            "omega_event.json",
            "report.md",
        ),
        required_csv_columns={
            "features_t.csv": (
                "row_id",
                "subject_id",
                "session_id",
                "run_id",
                "window_id",
                "task_label",
                "q_net",
                "q_abs",
                "f_dress",
                "defect_density",
                "n_triangles",
                "n_valid_triangles",
                "topology_quality",
                "null_method",
                "null_seed",
                "source_file",
                "window_start_s",
                "window_end_s",
            ),
        },
        required_json_keys={
            "topology_quality_report.json": ("quality_passed",),
            "null_placeholder_report.json": ("status", "real_nulls_performed"),
            "artifact_alignment_report.json": ("artifact_dominance_proxy",),
            "omega_event.json": ("safe_claim",),
        },
        required_report_terms=("operational", "topology telemetry", "future m+t residual testing"),
    ),
    StageContract(
        name="mt_real",
        relative_dir="mt_real",
        required_files=(
            "features_joined.csv",
            "metrics_mt_real.json",
            "nulls_real.json",
            "ablations_real.json",
            "leakage_report.json",
            "artifact_report.json",
            "omega_event.json",
            "report.md",
        ),
        required_csv_columns={
            "features_joined.csv": (
                "row_id",
                "subject_id",
                "session_id",
                "run_id",
                "window_id",
                "task_label",
                "spectral_power_proxy",
                "entropy_proxy",
                "lzc_proxy",
                "artifact_score",
                "q_net",
                "q_abs",
                "f_dress",
                "defect_density",
                "topology_quality",
            ),
        },
        required_json_keys={
            "metrics_mt_real.json": (
                "metrics_m",
                "metrics_mt",
                "delta_auc",
                "delta_ece",
                "promoted",
                "promotion_reason",
            ),
            "nulls_real.json": ("nulls_passed", "real_nulls_performed"),
            "ablations_real.json": ("M_only", "M_plus_all_T"),
            "leakage_report.json": ("leakage_detected",),
            "artifact_report.json": ("artifact_dominance",),
            "omega_event.json": ("safe_claim",),
        },
        required_report_terms=("residual predictive value", "level t topology telemetry", "specified controls"),
    ),
)


class ValidationError(RuntimeError):
    """Raised when a DS005620 artifact contract check fails."""


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError(f"Expected JSON object in {path}")
    return data


def _read_csv_header(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValidationError(f"CSV is empty: {path}") from exc
    return {column.strip() for column in header if column.strip()}


def _check_safe_text(path: Path) -> None:
    text = path.read_text(encoding="utf-8").lower()
    for phrase in BANNED_PHRASES:
        if phrase in text:
            raise ValidationError(f"Unsafe phrase in {path}: {phrase}")


def _check_terms(path: Path, terms: Iterable[str]) -> None:
    text = path.read_text(encoding="utf-8").lower()
    missing = [term for term in terms if term.lower() not in text]
    if missing:
        raise ValidationError(f"Missing expected report terms in {path}: {', '.join(missing)}")


def _check_required_files(stage_dir: Path, contract: StageContract) -> None:
    missing = [name for name in contract.required_files if not (stage_dir / name).is_file()]
    if missing:
        raise ValidationError(f"Missing files for {contract.name}: {', '.join(missing)}")


def _check_csv_columns(stage_dir: Path, contract: StageContract) -> None:
    for filename, required_columns in contract.required_csv_columns.items():
        path = stage_dir / filename
        header = _read_csv_header(path)
        missing = [column for column in required_columns if column not in header]
        if missing:
            raise ValidationError(f"Missing CSV columns in {path}: {', '.join(missing)}")


def _check_json_keys(stage_dir: Path, contract: StageContract) -> None:
    for filename, required_keys in contract.required_json_keys.items():
        path = stage_dir / filename
        data = _read_json(path)
        missing = [key for key in required_keys if key not in data]
        if missing:
            raise ValidationError(f"Missing JSON keys in {path}: {', '.join(missing)}")


def validate_stage(root: Path, contract: StageContract) -> None:
    stage_dir = root / contract.relative_dir
    if not stage_dir.is_dir():
        raise ValidationError(f"Missing stage directory for {contract.name}: {stage_dir}")
    _check_required_files(stage_dir, contract)
    _check_csv_columns(stage_dir, contract)
    _check_json_keys(stage_dir, contract)
    report_path = stage_dir / "report.md"
    _check_safe_text(report_path)
    _check_terms(report_path, contract.required_report_terms)

    for filename in contract.required_files:
        path = stage_dir / filename
        if path.suffix.lower() in {".json", ".md", ".csv"}:
            _check_safe_text(path)


def validate_all(root: Path, stages: Iterable[str] | None = None) -> list[str]:
    selected = set(stages or [])
    contracts = [contract for contract in STAGE_CONTRACTS if not selected or contract.name in selected]
    unknown = selected - {contract.name for contract in STAGE_CONTRACTS}
    if unknown:
        raise ValidationError(f"Unknown stage(s): {', '.join(sorted(unknown))}")

    passed: list[str] = []
    for contract in contracts:
        validate_stage(root, contract)
        passed.append(contract.name)
    return passed


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate DS005620 BTC/ICFT artifact contracts.")
    parser.add_argument(
        "--root",
        default="outputs/btc_icft/ds005620",
        help="DS005620 output root containing stage subdirectories.",
    )
    parser.add_argument(
        "--stage",
        action="append",
        choices=[contract.name for contract in STAGE_CONTRACTS],
        help="Validate only the named stage. May be provided multiple times.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable result JSON.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or sys.argv[1:]))
    root = Path(args.root)
    try:
        passed = validate_all(root, args.stage)
    except ValidationError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        else:
            print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    result = {"ok": True, "root": str(root), "stages": passed}
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"PASS: validated DS005620 artifact contracts for {', '.join(passed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
