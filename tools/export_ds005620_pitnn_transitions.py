#!/usr/bin/env python3
"""Export TransitionRecordV1 artifacts from the committed ds005620 PITNN/cohort
topology artifact.

Reads the already-computed, git-committed cohort artifact at
`contracts/btc_icft/ds005620/pitnn_cohort/` (`cohort_summary.json`,
`cohort_per_subject.csv`, `pairing.json`, `RunRecord.json`) -- produced by
`tools/analyze_pitnn_cohort_ds005620.py` from
`tools/stream_pitnn_cohort_ds005620.py`'s per-subject output -- and converts
it into `transitions.TransitionRecordV1` artifacts. No raw EEG data is read
or reprocessed here; this is a pure format conversion over an existing,
already-computed real-output artifact, reusing `transitions.record`,
`transitions.metrics`, and `transitions.store` rather than duplicating any
transition-record logic.

`cohort_summary.json` contains **two distinct real feature families** that
must never be conflated, selected via `--feature-set`:

  * `cohort_summary` (default) -- `cohort_per_subject.csv`'s
    persistence-landscape-area / windowed-mean-Betti-1 / mean-PLV summary,
    computed by `tools/analyze_pitnn_cohort_ds005620.py` from per-window
    persistent cubical homology.
  * `spatial_defect_map` -- the *nested*
    `cohort_summary.json["spatial_defect_map"]` block's per-subject
    unsigned topological charge (Q_abs) and a spatially-counted,
    integer-valued Betti-1-like defect/vortex count. This is a genuinely
    different topological measurement method from `cohort_summary`'s
    windowed persistent-homology Betti-1 mean, despite both loosely being
    "beta1"-flavored quantities in the source data -- see
    `docs/transition_science_foundation.md`'s "Two ds005620 feature
    families" section for why they are kept under different canonical
    feature names (`topology.betti1` vs `topology.spatial_defect_betti1`)
    rather than merged.

Usage:
  python tools/export_ds005620_pitnn_transitions.py \\
      --input contracts/btc_icft/ds005620/pitnn_cohort \\
      --out outputs/transitions/ds005620_pitnn \\
      --feature-set cohort_summary

  python tools/export_ds005620_pitnn_transitions.py \\
      --input contracts/btc_icft/ds005620/pitnn_cohort \\
      --out outputs/transitions/ds005620_spatial_defect_map \\
      --feature-set spatial_defect_map
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
_TRANSITION_CLASS = "anesthesia_propofol_awake_to_sedated"
_MODALITY = "EEG"
_TIME_AXIS = {"unit": "condition_summary", "n_samples": 2, "labels": ["awake", "sedated"]}
_ALPHA = 0.05

# ── Feature-set registry ──────────────────────────────────────────────────
#
# Each entry names the exact source-specific meaning of every feature it
# exports, so a downstream reader (or `metadata.feature_definitions` on the
# record itself) never has to guess what a bare "beta1" or "Q_abs" means.
# `feature_set_id` is recorded in `metadata`, not in the deterministic ID
# basis -- the two feature sets already use disjoint `feature_names`, which
# alone guarantees their transition_ids cannot collide (see
# transitions.record.compute_transition_id: dataset/subject/session/state/
# modality/feature_names is the full identity basis). Adding a first-class
# `feature_set_id` field to TransitionRecordV1 was considered and rejected
# as unnecessary schema churn for a collision this metadata-only field
# already prevents; see docs/transition_science_foundation.md.

_COHORT_SUMMARY_FEATURE_NAMES = [
    "topology.persistence_landscape_area",
    "topology.betti1",
    "connectivity.mean_plv",
]
_COHORT_SUMMARY_FEATURE_DEFINITIONS = {
    "topology.persistence_landscape_area": (
        "Integrated persistent-H1 landscape area per condition, computed by "
        "tools/analyze_pitnn_cohort_ds005620.py from "
        "tools/stream_pitnn_cohort_ds005620.py's per-window persistent cubical "
        "homology output (cohort_per_subject.csv column "
        "{awake,sedated}_landscape_area)."
    ),
    "topology.betti1": (
        "Mean H1 Betti number across windows_per_condition persistent-homology "
        "windows per condition (cohort_per_subject.csv column "
        "{awake,sedated}_beta1) -- a fractional per-condition average. This is "
        "NOT the same measurement as the spatial defect map's integer spatial "
        "Betti-1-like count (feature set 'spatial_defect_map', feature "
        "topology.spatial_defect_betti1); do not conflate the two."
    ),
    "connectivity.mean_plv": (
        "Mean pairwise phase-locking value across channel pairs per condition "
        "(cohort_per_subject.csv column {awake,sedated}_mean_plv)."
    ),
}

_SPATIAL_DEFECT_FEATURE_NAMES = [
    "topology.q_abs",
    "topology.spatial_defect_betti1",
]
_SPATIAL_DEFECT_FEATURE_DEFINITIONS = {
    "topology.q_abs": (
        "Unsigned topological charge magnitude (|Q|) of the spatial "
        "defect/vortex map for one condition, from "
        "cohort_summary.json['spatial_defect_map'] (per-subject: "
        "per_subject[].{awake,sedated}_qabs; cohort: "
        "mean_qabs_{awake,sedated})."
    ),
    "topology.spatial_defect_betti1": (
        "Integer count of non-trivial topological loops (a spatially-counted "
        "Betti-1-like quantity) detected in a single spatial defect/vortex map "
        "snapshot per condition, from cohort_summary.json['spatial_defect_map']"
        "['per_subject'][].{awake,sedated}_beta1. This is NOT the same "
        "measurement as the windowed persistent-homology mean used by feature "
        "set 'cohort_summary''s topology.betti1 feature; do not conflate the "
        "two despite the shared 'beta1' short name in the source data."
    ),
}

_FEATURE_SET_REGISTRY: dict[str, dict[str, Any]] = {
    "cohort_summary": {
        "feature_names": _COHORT_SUMMARY_FEATURE_NAMES,
        "feature_definitions": _COHORT_SUMMARY_FEATURE_DEFINITIONS,
        "feature_set_id": "ds005620_pitnn_cohort_summary",
        "default_out": "outputs/transitions/ds005620_pitnn",
    },
    "spatial_defect_map": {
        "feature_names": _SPATIAL_DEFECT_FEATURE_NAMES,
        "feature_definitions": _SPATIAL_DEFECT_FEATURE_DEFINITIONS,
        "feature_set_id": "ds005620_spatial_defect_map",
        "default_out": "outputs/transitions/ds005620_spatial_defect_map",
    },
}


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
        "TransitionRecord exported from existing committed ds005620 PITNN/cohort "
        "topology artifacts (contracts/btc_icft/ds005620/pitnn_cohort/); no raw "
        "data were reprocessed in this step.",
        "Exploratory EEG topology summary; not a clinical anesthesia-depth measure.",
        "This artifact does not validate consciousness detection, treatment "
        "response, mechanistic causality, or spiritual/meditative attainment.",
        "Feature definitions are source-specific (see metadata.feature_definitions "
        "and metadata.feature_set_id) and should not be conflated with other "
        "beta1 or Betti summaries without checking metadata.",
        "Condition labels ('awake', 'sedated') are inherited from source "
        "artifacts and were not independently revalidated by this exporter.",
        "velocity_summary reflects a two-point condition-summary trajectory "
        "(awake -> sedated), not a continuously sampled time series; treat it "
        "as a per-condition-step delta, not a physical rate.",
    ]


def _build_cohort_summary_subject_record(
    row: dict[str, Any],
    *,
    pairing: dict[str, Any],
    preprocessing_provenance: dict[str, Any],
    artifact_paths: dict[str, str],
    repo_commit: str | None,
) -> TransitionRecordV1:
    spec = _FEATURE_SET_REGISTRY["cohort_summary"]
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
        feature_names=list(spec["feature_names"]),
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
            "feature_set_id": spec["feature_set_id"],
            "feature_definitions": dict(spec["feature_definitions"]),
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


def _build_cohort_summary_cohort_record(
    summary: dict[str, Any],
    *,
    preprocessing_provenance: dict[str, Any],
    artifact_paths: dict[str, str],
    repo_commit: str | None,
) -> tuple[TransitionRecordV1, list[list[float]]]:
    spec = _FEATURE_SET_REGISTRY["cohort_summary"]
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
        feature_names=list(spec["feature_names"]),
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
            "feature_set_id": spec["feature_set_id"],
            "feature_definitions": dict(spec["feature_definitions"]),
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


# ── spatial_defect_map feature-set builders ──────────────────────────────

def _build_spatial_defect_subject_record(
    entry: dict[str, Any],
    *,
    pairing: dict[str, Any],
    preprocessing_provenance: dict[str, Any],
    artifact_paths: dict[str, str],
    repo_commit: str | None,
) -> tuple[TransitionRecordV1, list[list[float]]]:
    spec = _FEATURE_SET_REGISTRY["spatial_defect_map"]
    subject = entry.get("subject")
    if not subject:
        raise ExportError("spatial_defect_map.per_subject entry is missing a 'subject' value")

    try:
        awake_vec = [float(entry["awake_qabs"]), float(entry["awake_beta1"])]
        sedated_vec = [float(entry["sedated_qabs"]), float(entry["sedated_beta1"])]
    except (KeyError, ValueError) as exc:
        raise ExportError(
            f"subject {subject!r}: missing or malformed awake/sedated spatial_defect_map "
            f"values ({exc})"
        ) from exc

    trajectory = [awake_vec, sedated_vec]
    delta_summary = trajectory_mean_delta(trajectory)
    velocity_summary = transition_velocity(trajectory)

    limitations = _base_limitations() + [
        "Spatial defect map features are exploratory EEG topology summaries, "
        "not clinical anesthesia-depth measures.",
        "topology.spatial_defect_betti1 is a spatially-counted integer defect "
        "count from a single condition's defect/vortex map, computed by a "
        "different method than the ds005620_pitnn_cohort_summary feature "
        "set's windowed persistent-homology topology.betti1; the two must not "
        "be treated as the same measurement.",
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
        feature_names=list(spec["feature_names"]),
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
            "feature_set_id": spec["feature_set_id"],
            "feature_definitions": dict(spec["feature_definitions"]),
            "source_files": pairing.get(subject, {}),
        },
    )
    errors = record.validate()
    if errors:
        raise TransitionValidationError(
            f"subject {subject!r}: exported spatial-defect record failed validation: {'; '.join(errors)}"
        )
    return record, trajectory


def _build_spatial_defect_cohort_record(
    summary: dict[str, Any],
    *,
    preprocessing_provenance: dict[str, Any],
    artifact_paths: dict[str, str],
    repo_commit: str | None,
) -> tuple[TransitionRecordV1, list[list[float]]]:
    spec = _FEATURE_SET_REGISTRY["spatial_defect_map"]
    spatial = summary.get("spatial_defect_map") or {}
    if not spatial.get("available"):
        raise ExportError("cohort_summary.json['spatial_defect_map'] is missing or not available")

    mean_awake = spatial.get("mean_qabs_awake")
    mean_sedated = spatial.get("mean_qabs_sedated")
    if mean_awake is None or mean_sedated is None:
        raise ExportError(
            "cohort_summary.json['spatial_defect_map'] is missing "
            "mean_qabs_awake/mean_qabs_sedated cohort statistics"
        )

    # Only topology.q_abs has a source-reported cohort-level aggregate; no
    # cohort-level statistic for spatial_defect_betti1 exists in the source
    # artifact, so it is not fabricated here -- it stays subject-level only.
    trajectory = [[float(mean_awake)], [float(mean_sedated)]]
    delta_summary = trajectory_mean_delta(trajectory)
    velocity_summary = transition_velocity(trajectory)

    wilcoxon_qabs = spatial.get("paired_wilcoxon_qabs") or {}
    n_subjects = spatial.get("n_subjects")

    null_control_summary = {
        "status": "not_provided",
        "note": (
            "The source artifact reports a plain paired Wilcoxon signed-rank "
            "test on Q_abs (see metadata.additional_statistics.paired_wilcoxon_qabs), "
            "not a permutation/surrogate-based null-control test; "
            "null_control_summary is reserved for the latter, which this "
            "feature set does not provide in the source artifact."
        ),
    }

    limitations = _base_limitations() + [
        "Spatial defect map features are exploratory EEG topology summaries, "
        "not clinical anesthesia-depth measures.",
        "Cohort-level topology.q_abs uses the source's real mean_qabs_awake/"
        "mean_qabs_sedated values; no cohort-level aggregate for "
        "topology.spatial_defect_betti1 is reported by the source artifact, "
        "so it is included only in subject-level spatial-defect records, not "
        "this cohort record.",
        "A paired Wilcoxon signed-rank test on Q_abs is reported in "
        "metadata.additional_statistics; it is not a permutation-based null "
        "control, so null_control_summary honestly reflects that no such "
        "control is provided for this feature set here.",
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
        feature_names=["topology.q_abs"],
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
            "feature_set_id": spec["feature_set_id"],
            "feature_definitions": {"topology.q_abs": spec["feature_definitions"]["topology.q_abs"]},
            "subject_count": n_subjects,
            "additional_statistics": {"paired_wilcoxon_qabs": wilcoxon_qabs},
        },
    )
    errors = record.validate()
    if errors:
        raise TransitionValidationError(f"spatial-defect cohort record failed validation: {'; '.join(errors)}")
    return record, trajectory


def export(
    input_dir: Path,
    out_dir: Path,
    *,
    include_cohort: bool = True,
    feature_set: str = "cohort_summary",
    registry_path: Path | None = None,
    requested_use: str = "transition_export",
    claim_family: str | None = None,
) -> dict[str, Any]:
    """Export TransitionRecordV1 artifacts for one ds005620 feature set.

    `registry_path` is optional and off by default (None), so existing
    callers and the default CLI invocation are unaffected. When provided,
    this exporter consults `benchmarks.export_registry.BenchmarkRegistry`
    for dataset_id "ds005620" and fails closed (raises ExportError) before
    reading any artifact if `requested_use` is not permitted -- see
    docs/benchmark_dataset_registry.md. This is a discovery-vs-confirmation
    usage check, not a scientific validity check.
    """
    if feature_set not in _FEATURE_SET_REGISTRY:
        raise ExportError(
            f"unknown feature_set {feature_set!r}; choose one of {sorted(_FEATURE_SET_REGISTRY)}"
        )

    if registry_path is not None:
        from benchmarks.export_registry import BenchmarkRegistry, RegistryError

        try:
            registry = BenchmarkRegistry.load(registry_path)
            allowed, reason = registry.check_use("ds005620", requested_use, claim_family=claim_family)
        except RegistryError as exc:
            raise ExportError(f"benchmark registry error: {exc}") from exc
        if not allowed:
            raise ExportError(
                f"benchmark registry denied requested_use={requested_use!r} for "
                f"dataset_id='ds005620': {reason}"
            )

    artifact = _load_artifact(input_dir)
    repo_commit = _git_commit(_REPO_ROOT)
    preprocessing_provenance = _preprocessing_provenance(artifact["summary"], artifact["run_record"])

    store = TransitionStore(out_dir)
    subject_records: list[TransitionRecordV1] = []
    skipped: list[dict[str, str]] = []

    if feature_set == "cohort_summary":
        subject_entries: list[dict[str, Any]] = artifact["per_subject_rows"]
        build_subject_fn = _build_cohort_summary_subject_record
        build_cohort_fn = _build_cohort_summary_cohort_record
    else:  # spatial_defect_map
        spatial = artifact["summary"].get("spatial_defect_map") or {}
        subject_entries = spatial.get("per_subject") or []
        if not subject_entries:
            raise ExportError(
                f"no spatial_defect_map.per_subject data found in {input_dir}/cohort_summary.json"
            )
        build_subject_fn = _build_spatial_defect_subject_record
        build_cohort_fn = _build_spatial_defect_cohort_record

    for entry in subject_entries:
        subject = entry.get("subject", "<unknown>")
        try:
            record, trajectory = build_subject_fn(
                entry,
                pairing=artifact["pairing"],
                preprocessing_provenance=preprocessing_provenance,
                artifact_paths=artifact["artifact_paths"],
                repo_commit=repo_commit,
            )
        except (ExportError, TransitionValidationError) as exc:
            skipped.append({"subject": subject, "reason": str(exc)})
            continue
        store.write(record, trajectory=trajectory, trajectory_columns=record.feature_names)
        subject_records.append(record)

    if not subject_records:
        raise ExportError(
            f"no subjects could be exported from {input_dir} for feature_set={feature_set!r} "
            f"(skipped {len(skipped)}: {skipped})"
        )

    cohort_record = None
    if include_cohort:
        cohort_record, cohort_trajectory = build_cohort_fn(
            artifact["summary"],
            preprocessing_provenance=preprocessing_provenance,
            artifact_paths=artifact["artifact_paths"],
            repo_commit=repo_commit,
        )
        store.write(cohort_record, trajectory=cohort_trajectory, trajectory_columns=cohort_record.feature_names)

    return {
        "subject_records": subject_records,
        "cohort_record": cohort_record,
        "skipped": skipped,
        "out_dir": out_dir,
        "feature_set": feature_set,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--input", type=Path, default=Path("contracts/btc_icft/ds005620/pitnn_cohort"),
        help="directory containing cohort_summary.json + cohort_per_subject.csv "
             "(default: contracts/btc_icft/ds005620/pitnn_cohort)",
    )
    parser.add_argument(
        "--feature-set", choices=sorted(_FEATURE_SET_REGISTRY), default="cohort_summary",
        help="which real feature family in cohort_summary.json to export "
             "(default: cohort_summary)",
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help="output directory for the TransitionStore (default depends on "
             "--feature-set: outputs/transitions/ds005620_pitnn for "
             "cohort_summary, outputs/transitions/ds005620_spatial_defect_map "
             "for spatial_defect_map)",
    )
    parser.add_argument(
        "--no-cohort-record", action="store_true",
        help="skip emitting the cohort-level TransitionRecord",
    )
    parser.add_argument(
        "--registry", type=Path, default=None,
        help="optional benchmarks.export_registry.BenchmarkRegistry JSON path; if given, "
             "fails closed before exporting if --requested-use is not permitted for ds005620 "
             "(default: no registry check, unchanged from prior behavior)",
    )
    parser.add_argument(
        "--requested-use", default="transition_export",
        help="use to check against --registry (default: transition_export; ignored if "
             "--registry is not given)",
    )
    parser.add_argument(
        "--claim-family", default=None,
        help="claim family for --registry validation-use checks (only relevant for "
             "internal_validation/external_validation/confirmatory requested uses)",
    )
    args = parser.parse_args()

    out_dir = args.out or Path(_FEATURE_SET_REGISTRY[args.feature_set]["default_out"])

    try:
        result = export(
            args.input, out_dir, include_cohort=not args.no_cohort_record, feature_set=args.feature_set,
            registry_path=args.registry, requested_use=args.requested_use, claim_family=args.claim_family,
        )
    except (ExportError, TransitionValidationError) as exc:
        print(f"[export_ds005620_pitnn_transitions] FAILED: {exc}")
        return 1

    summary = {
        "feature_set": result["feature_set"],
        "n_subjects_exported": len(result["subject_records"]),
        "n_subjects_skipped": len(result["skipped"]),
        "skipped": result["skipped"],
        "cohort_record_written": result["cohort_record"] is not None,
        "cohort_transition_id": result["cohort_record"].transition_id if result["cohort_record"] else None,
        "out_dir": str(result["out_dir"]),
    }
    if args.registry is not None:
        summary["registry_check"] = {
            "registry_path": str(args.registry),
            "requested_use": args.requested_use,
            "allowed": True,  # export() already raised ExportError above if denied
        }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
