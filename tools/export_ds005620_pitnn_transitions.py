#!/usr/bin/env python3
"""Export TransitionRecordV1 artifacts from the committed ds005620 PITNN/cohort
topology artifact.

Reads the already-computed, git-committed cohort artifact at
`contracts/btc_icft/ds005620/pitnn_cohort/` (`cohort_summary.json`,
`cohort_per_subject.csv`, `pairing.json`, `RunRecord.json`) -- produced by
`tools/analyze_pitnn_cohort_ds005620.py` from
`tools/stream_pitnn_cohort_ds005620.py`'s per-subject output -- and converts
it into `transitions.TransitionRecordV1` artifacts: one per subject with a
paired awake/sedated summary, plus one cohort-level record built from the
same artifact's subject-median statistics. No raw EEG data is read or
reprocessed here; this is a pure format conversion over an existing,
already-computed real-output artifact, reusing `transitions.record`,
`transitions.metrics`, and `transitions.store` rather than duplicating any
transition-record logic.

Usage:
  python tools/export_ds005620_pitnn_transitions.py \\
      --input contracts/btc_icft/ds005620/pitnn_cohort \\
      --out outputs/transitions/ds005620_pitnn
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from transitions.metrics import trajectory_mean_delta, transition_velocity  # noqa: E402
from transitions.record import TransitionRecordV1, TransitionValidationError  # noqa: E402
from transitions.store import TransitionStore  # noqa: E402

_EXPECTED_SCHEMA = "NeuroTopologySim.DS005620PITNNCohort.v1"
_FEATURE_NAMES = [
    "topology.persistence_landscape_area",
    "topology.betti1",
    "connectivity.mean_plv",
]
_TRANSITION_CLASS = "anesthesia_propofol_awake_to_sedated"
_MODALITY = "EEG"
_TIME_AXIS = {"unit": "condition_summary", "n_samples": 2, "labels": ["awake", "sedated"]}
_ALPHA = 0.05


class ExportError(ValueError):
    """Raised when the input artifact is missing or structurally malformed."""


def _git_commit(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root,
            capture_output=True, text=True, timeout=5, check=True,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_REPO_ROOT))
    except ValueError:
        return str(path)


def _load_artifact(input_dir: Path) -> dict[str, Any]:
    if not input_dir.exists():
        raise ExportError(f"input path does not exist: {input_dir}")

    summary_path = input_dir / "cohort_summary.json"
    csv_path = input_dir / "cohort_per_subject.csv"
    pairing_path = input_dir / "pairing.json"
    run_record_path = input_dir / "RunRecord.json"

    if not summary_path.exists():
        raise ExportError(f"cohort_summary.json not found under {input_dir}")
    if not csv_path.exists():
        raise ExportError(f"cohort_per_subject.csv not found under {input_dir}")

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    schema = summary.get("schema")
    if schema != _EXPECTED_SCHEMA:
        raise ExportError(
            f"unsupported cohort_summary.json schema: {schema!r} (expected {_EXPECTED_SCHEMA!r})"
        )

    with csv_path.open(newline="", encoding="utf-8") as handle:
        per_subject_rows = list(csv.DictReader(handle))
    if not per_subject_rows:
        raise ExportError(f"cohort_per_subject.csv at {csv_path} has no subject rows")

    pairing = json.loads(pairing_path.read_text(encoding="utf-8")) if pairing_path.exists() else {}
    run_record = json.loads(run_record_path.read_text(encoding="utf-8")) if run_record_path.exists() else {}

    artifact_paths = {"cohort_summary": _relative_path(summary_path), "cohort_per_subject_csv": _relative_path(csv_path)}
    if pairing_path.exists():
        artifact_paths["pairing"] = _relative_path(pairing_path)
    if run_record_path.exists():
        artifact_paths["run_record"] = _relative_path(run_record_path)

    return {
        "summary": summary,
        "per_subject_rows": per_subject_rows,
        "pairing": pairing,
        "run_record": run_record,
        "artifact_paths": artifact_paths,
    }


def _preprocessing_provenance(summary: dict[str, Any], run_record: dict[str, Any]) -> dict[str, Any]:
    acquisition = summary.get("acquisition", {})
    return {
        "sample_rate_hz": acquisition.get("sample_rate_hz"),
        "n_channels": acquisition.get("n_channels"),
        "n_samples_per_condition": acquisition.get("n_samples_per_condition"),
        "band_hz": acquisition.get("band_hz"),
        "windows_per_condition": acquisition.get("windows_per_condition"),
        "betti1_definition": (
            "mean H1 Betti number across windows_per_condition windows per "
            "condition (a fractional per-condition average, not a single-window count)"
        ),
        "source_tool": run_record.get("source", "tools/analyze_pitnn_cohort_ds005620.py"),
        "upstream_tool": "tools/stream_pitnn_cohort_ds005620.py",
    }


def _base_limitations() -> list[str]:
    return [
        "TransitionRecord exported from the existing, already-computed ds005620 "
        "PITNN/cohort topology artifact (contracts/btc_icft/ds005620/pitnn_cohort/); "
        "no raw EEG data were reprocessed in this export step.",
        "Exploratory EEG topology artifact; not a clinical anesthesia-depth measure.",
        "Does not validate consciousness detection, treatment response, or "
        "mechanistic causal interpretation.",
        "Condition labels ('awake', 'sedated') are inherited from the source "
        "artifact's own pairing.json / cohort analysis and were not "
        "independently re-verified by this exporter.",
        "velocity_summary reflects a two-point condition-summary trajectory "
        "(awake -> sedated), not a continuously sampled time series; treat it "
        "as a per-condition-step delta, not a physical rate.",
    ]


def _build_subject_record(
    row: dict[str, Any],
    *,
    pairing: dict[str, Any],
    preprocessing_provenance: dict[str, Any],
    artifact_paths: dict[str, str],
    repo_commit: str | None,
) -> TransitionRecordV1:
    subject = row.get("subject")
    if not subject:
        raise ExportError("cohort_per_subject.csv row is missing a 'subject' value")

    try:
        awake_vec = [
            float(row["awake_landscape_area"]),
            float(row["awake_beta1"]),
            float(row["awake_mean_plv"]),
        ]
        sedated_vec = [
            float(row["sedated_landscape_area"]),
            float(row["sedated_beta1"]),
            float(row["sedated_mean_plv"]),
        ]
    except (KeyError, ValueError) as exc:
        raise ExportError(
            f"subject {subject!r}: missing or malformed awake/sedated feature values "
            f"in cohort_per_subject.csv ({exc})"
        ) from exc

    trajectory = [awake_vec, sedated_vec]
    delta_summary = trajectory_mean_delta(trajectory)
    velocity_summary = transition_velocity(trajectory)

    bayes_factor_raw = row.get("bayes_factor")
    bayes_factor = float(bayes_factor_raw) if bayes_factor_raw not in (None, "") else None
    verdict = row.get("verdict") or None

    limitations = _base_limitations() + [
        f"PITNN Bayes-factor hypothesis was {verdict or 'not evaluated'} for this "
        f"subject in the source cohort analysis (bayes_factor={bayes_factor}); "
        "PASS is reserved strictly for Bayes factor K > 100.",
    ]

    record = TransitionRecordV1.make(
        dataset_id="ds005620",
        subject_id=subject,
        session_id=None,
        record_level="subject",
        modality=_MODALITY,
        source_state="awake",
        target_state="sedated",
        transition_class=_TRANSITION_CLASS,
        feature_names=list(_FEATURE_NAMES),
        limitations=limitations,
        claim_scope="exploratory_metric",
        evidence_level="L2_single_subject_real_signal",
        repo_commit=repo_commit,
        time_axis=dict(_TIME_AXIS),
        duration=None,
        delta_summary=delta_summary,
        velocity_summary=velocity_summary,
        null_control_summary={"status": "not_provided"},
        preprocessing_provenance=preprocessing_provenance,
        artifact_paths=dict(artifact_paths),
        metadata={
            "bayes_factor": bayes_factor,
            "pitnn_verdict": verdict,
            "source_files": pairing.get(subject, {}),
        },
    )
    errors = record.validate()
    if errors:
        raise TransitionValidationError(
            f"subject {subject!r}: exported record failed validation: {'; '.join(errors)}"
        )
    return record, trajectory


def _feature_stat(topology_tests: dict[str, Any], name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    stat = topology_tests.get(name, {})
    return stat.get("paired_wilcoxon_subject_means", {}), stat.get("subject_blocked_permutation", {})


def _build_cohort_record(
    summary: dict[str, Any],
    *,
    preprocessing_provenance: dict[str, Any],
    artifact_paths: dict[str, str],
    repo_commit: str | None,
) -> tuple[TransitionRecordV1, list[list[float]]]:
    topology_tests = summary.get("topology_tests", {})

    landscape_wilcoxon, landscape_perm = _feature_stat(topology_tests, "integrated_landscape_area")
    beta1_wilcoxon, beta1_perm = _feature_stat(topology_tests, "beta1")
    plv_wilcoxon, plv_perm = _feature_stat(topology_tests, "mean_plv")

    missing = [
        name for name, w in (
            ("integrated_landscape_area", landscape_wilcoxon),
            ("beta1", beta1_wilcoxon),
            ("mean_plv", plv_wilcoxon),
        ) if not w
    ]
    if missing:
        raise ExportError(f"cohort_summary.json is missing topology_tests entries for: {missing}")

    awake_vec = [
        float(landscape_wilcoxon["median_awake"]),
        float(beta1_wilcoxon["median_awake"]),
        float(plv_wilcoxon["median_awake"]),
    ]
    sedated_vec = [
        float(landscape_wilcoxon["median_sedated"]),
        float(beta1_wilcoxon["median_sedated"]),
        float(plv_wilcoxon["median_sedated"]),
    ]
    trajectory = [awake_vec, sedated_vec]
    delta_summary = trajectory_mean_delta(trajectory)
    velocity_summary = transition_velocity(trajectory)

    per_feature_null = {
        "topology.persistence_landscape_area": landscape_perm,
        "topology.betti1": beta1_perm,
        "connectivity.mean_plv": plv_perm,
    }
    any_significant = any(
        (isinstance(p.get("p_value"), (int, float)) and p["p_value"] < _ALPHA)
        for p in per_feature_null.values()
    )
    null_control_summary = {
        "status": "passed" if any_significant else "failed",
        "method": "permutation_test_subject_blocked_paired",
        "alpha": _ALPHA,
        "per_feature": per_feature_null,
        "note": (
            "Subject-blocked permutation p-values against a label-shuffled null, "
            "one per exported topology feature (see per_feature). "
            + (
                "At least one feature reached p < 0.05."
                if any_significant else
                "None of the three reached p < 0.05; the null hypothesis of no "
                "awake/sedated difference could not be rejected for these "
                "features in this cohort at the subject-blocked permutation level."
            )
        ),
    }

    n_paired = summary.get("n_paired_subjects")
    pitnn = summary.get("pitnn", {})

    limitations = _base_limitations() + [
        "Cohort-level summary built from per-feature subject medians "
        "(paired_wilcoxon_subject_means) in the source artifact, not from "
        "individual subject trajectories.",
        f"PITNN Bayes-factor hypothesis verdict distribution in the source "
        f"cohort analysis: {pitnn.get('verdict_counts', 'not reported')}; PASS "
        "is reserved strictly for Bayes factor K > 100.",
        "MixedLM random-intercept models on the same underlying data reported "
        "smaller p-values for some features (see metadata.additional_statistics); "
        "subject-blocked permutation is used here as the more conservative "
        "null-control criterion and is the only test summarized in "
        "null_control_summary.",
    ]

    record = TransitionRecordV1.make(
        dataset_id="ds005620",
        subject_id=None,
        session_id=None,
        record_level="cohort",
        modality=_MODALITY,
        source_state="awake",
        target_state="sedated",
        transition_class=_TRANSITION_CLASS,
        feature_names=list(_FEATURE_NAMES),
        limitations=limitations,
        claim_scope="exploratory_metric",
        evidence_level="L4_cross_subject_dataset_specific",
        repo_commit=repo_commit,
        time_axis=dict(_TIME_AXIS),
        duration=None,
        delta_summary=delta_summary,
        velocity_summary=velocity_summary,
        null_control_summary=null_control_summary,
        preprocessing_provenance=preprocessing_provenance,
        artifact_paths=dict(artifact_paths),
        metadata={
            "subject_count": n_paired,
            "pitnn_verdict_counts": pitnn.get("verdict_counts"),
            "additional_statistics": {
                "mixedlm": {
                    "topology.persistence_landscape_area": topology_tests.get("integrated_landscape_area", {}).get("mixedlm"),
                    "topology.betti1": topology_tests.get("beta1", {}).get("mixedlm"),
                    "connectivity.mean_plv": topology_tests.get("mean_plv", {}).get("mixedlm"),
                },
                "paired_wilcoxon_subject_means": {
                    "topology.persistence_landscape_area": landscape_wilcoxon,
                    "topology.betti1": beta1_wilcoxon,
                    "connectivity.mean_plv": plv_wilcoxon,
                },
            },
        },
    )
    errors = record.validate()
    if errors:
        raise TransitionValidationError(f"cohort record failed validation: {'; '.join(errors)}")
    return record, trajectory


def export(input_dir: Path, out_dir: Path, *, include_cohort: bool = True) -> dict[str, Any]:
    artifact = _load_artifact(input_dir)
    repo_commit = _git_commit(_REPO_ROOT)
    preprocessing_provenance = _preprocessing_provenance(artifact["summary"], artifact["run_record"])

    store = TransitionStore(out_dir)
    subject_records: list[TransitionRecordV1] = []
    skipped: list[dict[str, str]] = []

    for row in artifact["per_subject_rows"]:
        subject = row.get("subject", "<unknown>")
        try:
            record, trajectory = _build_subject_record(
                row,
                pairing=artifact["pairing"],
                preprocessing_provenance=preprocessing_provenance,
                artifact_paths=artifact["artifact_paths"],
                repo_commit=repo_commit,
            )
        except (ExportError, TransitionValidationError) as exc:
            skipped.append({"subject": subject, "reason": str(exc)})
            continue
        store.write(record, trajectory=trajectory, trajectory_columns=_FEATURE_NAMES)
        subject_records.append(record)

    if not subject_records:
        raise ExportError(
            f"no subjects could be exported from {input_dir} "
            f"(skipped {len(skipped)}: {skipped})"
        )

    cohort_record = None
    if include_cohort:
        cohort_record, cohort_trajectory = _build_cohort_record(
            artifact["summary"],
            preprocessing_provenance=preprocessing_provenance,
            artifact_paths=artifact["artifact_paths"],
            repo_commit=repo_commit,
        )
        store.write(cohort_record, trajectory=cohort_trajectory, trajectory_columns=_FEATURE_NAMES)

    return {
        "subject_records": subject_records,
        "cohort_record": cohort_record,
        "skipped": skipped,
        "out_dir": out_dir,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--input", type=Path, default=Path("contracts/btc_icft/ds005620/pitnn_cohort"),
        help="directory containing cohort_summary.json + cohort_per_subject.csv "
             "(default: contracts/btc_icft/ds005620/pitnn_cohort)",
    )
    parser.add_argument(
        "--out", type=Path, default=Path("outputs/transitions/ds005620_pitnn"),
        help="output directory for the TransitionStore (default: outputs/transitions/ds005620_pitnn)",
    )
    parser.add_argument(
        "--no-cohort-record", action="store_true",
        help="skip emitting the cohort-level TransitionRecord",
    )
    args = parser.parse_args()

    try:
        result = export(args.input, args.out, include_cohort=not args.no_cohort_record)
    except (ExportError, TransitionValidationError) as exc:
        print(f"[export_ds005620_pitnn_transitions] FAILED: {exc}")
        return 1

    summary = {
        "n_subjects_exported": len(result["subject_records"]),
        "n_subjects_skipped": len(result["skipped"]),
        "skipped": result["skipped"],
        "cohort_record_written": result["cohort_record"] is not None,
        "cohort_transition_id": result["cohort_record"].transition_id if result["cohort_record"] else None,
        "out_dir": str(result["out_dir"]),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
