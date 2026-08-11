"""Export PhaseSpaceCoordinateV1 artifacts from TransitionRecordV1 artifacts.

Usage::

    python -m phase_space.export_from_transitions \\
        --input outputs/transitions/ds005620_pitnn \\
        --out outputs/phase_space/ds005620_pitnn \\
        --normalization-mode within_record

`--input` accepts either a single `TransitionRecord.json` or a directory
written by `transitions.store.TransitionStore` (one subdirectory per
transition). Nothing is fabricated: axes whose source features are absent
from a record are emitted as `insufficient_data` with the missing feature
names listed, never as a guessed number.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from phase_space.axes import AXIS_NAMES  # noqa: E402
from phase_space.coordinate import ESTIMATOR_VERSION, NORMALIZATION_MODES  # noqa: E402
from phase_space.estimators import estimate_coordinates  # noqa: E402
from phase_space.store import PhaseSpaceStore  # noqa: E402
from phase_space.trajectory import PhaseSpaceTrajectoryV1  # noqa: E402
from transitions.record import TransitionRecordV1  # noqa: E402
from transitions.store import RECORD_FILENAME  # noqa: E402


class ExportError(ValueError):
    """Raised when the input path yields no usable transition records."""


def _load_records(input_path: Path) -> list[tuple[TransitionRecordV1, Path]]:
    """Load one record file, or every record under a TransitionStore dir."""
    if not input_path.exists():
        raise ExportError(f"input path does not exist: {input_path}")

    candidates: list[Path] = []
    if input_path.is_file():
        candidates = [input_path]
    else:
        direct = input_path / RECORD_FILENAME
        if direct.exists():
            candidates = [direct]
        else:
            candidates = sorted(input_path.glob(f"*/{RECORD_FILENAME}"))

    if not candidates:
        raise ExportError(
            f"no {RECORD_FILENAME} found at or under {input_path}; expected a "
            "TransitionRecord.json file or a TransitionStore directory"
        )

    records: list[tuple[TransitionRecordV1, Path]] = []
    failures: list[str] = []
    for path in candidates:
        try:
            record = TransitionRecordV1.from_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError) as exc:
            failures.append(f"{path}: {exc}")
            continue
        if not record.transition_id:
            failures.append(f"{path}: record has no transition_id")
            continue
        records.append((record, path))

    if not records:
        raise ExportError(
            f"no valid transition records could be read from {input_path} "
            f"({len(failures)} failed: {failures})"
        )
    return records


def export(
    input_path: Path,
    out_dir: Path,
    *,
    normalization_mode: str = "within_record",
    axes: Optional[list[str]] = None,
    write_trajectory: bool = True,
    registry_path: Optional[Path] = None,
    requested_use: str = "phase_space_export",
    claim_family: Optional[str] = None,
    mark_seen: bool = False,
    seen_by: str = "exploration",
    updated_registry_out: Optional[Path] = None,
) -> dict[str, Any]:
    """Estimate PhaseSpaceCoordinateV1 records from TransitionRecordV1 input.

    `registry_path` is optional and off by default (None), so existing
    callers and the default CLI invocation are unaffected. When provided,
    every unique `dataset_id` found among the loaded transition records is
    checked against `benchmarks.export_registry.BenchmarkRegistry` for
    `requested_use` (default "phase_space_export"); this exporter fails
    closed (raises ExportError) before writing any coordinate if ANY
    dataset's use is denied -- see docs/benchmark_dataset_registry.md.
    This is a discovery-vs-confirmation usage check, not a scientific
    validity check.

    `mark_seen=True` (only meaningful together with `registry_path`) marks
    every checked dataset as `seen_by="exploration"` (phase-space
    estimation is itself an exploratory computational step; see
    `benchmarks.split_policy.mark_seen`'s vocabulary) with a note
    identifying `phase_space_export` as the consumer, AFTER coordinates
    have been successfully generated. The mutated registry is written only
    to `updated_registry_out` (required whenever `mark_seen=True`) -- the
    file at `registry_path` is never mutated in place.
    """
    if normalization_mode not in NORMALIZATION_MODES:
        raise ExportError(
            f"unknown normalization mode '{normalization_mode}'; choose one of "
            f"{sorted(NORMALIZATION_MODES)}"
        )
    if mark_seen and registry_path is None:
        raise ExportError("mark_seen=True requires registry_path to also be given")
    if mark_seen and updated_registry_out is None:
        raise ExportError(
            "mark_seen=True requires updated_registry_out (never mutates registry_path in place)"
        )

    records = _load_records(input_path)

    registry = None
    registry_decisions: list[dict[str, Any]] = []
    if registry_path is not None:
        from benchmarks.export_registry import BenchmarkRegistry, RegistryError

        try:
            registry = BenchmarkRegistry.load(registry_path)
        except RegistryError as exc:
            raise ExportError(f"benchmark registry error: {exc}") from exc

        dataset_ids = sorted({r.dataset_id for r, _ in records if r.dataset_id})
        denied: list[str] = []
        for dataset_id in dataset_ids:
            try:
                allowed, reason = registry.check_use(dataset_id, requested_use, claim_family=claim_family)
            except RegistryError as exc:
                raise ExportError(f"benchmark registry error for dataset_id={dataset_id!r}: {exc}") from exc
            registry_decisions.append(
                {"dataset_id": dataset_id, "requested_use": requested_use, "allowed": allowed, "reason": reason}
            )
            if not allowed:
                denied.append(f"{dataset_id}: {reason}")
        if denied:
            raise ExportError(
                f"benchmark registry denied requested_use={requested_use!r} for "
                f"{len(denied)} dataset(s): {denied}"
            )

    store = PhaseSpaceStore(out_dir)

    axis_names = list(axes) if axes else list(AXIS_NAMES)
    all_coordinates = []
    per_transition: dict[str, dict[str, int]] = {}
    n_estimated = 0
    n_insufficient = 0
    n_invalid = 0

    for record, source_path in records:
        coordinates = estimate_coordinates(
            record, axes=axis_names, normalization_mode=normalization_mode
        )
        for coord in coordinates:
            coord.provenance["source_record_path"] = str(source_path)
            errors = coord.validate()
            if errors:
                # Never write a coordinate that fails its own validation.
                coord.status = "failed_validation"
                coord.value = None
                coord.confidence = "none"
                coord.metadata["validation_errors"] = errors
                n_invalid += 1
            elif coord.status == "estimated":
                n_estimated += 1
            else:
                n_insufficient += 1

        trajectory = None
        if write_trajectory:
            trajectory = PhaseSpaceTrajectoryV1.from_coordinates(
                coordinates,
                normalization_mode=normalization_mode,
                estimator_version=ESTIMATOR_VERSION,
                provenance={"source_record_path": str(source_path)},
            )

        store.write(record.transition_id, coordinates, trajectory=trajectory)
        all_coordinates.extend(coordinates)
        per_transition[record.transition_id] = {
            "estimated": sum(1 for c in coordinates if c.status == "estimated"),
            "insufficient_data": sum(
                1 for c in coordinates if c.status == "insufficient_data"
            ),
        }

    contamination_updates: list[dict[str, Any]] = []
    updated_registry_path: Optional[str] = None
    if mark_seen and registry is not None:
        for decision in registry_decisions:
            dataset_id = decision["dataset_id"]
            registry.mark_seen(dataset_id, seen_by=seen_by, note="phase_space_export")
            contamination_updates.append(
                {"dataset_id": dataset_id, "seen_by": seen_by, "note": "phase_space_export", "applied": True}
            )
        written = registry.save(updated_registry_out)
        updated_registry_path = str(written)

    return {
        "n_transitions": len(records),
        "n_coordinates": len(all_coordinates),
        "n_estimated": n_estimated,
        "n_insufficient_data": n_insufficient,
        "n_failed_validation": n_invalid,
        "per_transition": per_transition,
        "out_dir": out_dir,
        "normalization_mode": normalization_mode,
        "coordinates": all_coordinates,
        "registry_decisions": registry_decisions,
        "contamination_updates": contamination_updates,
        "updated_registry_path": updated_registry_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--input", required=True, type=Path,
        help="a TransitionRecord.json file, or a TransitionStore directory",
    )
    parser.add_argument(
        "--out", required=True, type=Path,
        help="output directory for the PhaseSpaceStore",
    )
    parser.add_argument(
        "--normalization-mode", default="within_record",
        choices=sorted(NORMALIZATION_MODES),
        help="how coordinate values are scaled (default: within_record)",
    )
    parser.add_argument(
        "--axes", nargs="*", default=None,
        help=f"subset of axes to estimate (default: all -- {list(AXIS_NAMES)})",
    )
    parser.add_argument(
        "--no-trajectory", action="store_true",
        help="skip writing the per-transition PhaseSpaceTrajectory.json",
    )
    parser.add_argument(
        "--registry", type=Path, default=None,
        help="optional benchmarks.export_registry.BenchmarkRegistry JSON path; if given, "
             "fails closed before writing any coordinate if --requested-use is not permitted "
             "for every dataset_id found in the input (default: no registry check, unchanged "
             "from prior behavior)",
    )
    parser.add_argument(
        "--requested-use", default="phase_space_export",
        help="use to check against --registry (default: phase_space_export; ignored if "
             "--registry is not given)",
    )
    parser.add_argument(
        "--claim-family", default=None,
        help="claim family for --registry validation-use checks",
    )
    parser.add_argument(
        "--mark-seen", action="store_true",
        help="after a successful export, mark every dataset_id consumed as "
             "seen_by='exploration' (note: phase_space_export) and write the updated "
             "registry to --updated-registry-out (required together with this flag); "
             "requires --registry",
    )
    parser.add_argument(
        "--seen-by", default="exploration",
        choices=("exploration", "llm", "theory_generation", "model_selection"),
        help="contamination kind recorded by --mark-seen (default: exploration)",
    )
    parser.add_argument(
        "--updated-registry-out", type=Path, default=None,
        help="output path for the updated registry when --mark-seen is given; the file at "
             "--registry is never mutated in place",
    )
    args = parser.parse_args()

    try:
        result = export(
            args.input, args.out,
            normalization_mode=args.normalization_mode,
            axes=args.axes,
            write_trajectory=not args.no_trajectory,
            registry_path=args.registry,
            requested_use=args.requested_use,
            claim_family=args.claim_family,
            mark_seen=args.mark_seen,
            seen_by=args.seen_by,
            updated_registry_out=args.updated_registry_out,
        )
    except ExportError as exc:
        print(f"[phase_space.export_from_transitions] FAILED: {exc}")
        return 1

    summary = {
        "transitions_read": result["n_transitions"],
        "coordinates_total": result["n_coordinates"],
        "coordinates_estimated": result["n_estimated"],
        "coordinates_insufficient_data": result["n_insufficient_data"],
        "coordinates_failed_validation": result["n_failed_validation"],
        "normalization_mode": result["normalization_mode"],
        "out_dir": str(result["out_dir"]),
    }
    if args.registry is not None:
        summary["registry_decisions"] = result["registry_decisions"]
    if args.mark_seen:
        summary["contamination_updates"] = result["contamination_updates"]
        summary["updated_registry_path"] = result["updated_registry_path"]
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
