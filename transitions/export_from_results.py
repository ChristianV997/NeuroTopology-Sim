"""Export TransitionRecordV1 artifacts from existing metric CSV/JSON outputs.

Usage::

    python -m transitions.export_from_results \\
        --dataset ds005620 \\
        --input outputs/pitnn_cohort/ds005620/subjects/sub-1010.json \\
        --out artifacts/transitions/ds005620 \\
        --source-state awake --target-state sedated \\
        --transition-class anesthesia_induction \\
        --modality eeg \\
        --subject sub-1010

This is a generic converter: it does not know anything about anesthesia,
meditation, or any other domain. It reads a flat table of already-computed
metrics (one row per timepoint/window), validates or sorts timestamps according
to an explicit `--timestamp-policy` (`reject` or `sort`), maps recognizable
column names onto the canonical feature namespace (transitions.features),
computes elapsed-time rates, and writes a TransitionRecordV1 + trajectory CSV.
State labels are never inferred from filenames, column values, or metric
values — `--source-state`/`--target-state` must be supplied explicitly, or
the export fails closed.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import subprocess
from pathlib import Path
from typing import Any

from transitions.features import CANONICAL_FEATURES, FeatureNameError, validate_feature_name
from transitions.governance import DEFAULT_NULL_CONTROL_SUMMARY
from transitions.metrics import transition_velocity, trajectory_mean_delta
from transitions.record import TransitionRecordV1, TransitionValidationError
from transitions.store import TransitionConflictError, TransitionStore

# Local column name (lowercased, underscored) -> canonical dotted feature
# name, generated from the canonical registry itself so the two never drift.
KNOWN_COLUMN_ALIASES: dict[str, str] = {
    name.split(".", 1)[1]: name for name in CANONICAL_FEATURES
}

NON_FEATURE_COLUMNS: frozenset[str] = frozenset(
    {
        "row_id",
        "subject_id",
        "session_id",
        "sequence_id",
        "condition",
        "state",
        "state_label",
        "label",
        "time",
        "timestamp",
        "t",
        "window_start_s",
        "window_end_s",
    }
)

TIME_COLUMN_CANDIDATES: tuple[str, ...] = ("timestamp", "time", "t", "window_start_s")
VALID_TIMESTAMP_POLICIES: frozenset[str] = frozenset({"reject", "sort"})


class ExportError(ValueError):
    """Raised when the input file cannot be unambiguously exported."""


def _normalize_column(name: str) -> str:
    return name.strip().lower().replace("-", "_").replace(" ", "_")


def _parse_finite_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _load_rows(input_path: Path) -> list[dict[str, Any]]:
    if input_path.suffix.lower() == ".csv":
        with input_path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        if not rows:
            raise ExportError(f"input CSV '{input_path}' has no data rows")
        return rows

    if input_path.suffix.lower() == ".json":
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and "rows" in payload:
            payload = payload["rows"]
        if not isinstance(payload, list) or not payload or not all(
            isinstance(row, dict) for row in payload
        ):
            raise ExportError(
                f"input JSON '{input_path}' must be a non-empty list of flat objects "
                "(or {\"rows\": [...]})"
            )
        return payload

    raise ExportError(f"unsupported input file extension: '{input_path.suffix}' (use .csv or .json)")


def _is_numeric_column(rows: list[dict[str, Any]], column: str) -> bool:
    return all(_parse_finite_float(row.get(column)) is not None for row in rows)


def _infer_feature_columns(rows: list[dict[str, Any]]) -> tuple[list[str], dict[str, str], list[str]]:
    """Return (raw_columns, {raw_column: canonical_feature_name}, skipped_columns)."""
    all_columns = list(rows[0].keys())
    feature_map: dict[str, str] = {}
    skipped: list[str] = []

    for raw_column in all_columns:
        normalized = _normalize_column(raw_column)
        if normalized in NON_FEATURE_COLUMNS:
            continue
        if not _is_numeric_column(rows, raw_column):
            skipped.append(raw_column)
            continue

        if "." in normalized:
            try:
                validate_feature_name(normalized)
                feature_map[raw_column] = normalized
                continue
            except FeatureNameError:
                skipped.append(raw_column)
                continue

        canonical = KNOWN_COLUMN_ALIASES.get(normalized)
        if canonical is not None:
            feature_map[raw_column] = canonical
        else:
            skipped.append(raw_column)

    return all_columns, feature_map, skipped


def _resolve_time_axis(
    rows: list[dict[str, Any]],
    *,
    timestamp_policy: str = "reject",
) -> tuple[list[dict[str, Any]], list[float] | None, dict[str, Any], float | None, bool]:
    """Validate and optionally sort timestamps according to `timestamp_policy`.

    Returns ``(ordered_rows, timestamps_or_none, time_axis_dict, duration, rows_reordered)``.
    """
    if timestamp_policy not in VALID_TIMESTAMP_POLICIES:
        raise ExportError(
            f"invalid timestamp_policy {timestamp_policy!r}; expected one of "
            f"{sorted(VALID_TIMESTAMP_POLICIES)}"
        )

    for candidate in TIME_COLUMN_CANDIDATES:
        for raw_column in rows[0].keys():
            if _normalize_column(raw_column) != candidate:
                continue

            parsed_values: list[float] = []
            for idx, row in enumerate(rows):
                val = _parse_finite_float(row.get(raw_column))
                if val is None:
                    raise ExportError(
                        f"missing or non-finite timestamp in column '{raw_column}' at row {idx}"
                    )
                parsed_values.append(val)

            if len(set(parsed_values)) != len(parsed_values):
                raise ExportError(
                    f"duplicate timestamps detected in column '{raw_column}'; "
                    "elapsed-time transition rates are undefined"
                )

            is_monotonic = all(
                b > a for a, b in zip(parsed_values, parsed_values[1:])
            )
            rows_reordered = False
            ordered_rows = rows
            ordered_ts = parsed_values
            if not is_monotonic:
                if timestamp_policy == "reject":
                    raise ExportError(
                        f"non-monotonic timestamps in column '{raw_column}' under "
                        "timestamp_policy='reject'; reorder input or pass timestamp_policy='sort'"
                    )
                order = sorted(range(len(rows)), key=lambda i: parsed_values[i])
                ordered_rows = [rows[i] for i in order]
                ordered_ts = [parsed_values[i] for i in order]
                rows_reordered = order != list(range(len(rows)))

            duration = (
                float(ordered_ts[-1] - ordered_ts[0]) if len(ordered_ts) >= 2 else None
            )
            time_axis = {
                "unit": "unknown",
                "source_column": raw_column,
                "n_samples": len(ordered_rows),
                "start": ordered_ts[0],
                "end": ordered_ts[-1],
                "timestamp_policy": timestamp_policy,
                "rows_reordered": rows_reordered,
            }
            return ordered_rows, ordered_ts, time_axis, duration, rows_reordered

    return (
        rows,
        None,
        {"unit": "sample_index", "n_samples": len(rows), "timestamp_policy": timestamp_policy},
        None,
        False,
    )


def _git_commit(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def export(
    *,
    dataset_id: str,
    input_path: Path,
    out_dir: Path,
    source_state: str,
    target_state: str,
    transition_class: str,
    modality: str,
    subject_id: str | None = None,
    session_id: str | None = None,
    episode_id: str | None = None,
    intervention: dict[str, Any] | None = None,
    revision_key: str | None = None,
    timestamp_policy: str = "reject",
    overwrite: bool = False,
    claim_scope: str = "computational_artifact",
    evidence_level: str = "L0_computational_artifact",
) -> dict[str, Any]:
    rows = _load_rows(input_path)
    ordered_rows, timestamps, time_axis, duration, rows_reordered = _resolve_time_axis(
        rows, timestamp_policy=timestamp_policy
    )
    all_columns, feature_map, skipped_columns = _infer_feature_columns(ordered_rows)
    if not feature_map:
        raise ExportError(
            f"could not unambiguously infer any feature columns from '{input_path}' "
            f"(columns seen: {all_columns})"
        )

    raw_columns = list(feature_map.keys())
    feature_names = [feature_map[col] for col in raw_columns]
    trajectory = [[float(row[col]) for col in raw_columns] for row in ordered_rows]

    if len(trajectory) < 2:
        insufficient = {"status": "insufficient_data", "reason": "fewer than two timepoints"}
        delta_summary = dict(insufficient)
        velocity_summary = dict(insufficient)
    else:
        delta_summary = trajectory_mean_delta(trajectory)
        velocity_summary = transition_velocity(trajectory, timestamps=timestamps)

    if timestamps is not None:
        ordering_note = (
            f"Timestamps along '{time_axis['source_column']}' were "
            + ("sorted ascending" if rows_reordered else "validated strictly increasing")
            + f" (timestamp_policy='{timestamp_policy}'); velocity_summary uses elapsed time."
        )
    else:
        ordering_note = (
            "No timestamp column was present; duration is omitted (None) and "
            "velocity_summary assumes unit sample-index steps."
        )

    limitations = [
        "This is a transition artifact export, not a validated consciousness "
        "biomarker, clinical assessment, or diagnostic output.",
        "Feature columns were inferred from the input file's column names and "
        "mapped onto the canonical feature namespace via a fixed alias table "
        f"({len(feature_map)} of {len(all_columns)} columns used); verify "
        "feature_names matches the intended metrics before downstream use.",
        ordering_note,
        "null_control_summary is 'not_provided': this exporter does not read "
        "null/surrogate control data from the input file.",
    ]
    if skipped_columns:
        limitations.append(
            f"Columns not mapped to a canonical feature and excluded: {skipped_columns}."
        )
    if not source_state or not target_state:
        limitations.append(
            "source_state/target_state were not both supplied; this record is "
            "restricted to an unlabeled exploratory claim scope."
        )

    record = TransitionRecordV1.make(
        dataset_id=dataset_id,
        subject_id=subject_id,
        session_id=session_id,
        episode_id=episode_id,
        revision_key=revision_key,
        record_level="subject" if subject_id else "cohort",
        modality=modality,
        source_state=source_state or None,
        target_state=target_state or None,
        transition_class=transition_class,
        feature_names=feature_names,
        limitations=limitations,
        claim_scope=claim_scope,
        evidence_level=evidence_level,
        repo_commit=_git_commit(Path(__file__).resolve().parents[1]),
        time_axis=time_axis,
        duration=duration,
        intervention=intervention,
        delta_summary=delta_summary,
        velocity_summary=velocity_summary,
        null_control_summary=dict(DEFAULT_NULL_CONTROL_SUMMARY),
        metadata={
            "input_file": str(input_path),
            "n_rows": len(ordered_rows),
            "column_feature_map": feature_map,
            "skipped_columns": skipped_columns,
        },
    )

    errors = record.validate()
    if errors:
        raise TransitionValidationError(
            f"exported record failed validation and was not written: {'; '.join(errors)}"
        )

    store = TransitionStore(out_dir)
    written = store.write(
        record,
        trajectory=trajectory,
        trajectory_columns=feature_names,
        overwrite=overwrite,
    )

    return {"record": record, "written": written}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dataset", required=True, help="dataset_id")
    parser.add_argument("--input", required=True, type=Path, help="metrics CSV or JSON file")
    parser.add_argument("--out", required=True, type=Path, help="output directory for the TransitionStore")
    parser.add_argument("--source-state", required=True, help="source state label")
    parser.add_argument("--target-state", required=True, help="target state label")
    parser.add_argument("--transition-class", required=True, help="freeform transition category label")
    parser.add_argument("--modality", required=True, help="e.g. eeg, fmri, synthetic")
    parser.add_argument("--subject", default=None, help="subject_id (omit for a cohort-level export)")
    parser.add_argument("--session", default=None, help="session_id")
    parser.add_argument("--episode-id", default=None, help="episode_id for distinct episodes within a session")
    parser.add_argument("--intervention-json", default=None, help="JSON object describing the intervention")
    parser.add_argument("--revision-key", default=None, help="explicit revision/content key to distinguish runs")
    parser.add_argument(
        "--timestamp-policy",
        default="reject",
        choices=sorted(VALID_TIMESTAMP_POLICIES),
        help="how to handle non-monotonic timestamps ('reject' or 'sort')",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="allow overwriting an existing conflicting record/trajectory with the same transition_id",
    )
    parser.add_argument("--claim-scope", default="computational_artifact")
    parser.add_argument("--evidence-level", default="L0_computational_artifact")
    args = parser.parse_args()

    intervention: dict[str, Any] | None = None
    if args.intervention_json:
        try:
            parsed_intervention = json.loads(args.intervention_json)
        except json.JSONDecodeError as exc:
            print(f"[transitions.export_from_results] FAILED: invalid --intervention-json: {exc}")
            return 1
        if not isinstance(parsed_intervention, dict):
            print("[transitions.export_from_results] FAILED: --intervention-json must decode to a JSON object")
            return 1
        intervention = parsed_intervention

    try:
        result = export(
            dataset_id=args.dataset,
            input_path=args.input,
            out_dir=args.out,
            source_state=args.source_state,
            target_state=args.target_state,
            transition_class=args.transition_class,
            modality=args.modality,
            subject_id=args.subject,
            session_id=args.session,
            episode_id=args.episode_id,
            intervention=intervention,
            revision_key=args.revision_key,
            timestamp_policy=args.timestamp_policy,
            overwrite=args.overwrite,
            claim_scope=args.claim_scope,
            evidence_level=args.evidence_level,
        )
    except (ExportError, TransitionValidationError, TransitionConflictError) as exc:
        print(f"[transitions.export_from_results] FAILED: {exc}")
        return 1

    record = result["record"]
    print(
        f"[transitions.export_from_results] transition_id={record.transition_id} "
        f"dataset={record.dataset_id} {record.source_state}->{record.target_state} "
        f"n_features={len(record.feature_names)} -> {result['written']['record']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
