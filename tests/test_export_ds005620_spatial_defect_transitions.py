"""Tests for the spatial_defect_map feature-set path of
tools/export_ds005620_pitnn_transitions.py.

Uses small synthetic fixtures modeled on the real, committed shape of
cohort_summary.json['spatial_defect_map'] (available/mean_qabs_awake/
mean_qabs_sedated/n_subjects/paired_wilcoxon_qabs/per_subject) -- not the
real 20-subject cohort data. No new empirical result is produced or implied
by these fixtures.

The core thing under test: cohort_summary.json's spatial_defect_map.beta1
and cohort_per_subject.csv's beta1 are two different, differently-computed
quantities (see docs/transition_science_foundation.md). This suite proves
the exporter keeps them under different canonical feature names
(topology.spatial_defect_betti1 vs topology.betti1), that the two feature
sets never produce colliding transition_ids for the same subject, and that
every generated record is honest about which measurement it represents.
"""
from __future__ import annotations

import csv
import json

import pytest

from tests.test_export_ds005620_pitnn_transitions import _fixture_csv_rows, _fixture_pairing, _fixture_run_record
from tools.export_ds005620_pitnn_transitions import ExportError, export
from transitions.governance import BLOCKED_CLAIM_SCOPES
from transitions.record import TransitionValidationError
from transitions.store import TransitionStore

_SCHEMA = "NeuroTopologySim.DS005620PITNNCohort.v1"


def _fixture_spatial_per_subject(subjects=("sub-9001", "sub-9002")):
    # Deliberately different numeric identity than cohort_per_subject.csv's
    # fractional beta1 fixture values (1.33/2.67), matching the real
    # artifact's pattern of small plain integers here.
    values = {
        "sub-9001": {"awake_qabs": 1.7e-15, "sedated_qabs": 8.0, "awake_beta1": 2, "sedated_beta1": 3},
        "sub-9002": {"awake_qabs": 4.0, "sedated_qabs": 7.7e-21, "awake_beta1": 2, "sedated_beta1": 4},
    }
    return [{"subject": s, **values[s]} for s in subjects if s in values]


def _fixture_summary_with_spatial(
    *, subjects=("sub-9001", "sub-9002"), spatial_available=True, include_cohort_qabs=True, per_subject=None
):
    spatial: dict = {"available": spatial_available}
    if spatial_available:
        if include_cohort_qabs:
            spatial["mean_qabs_awake"] = 2.85
            spatial["mean_qabs_sedated"] = 5.5
            spatial["paired_wilcoxon_qabs"] = {"p_value": 0.054, "statistic": 53.5}
        spatial["n_subjects"] = len(subjects)
        spatial["per_subject"] = (
            per_subject if per_subject is not None else _fixture_spatial_per_subject(subjects)
        )

    return {
        "schema": _SCHEMA,
        "dataset_id": "ds005620",
        "n_paired_subjects": len(subjects),
        "subjects": list(subjects),
        "acquisition": {
            "sample_rate_hz": 500.0, "n_channels": 65,
            "n_samples_per_condition": 15000, "band_hz": [30.0, 80.0],
            "windows_per_condition": 3,
        },
        "pitnn": {"verdict_counts": {"NOT_SUPPORTED": len(subjects)}},
        "scientific_note": "fixture scientific note",
        "topology_tests": {
            "integrated_landscape_area": {
                "paired_wilcoxon_subject_means": {
                    "median_awake": 0.004, "median_sedated": 0.009,
                    "n_pairs": len(subjects), "p_value": 0.04, "statistic": 5.0, "status": "computed",
                },
                "subject_blocked_permutation": {
                    "p_value": 0.5, "n_permutations": 1000, "seed": 0,
                    "effect_size_d": -0.4, "method": "permutation_test_subject_blocked_paired",
                    "n_a": len(subjects), "n_b": len(subjects), "alternative": "two-sided",
                    "observed_stat": -0.005,
                },
                "mixedlm": {"coef": 0.006, "p_value": 0.0001, "converged": True, "se": 0.001, "n_obs": 12, "n_groups": len(subjects), "method": "mixedlm_random_intercept", "convergence_warning": None},
            },
            "beta1": {
                "paired_wilcoxon_subject_means": {
                    "median_awake": 1.5, "median_sedated": 2.5,
                    "n_pairs": len(subjects), "p_value": 0.5, "statistic": 3.0, "status": "computed",
                },
                "subject_blocked_permutation": {
                    "p_value": 0.5, "n_permutations": 1000, "seed": 0,
                    "effect_size_d": 0.18, "method": "permutation_test_subject_blocked_paired",
                    "n_a": len(subjects), "n_b": len(subjects), "alternative": "two-sided",
                    "observed_stat": 0.45,
                },
                "mixedlm": {"coef": -0.45, "p_value": 0.13, "converged": True, "se": 0.29, "n_obs": 12, "n_groups": len(subjects), "method": "mixedlm_random_intercept", "convergence_warning": None},
            },
            "mean_plv": {
                "paired_wilcoxon_subject_means": {
                    "median_awake": 0.6, "median_sedated": 0.51,
                    "n_pairs": len(subjects), "p_value": 0.18, "statistic": 4.0, "status": "computed",
                },
                "subject_blocked_permutation": {
                    "p_value": 0.5, "n_permutations": 1000, "seed": 0,
                    "effect_size_d": 0.25, "method": "permutation_test_subject_blocked_paired",
                    "n_a": len(subjects), "n_b": len(subjects), "alternative": "two-sided",
                    "observed_stat": 0.043,
                },
                "mixedlm": {"coef": -0.043, "p_value": 0.011, "converged": True, "se": 0.017, "n_obs": 12, "n_groups": len(subjects), "method": "mixedlm_random_intercept", "convergence_warning": None},
            },
        },
        "spatial_defect_map": spatial,
    }


