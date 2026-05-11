#!/usr/bin/env python3
"""Validate EEG signal pipeline artifact contracts (P8.1/P8.2/P9/P10/P11).

Stdlib-only operator utility. Checks whether staged EEG signal pipeline artifacts
exist and whether key JSON/CSV/report contracts remain safe for downstream use.

Does not download data, train models, compute evidence, fabricate targets, or
promote ontology claims. Only validates local artifact shape and guardrail language.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


BANNED_PHRASES: tuple[str, ...] = (
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
    "sedated implies no_experience",
    "unresponsive implies unconscious",
)

_OMEGA_CLAIM_KEYS: tuple[str, ...] = ("safe_claim", "claim", "allowed_claim")


@dataclass(frozen=True)
class StageSpec:
    name: str
    required_files: tuple[str, ...]
    required_csv_columns: dict[str, tuple[str, ...]]
    required_json_keys: dict[str, tuple[str, ...]]
    ablations_file: str | None = None


_STAGE_SPECS: dict[str, StageSpec] = {
    "eeg_studies": StageSpec(
        name="eeg_studies",
        required_files=(
            "study_card.json",
            "file_readability_report.json",
            "reader_capability_report.json",
            "dataset_readiness_report.json",
            "report.md",
        ),
        required_csv_columns={},
        required_json_keys={
            "dataset_readiness_report.json": ("dataset_id", "readiness_status"),
        },
    ),
    "signal_blocks": StageSpec(
        name="signal_blocks",
        required_files=(
            "signal_block_inventory.json",
            "window_inventory.csv",
            "reader_alignment_report.json",
            "skipped_files.json",
            "omega_event.json",
            "report.md",
        ),
        required_csv_columns={
            "window_inventory.csv": (
                "file_path",
                "row_id",
                "window_id",
                "window_start_s",
                "window_end_s",
                "sample_start",
                "sample_end",
                "n_channels",
                "n_samples",
                "sample_rate_hz",
                "status",
            ),
        },
        required_json_keys={
            "reader_alignment_report.json": ("ready_for_p9_signal_extraction",),
        },
    ),
    "eeg_level_m": StageSpec(
        name="eeg_level_m",
        required_files=(
            "features_m_signal.csv",
            "feature_quality_report.json",
            "artifact_report.json",
            "skipped_windows.json",
            "omega_event.json",
            "report.md",
        ),
        required_csv_columns={
            "features_m_signal.csv": (
                "dataset_id",
                "row_id",
                "source_file",
                "window_id",
                "window_start_s",
                "window_end_s",
                "sample_start",
                "sample_end",
                "n_channels",
                "n_samples",
                "sample_rate_hz",
                "spectral_power_proxy",
                "entropy_proxy",
                "lzc_proxy",
                "artifact_score",
                "feature_status",
            ),
        },
        required_json_keys={
            "feature_quality_report.json": (
                "quality_passed",
                "n_feature_rows",
                "n_skipped_windows",
            ),
        },
    ),
    "eeg_level_t": StageSpec(
        name="eeg_level_t",
        required_files=(
            "features_t_signal.csv",
            "topology_quality_report.json",
            "artifact_report.json",
            "skipped_windows.json",
            "omega_event.json",
            "report.md",
        ),
        required_csv_columns={
            "features_t_signal.csv": (
                "dataset_id",
                "row_id",
                "source_file",
                "window_id",
                "window_start_s",
                "window_end_s",
                "sample_start",
                "sample_end",
                "n_channels",
                "n_samples",
                "sample_rate_hz",
                "q_net",
                "q_abs",
                "f_dress",
                "defect_density",
                "n_triangles",
                "n_valid_triangles",
                "topology_quality",
                "topology_status",
            ),
        },
        required_json_keys={
            "topology_quality_report.json": (
                "quality_passed",
                "n_topology_rows",
                "n_skipped_windows",
            ),
        },
    ),
    "eeg_signal_mt": StageSpec(
        name="eeg_signal_mt",
        required_files=(
            "features_joined_signal.csv",
            "metrics_signal_mt.json",
            "nulls_signal.json",
            "ablations_signal.json",
            "alignment_report.json",
            "artifact_report.json",
            "omega_event.json",
            "report.md",
        ),
        required_csv_columns={
            "features_joined_signal.csv": (
                "dataset_id",
                "row_id",
                "source_file",
                "window_id",
                "window_start_s",
                "window_end_s",
                "sample_start",
                "sample_end",
                "n_channels",
                "n_samples",
                "sample_rate_hz",
                "spectral_power_proxy",
                "entropy_proxy",
                "lzc_proxy",
                "artifact_score_m",
                "feature_status",
                "q_net",
                "q_abs",
                "f_dress",
                "defect_density",
                "n_triangles",
                "n_valid_triangles",
                "topology_quality",
                "topology_status",
                "y",
                "label",
            ),
        },
        required_json_keys={
            "metrics_signal_mt.json": (
                "predictive_metrics_available",
                "promoted",
                "promotion_reason",
            ),
            "alignment_report.json": (
                "alignment_passed",
                "n_joined_rows",
            ),
            "nulls_signal.json": (
                "real_nulls_performed",
                "nulls_passed",
            ),
        },
        ablations_file="ablations_signal.json",
    ),
}

ALL_STAGES: tuple[str, ...] = (
    "eeg_studies",
    "signal_blocks",
    "eeg_level_m",
    "eeg_level_t",
    "eeg_signal_mt",
)


class ValidationError(RuntimeError):
    """Raised when an EEG signal artifact contract check fails."""


def _stage_dir(root: Path, stage: str, dataset_id: str) -> Path:
    if stage == "eeg_studies":
        return root / "eeg_studies" / dataset_id
    if stage == "signal_blocks":
        return root / dataset_id.lower() / "signal_blocks"
    if stage == "eeg_level_m":
        return root / "eeg_level_m" / dataset_id
    if stage == "eeg_level_t":
        return root / "eeg_level_t" / dataset_id
    if stage == "eeg_signal_mt":
        return root / "eeg_signal_mt" / dataset_id
    raise ValidationError(f"Unknown stage: {stage!r}")


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError(f"Expected JSON object in {path}")
    return data


def _read_csv_header(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValidationError(f"CSV is empty: {path}") from exc
    return {col.strip() for col in header if col.strip()}


def _check_safe_text(path: Path) -> None:
    text = path.read_text(encoding="utf-8").lower()
    for phrase in BANNED_PHRASES:
        if phrase in text:
            raise ValidationError(f"Unsafe phrase in {path.name}: '{phrase}'")


def _check_required_files(stage_dir: Path, spec: StageSpec) -> None:
    missing = [f for f in spec.required_files if not (stage_dir / f).is_file()]
    if missing:
        raise ValidationError(
            f"Stage '{spec.name}' missing required files: {', '.join(missing)}"
        )


def _check_csv_columns(stage_dir: Path, spec: StageSpec) -> None:
    for filename, required_cols in spec.required_csv_columns.items():
        path = stage_dir / filename
        header = _read_csv_header(path)
        missing = [c for c in required_cols if c not in header]
        if missing:
            raise ValidationError(
                f"Stage '{spec.name}' {filename} missing columns: {', '.join(missing)}"
            )


def _check_json_keys(stage_dir: Path, spec: StageSpec) -> None:
    for filename, required_keys in spec.required_json_keys.items():
        path = stage_dir / filename
        data = _read_json(path)
        missing = [k for k in required_keys if k not in data]
        if missing:
            raise ValidationError(
                f"Stage '{spec.name}' {filename} missing keys: {', '.join(missing)}"
            )


def _check_omega_event(stage_dir: Path, spec: StageSpec) -> None:
    omega_path = stage_dir / "omega_event.json"
    if not omega_path.is_file():
        return
    data = _read_json(omega_path)
    if not any(k in data for k in _OMEGA_CLAIM_KEYS):
        raise ValidationError(
            f"Stage '{spec.name}' omega_event.json missing claim key "
            f"(expected one of: {', '.join(_OMEGA_CLAIM_KEYS)})"
        )


def _check_ablations(stage_dir: Path, spec: StageSpec) -> None:
    if spec.ablations_file is None:
        return
    path = stage_dir / spec.ablations_file
    data = _read_json(path)
    entries = data.get("ablation_entries")
    if entries is None:
        if "M_only" in data and "M_plus_all_T" in data:
            return
        raise ValidationError(
            f"Stage '{spec.name}' {spec.ablations_file} missing 'ablation_entries' "
            "or top-level 'M_only'/'M_plus_all_T'"
        )
    missing = [k for k in ("M_only", "M_plus_all_T") if k not in entries]
    if missing:
        raise ValidationError(
            f"Stage '{spec.name}' {spec.ablations_file} ablation_entries "
            f"missing keys: {', '.join(missing)}"
        )


def validate_stage(
    root: Path,
    stage: str,
    dataset_id: str,
) -> dict:
    if stage not in _STAGE_SPECS:
        raise ValidationError(f"Unknown stage: {stage!r}")
    spec = _STAGE_SPECS[stage]
    sdir = _stage_dir(root, stage, dataset_id)

    if not sdir.is_dir():
        raise ValidationError(
            f"Stage '{stage}' directory not found: {sdir}"
        )

    _check_required_files(sdir, spec)
    _check_csv_columns(sdir, spec)
    _check_json_keys(sdir, spec)
    _check_omega_event(sdir, spec)
    _check_ablations(sdir, spec)

    for filename in spec.required_files:
        path = sdir / filename
        if path.suffix.lower() in {".json", ".md", ".csv"}:
            _check_safe_text(path)

    return {"stage": stage, "dir": str(sdir), "ok": True}


def validate_all(
    root: Path,
    dataset_id: str,
    stages: Iterable[str] | None = None,
    allow_missing: bool = False,
) -> dict:
    selected = list(stages or ALL_STAGES)
    unknown = [s for s in selected if s not in _STAGE_SPECS]
    if unknown:
        raise ValidationError(f"Unknown stage(s): {', '.join(unknown)}")

    results: dict[str, dict] = {}
    errors: list[str] = []
    warnings: list[str] = []

    for stage in selected:
        try:
            results[stage] = validate_stage(root, stage, dataset_id)
        except ValidationError as exc:
            msg = str(exc)
            if allow_missing and "directory not found" in msg:
                warnings.append(f"Skipped missing stage '{stage}': {msg}")
                results[stage] = {"stage": stage, "ok": True, "skipped": True}
            else:
                errors.append(msg)
                results[stage] = {"stage": stage, "ok": False, "error": msg}

    ok = len(errors) == 0
    return {
        "ok": ok,
        "dataset_id": dataset_id,
        "stages": results,
        "errors": errors,
        "warnings": warnings,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate EEG signal pipeline artifact contracts (P8.1–P11)."
    )
    parser.add_argument(
        "--root",
        default="outputs/btc_icft",
        help="BTC/ICFT output root directory.",
    )
    parser.add_argument(
        "--dataset-id",
        default="DS005620",
        help="Dataset identifier (used to construct stage subdirectories).",
    )
    parser.add_argument(
        "--stage",
        action="append",
        dest="stages",
        choices=list(ALL_STAGES),
        help="Validate only the named stage. May be provided multiple times.",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Skip stages whose output directories are absent rather than failing.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable result JSON.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(list(argv or sys.argv[1:]))
    root = Path(args.root)

    try:
        result = validate_all(
            root,
            dataset_id=args.dataset_id,
            stages=args.stages,
            allow_missing=args.allow_missing,
        )
    except ValidationError as exc:
        if args.json:
            print(
                json.dumps(
                    {"ok": False, "dataset_id": args.dataset_id, "errors": [str(exc)]},
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        if result["warnings"]:
            for w in result["warnings"]:
                print(f"  WARNING: {w}")
        if result["ok"]:
            passed = [s for s, v in result["stages"].items() if v.get("ok")]
            print(
                f"PASS: validated EEG signal artifact contracts for "
                f"{', '.join(passed)} (dataset_id={args.dataset_id})"
            )
        else:
            for err in result["errors"]:
                print(f"FAIL: {err}", file=sys.stderr)

    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