def _write_fixture_dir(tmp_path, *, summary=None, include_pairing=True, include_run_record=True):
    d = tmp_path / "pitnn_cohort_fixture"
    d.mkdir()
    (d / "cohort_summary.json").write_text(
        json.dumps(summary if summary is not None else _fixture_summary_with_spatial()), encoding="utf-8"
    )
    rows = _fixture_csv_rows()
    fieldnames = list(rows[0].keys())
    with (d / "cohort_per_subject.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, restval="")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    if include_pairing:
        (d / "pairing.json").write_text(json.dumps(_fixture_pairing()), encoding="utf-8")
    if include_run_record:
        (d / "RunRecord.json").write_text(json.dumps(_fixture_run_record()), encoding="utf-8")
    return d


# ── Existing cohort-summary export still passes ─────────────────────────────

def test_cohort_summary_export_unaffected_by_spatial_addition(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out", feature_set="cohort_summary")
    assert len(result["subject_records"]) == 2
    assert result["subject_records"][0].feature_names == [
        "topology.persistence_landscape_area", "topology.betti1", "connectivity.mean_plv",
    ]


# ── Subject-level spatial-defect export ──────────────────────────────────────

def test_spatial_defect_subject_export_emits_valid_record(tmp_path):
    input_dir = _write_fixture_dir(tmp_path, summary=_fixture_summary_with_spatial(subjects=("sub-9001",)))
    result = export(input_dir, tmp_path / "out", feature_set="spatial_defect_map", include_cohort=False)

    assert len(result["subject_records"]) == 1
    record = result["subject_records"][0]
    assert record.subject_id == "sub-9001"
    assert record.dataset_id == "ds005620"
    assert record.source_state == "awake"
    assert record.target_state == "sedated"
    assert record.modality == "EEG"
    assert record.claim_scope == "exploratory_metric"
    assert record.evidence_level == "L2_single_subject_real_signal"
    assert record.feature_names == ["topology.q_abs", "topology.spatial_defect_betti1"]
    assert record.null_control_summary["status"] == "not_provided"
    assert record.limitations
    assert record.validate() == []


def test_spatial_defect_two_paired_subjects(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out", feature_set="spatial_defect_map")
    assert len(result["subject_records"]) == 2
    assert {r.subject_id for r in result["subject_records"]} == {"sub-9001", "sub-9002"}


def test_spatial_defect_records_carry_feature_definitions_and_feature_set_id(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out", feature_set="spatial_defect_map")
    for record in result["subject_records"]:
        assert record.metadata["feature_set_id"] == "ds005620_spatial_defect_map"
        assert set(record.metadata["feature_definitions"]) == set(record.feature_names)
    cohort = result["cohort_record"]
    assert cohort.metadata["feature_set_id"] == "ds005620_spatial_defect_map"
    assert set(cohort.metadata["feature_definitions"]) == set(cohort.feature_names)


# ── Semantic non-conflation between the two beta1-flavored quantities ──────

def test_cohort_summary_beta1_and_spatial_defect_beta1_are_different_feature_names(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    cohort_summary_result = export(input_dir, tmp_path / "out1", feature_set="cohort_summary")
    spatial_result = export(input_dir, tmp_path / "out2", feature_set="spatial_defect_map")

    cohort_summary_features = set(cohort_summary_result["subject_records"][0].feature_names)
    spatial_features = set(spatial_result["subject_records"][0].feature_names)

    assert "topology.betti1" in cohort_summary_features
    assert "topology.betti1" not in spatial_features
    assert "topology.spatial_defect_betti1" in spatial_features
    assert "topology.spatial_defect_betti1" not in cohort_summary_features
    assert cohort_summary_features.isdisjoint(spatial_features)


def test_no_transition_id_collision_across_feature_sets_for_same_subject(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    cohort_summary_result = export(input_dir, tmp_path / "out1", feature_set="cohort_summary")
    spatial_result = export(input_dir, tmp_path / "out2", feature_set="spatial_defect_map")

    cohort_summary_by_subject = {r.subject_id: r for r in cohort_summary_result["subject_records"]}
    spatial_by_subject = {r.subject_id: r for r in spatial_result["subject_records"]}

    for subject in cohort_summary_by_subject:
        a = cohort_summary_by_subject[subject].transition_id
        b = spatial_by_subject[subject].transition_id
        assert a != b, f"transition_id collision for {subject} across feature sets"

    # cohort-level records must not collide with each other either
    assert cohort_summary_result["cohort_record"].transition_id != spatial_result["cohort_record"].transition_id


def test_deterministic_ids_stable_across_repeated_spatial_export(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result1 = export(input_dir, tmp_path / "out1", feature_set="spatial_defect_map")
    result2 = export(input_dir, tmp_path / "out2", feature_set="spatial_defect_map")
    ids1 = sorted(r.transition_id for r in result1["subject_records"])
    ids2 = sorted(r.transition_id for r in result2["subject_records"])
    assert ids1 == ids2
    assert result1["cohort_record"].transition_id == result2["cohort_record"].transition_id


# ── Cohort-level spatial-defect export ───────────────────────────────────────

def test_spatial_defect_cohort_record_uses_only_qabs(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out", feature_set="spatial_defect_map")
    cohort = result["cohort_record"]
    assert cohort.feature_names == ["topology.q_abs"]
    assert cohort.record_level == "cohort"
    assert cohort.subject_id is None
    assert cohort.evidence_level == "L4_cross_subject_dataset_specific"
    assert cohort.metadata["subject_count"] == 2


def test_spatial_defect_cohort_null_control_not_provided_not_silently_passed(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out", feature_set="spatial_defect_map")
    status = result["cohort_record"].null_control_summary["status"]
    assert status == "not_provided"
    assert status != "passed"


def test_spatial_defect_cohort_missing_qabs_aggregate_fails(tmp_path):
    input_dir = _write_fixture_dir(
        tmp_path, summary=_fixture_summary_with_spatial(include_cohort_qabs=False)
    )
    with pytest.raises(ExportError, match="mean_qabs_awake"):
        export(input_dir, tmp_path / "out", feature_set="spatial_defect_map")


# ── Fail-closed behavior ─────────────────────────────────────────────────────

def test_missing_spatial_defect_map_block_fails_clearly(tmp_path):
    input_dir = _write_fixture_dir(tmp_path, summary=_fixture_summary_with_spatial(spatial_available=False))
    with pytest.raises(ExportError, match="spatial_defect_map"):
        export(input_dir, tmp_path / "out", feature_set="spatial_defect_map")


def test_missing_spatial_per_subject_data_fails_clearly(tmp_path):
    input_dir = _write_fixture_dir(tmp_path, summary=_fixture_summary_with_spatial(per_subject=[]))
    with pytest.raises(ExportError, match="per_subject"):
        export(input_dir, tmp_path / "out", feature_set="spatial_defect_map")


def test_missing_sedated_qabs_skips_subject_with_reason(tmp_path):
    entry = _fixture_spatial_per_subject(("sub-9001",))[0]
    del entry["sedated_qabs"]
    input_dir = _write_fixture_dir(
        tmp_path, summary=_fixture_summary_with_spatial(subjects=("sub-9001",), per_subject=[entry])
    )
    with pytest.raises(ExportError, match="no subjects could be exported"):
        export(input_dir, tmp_path / "out", feature_set="spatial_defect_map")


def test_missing_awake_beta1_skips_subject_with_reason(tmp_path):
    entry = _fixture_spatial_per_subject(("sub-9001",))[0]
    del entry["awake_beta1"]
    input_dir = _write_fixture_dir(
        tmp_path, summary=_fixture_summary_with_spatial(subjects=("sub-9001",), per_subject=[entry])
    )
    with pytest.raises(ExportError, match="no subjects could be exported"):
        export(input_dir, tmp_path / "out", feature_set="spatial_defect_map")


def test_partial_bad_subject_skipped_not_fatal_when_others_succeed(tmp_path):
    entries = _fixture_spatial_per_subject()
    del entries[0]["awake_beta1"]  # sub-9001 malformed, sub-9002 fine
    input_dir = _write_fixture_dir(tmp_path, summary=_fixture_summary_with_spatial(per_subject=entries))
    result = export(input_dir, tmp_path / "out", feature_set="spatial_defect_map")
    assert len(result["subject_records"]) == 1
    assert result["subject_records"][0].subject_id == "sub-9002"
    assert len(result["skipped"]) == 1
    assert result["skipped"][0]["subject"] == "sub-9001"


# ── Governance ────────────────────────────────────────────────────────────

def test_spatial_defect_no_blocked_claim_scope(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out", feature_set="spatial_defect_map")
    for record in result["subject_records"] + [result["cohort_record"]]:
        assert record.claim_scope not in BLOCKED_CLAIM_SCOPES
        assert record.claim_scope == "exploratory_metric"


def test_spatial_defect_no_banned_overclaim_text(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out", feature_set="spatial_defect_map")
    for record in result["subject_records"] + [result["cohort_record"]]:
        assert record.validate() == []  # includes the banned-phrase scan


def test_spatial_defect_limitations_non_empty(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out", feature_set="spatial_defect_map")
    for record in result["subject_records"] + [result["cohort_record"]]:
        assert len(record.limitations) > 0
        assert all(str(item).strip() for item in record.limitations)


# ── Store compatibility ──────────────────────────────────────────────────────

def test_spatial_defect_records_can_be_read_back_via_transition_store(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    out_dir = tmp_path / "out"
    result = export(input_dir, out_dir, feature_set="spatial_defect_map")
    store = TransitionStore(out_dir)
    for record in result["subject_records"] + [result["cohort_record"]]:
        loaded = store.read(record.transition_id)
        assert loaded.to_dict() == record.to_dict()
        header, rows = store.read_trajectory(record.transition_id)
        assert header == record.feature_names
        assert len(rows) == 2


def test_cli_end_to_end_spatial_defect(tmp_path):
    import subprocess
    import sys
    from pathlib import Path as _Path

    input_dir = _write_fixture_dir(tmp_path)
    out_dir = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, "tools/export_ds005620_pitnn_transitions.py",
         "--input", str(input_dir), "--out", str(out_dir), "--feature-set", "spatial_defect_map"],
        capture_output=True, text=True, cwd=str(_Path(__file__).resolve().parents[1]),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["feature_set"] == "spatial_defect_map"
    assert payload["n_subjects_exported"] == 2
    assert payload["cohort_record_written"] is True
