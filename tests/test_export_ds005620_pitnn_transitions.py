"""Tests for tools/export_ds005620_pitnn_transitions.py.

Uses small synthetic fixtures modeled on the real, committed shape of
`contracts/btc_icft/ds005620/pitnn_cohort/` (cohort_summary.json,
cohort_per_subject.csv, pairing.json, RunRecord.json) -- not the real
20-subject cohort data itself. No new empirical result is produced or
implied by these fixtures; they exist only to exercise the exporter's
parsing/mapping/governance logic quickly and deterministically.
"""
from __future__ import annotations

import csv
import json

import pytest

from tools.export_ds005620_pitnn_transitions import ExportError, export
from transitions.governance import BLOCKED_CLAIM_SCOPES
from transitions.record import TransitionValidationError
from transitions.store import TransitionStore

_SCHEMA = "NeuroTopologySim.DS005620PITNNCohort.v1"


def _fixture_summary(*, subjects=("sub-9001", "sub-9002"), landscape_perm_p=0.5, beta1_perm_p=0.5, plv_perm_p=0.5):
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
                    "p_value": landscape_perm_p, "n_permutations": 1000, "seed": 0,
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
                    "p_value": beta1_perm_p, "n_permutations": 1000, "seed": 0,
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
                    "p_value": plv_perm_p, "n_permutations": 1000, "seed": 0,
                    "effect_size_d": 0.25, "method": "permutation_test_subject_blocked_paired",
                    "n_a": len(subjects), "n_b": len(subjects), "alternative": "two-sided",
                    "observed_stat": 0.043,
                },
                "mixedlm": {"coef": -0.043, "p_value": 0.011, "converged": True, "se": 0.017, "n_obs": 12, "n_groups": len(subjects), "method": "mixedlm_random_intercept", "convergence_warning": None},
            },
        },
        "cubical_persistence_h1_bottleneck": {"available": True, "n_subjects": len(subjects)},
        "spatial_defect_map": {"available": True, "n_subjects": len(subjects)},
    }


def _fixture_csv_rows():
    return [
        {
            "subject": "sub-9001", "bayes_factor": "0.9999995",
            "verdict": "NOT_SUPPORTED",
            "awake_landscape_area": "0.0004", "sedated_landscape_area": "0.010",
            "awake_beta1": "1.3333333333333333", "sedated_beta1": "2.6666666666666665",
            "awake_mean_plv": "0.75", "sedated_mean_plv": "0.40",
        },
        {
            "subject": "sub-9002", "bayes_factor": "0.9999996",
            "verdict": "NOT_SUPPORTED",
            "awake_landscape_area": "0.0060", "sedated_landscape_area": "0.014",
            "awake_beta1": "2.6666666666666665", "sedated_beta1": "3.3333333333333335",
            "awake_mean_plv": "0.54", "sedated_mean_plv": "0.50",
        },
    ]


def _fixture_pairing():
    return {
        "sub-9001": {
            "awake": "ds005620/sub-9001/eeg/sub-9001_task-awake_acq-EC_eeg.vhdr",
            "sedated": "ds005620/sub-9001/eeg/sub-9001_task-sed_acq-rest_run-1_eeg.vhdr",
        },
        "sub-9002": {
            "awake": "ds005620/sub-9002/eeg/sub-9002_task-awake_acq-EC_eeg.vhdr",
            "sedated": "ds005620/sub-9002/eeg/sub-9002_task-sed_acq-rest_run-1_eeg.vhdr",
        },
    }


def _fixture_run_record():
    return {"source": "tools/analyze_pitnn_cohort_ds005620.py", "run_id": "fixture0000000000"}


def _write_fixture_dir(
    tmp_path,
    *,
    summary=None,
    rows=None,
    include_pairing=True,
    include_run_record=True,
    csv_fieldnames=None,
):
    d = tmp_path / "pitnn_cohort_fixture"
    d.mkdir()
    (d / "cohort_summary.json").write_text(json.dumps(summary if summary is not None else _fixture_summary()), encoding="utf-8")

    rows = rows if rows is not None else _fixture_csv_rows()
    fieldnames = csv_fieldnames or [
        "subject", "bayes_factor", "verdict", "awake_landscape_area", "sedated_landscape_area",
        "awake_beta1", "sedated_beta1", "awake_mean_plv", "sedated_mean_plv",
    ]
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


# ── Subject-level export ─────────────────────────────────────────────────────

def test_single_subject_export_emits_valid_record(tmp_path):
    input_dir = _write_fixture_dir(tmp_path, rows=[_fixture_csv_rows()[0]], summary=_fixture_summary(subjects=("sub-9001",)))
    out_dir = tmp_path / "out"

    result = export(input_dir, out_dir, include_cohort=False)

    assert len(result["subject_records"]) == 1
    record = result["subject_records"][0]
    assert record.subject_id == "sub-9001"
    assert record.dataset_id == "ds005620"
    assert record.source_state == "awake"
    assert record.target_state == "sedated"
    assert record.modality == "EEG"
    assert record.claim_scope == "exploratory_metric"
    assert record.null_control_summary["status"] == "not_provided"
    assert record.limitations
    assert record.validate() == []


def test_subject_record_has_correct_delta_direction(tmp_path):
    input_dir = _write_fixture_dir(tmp_path, rows=[_fixture_csv_rows()[0]], summary=_fixture_summary(subjects=("sub-9001",)))
    result = export(input_dir, tmp_path / "out", include_cohort=False)
    record = result["subject_records"][0]
    # awake_mean_plv=0.75, sedated_mean_plv=0.40 -> connectivity.mean_plv is feature index 2
    assert record.feature_names[2] == "connectivity.mean_plv"
    assert record.delta_summary["delta_per_feature"][2] == pytest.approx(0.40 - 0.75)


def test_subject_record_evidence_level_is_conservative(tmp_path):
    input_dir = _write_fixture_dir(tmp_path, rows=[_fixture_csv_rows()[0]], summary=_fixture_summary(subjects=("sub-9001",)))
    result = export(input_dir, tmp_path / "out", include_cohort=False)
    assert result["subject_records"][0].evidence_level == "L2_single_subject_real_signal"


def test_claim_scope_never_stronger_than_exploratory_metric(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out")
    for record in result["subject_records"] + [result["cohort_record"]]:
        assert record.claim_scope in ("computational_artifact", "exploratory_metric")
        assert record.claim_scope not in BLOCKED_CLAIM_SCOPES


# ── Multi-subject export ─────────────────────────────────────────────────────

def test_multi_subject_export_emits_one_record_per_subject(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out")
    assert len(result["subject_records"]) == 2
    assert {r.subject_id for r in result["subject_records"]} == {"sub-9001", "sub-9002"}


def test_multi_subject_export_emits_cohort_record(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out")
    assert result["cohort_record"] is not None
    assert result["cohort_record"].record_level == "cohort"
    assert result["cohort_record"].subject_id is None
    assert result["cohort_record"].metadata["subject_count"] == 2


def test_no_cohort_record_flag_skips_cohort(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out", include_cohort=False)
    assert result["cohort_record"] is None


def test_deterministic_ids_stable_across_repeated_export(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result1 = export(input_dir, tmp_path / "out1")
    result2 = export(input_dir, tmp_path / "out2")
    ids1 = sorted(r.transition_id for r in result1["subject_records"])
    ids2 = sorted(r.transition_id for r in result2["subject_records"])
    assert ids1 == ids2
    assert result1["cohort_record"].transition_id == result2["cohort_record"].transition_id


# ── Fail-closed behavior ─────────────────────────────────────────────────────

def test_missing_input_path_fails(tmp_path):
    with pytest.raises(ExportError, match="does not exist"):
        export(tmp_path / "nonexistent", tmp_path / "out")


def test_missing_cohort_summary_fails(tmp_path):
    d = tmp_path / "bad"
    d.mkdir()
    (d / "cohort_per_subject.csv").write_text("subject,q\nsub-1,1\n", encoding="utf-8")
    with pytest.raises(ExportError, match="cohort_summary.json"):
        export(d, tmp_path / "out")


def test_missing_per_subject_csv_fails(tmp_path):
    d = tmp_path / "bad"
    d.mkdir()
    (d / "cohort_summary.json").write_text(json.dumps(_fixture_summary()), encoding="utf-8")
    with pytest.raises(ExportError, match="cohort_per_subject.csv"):
        export(d, tmp_path / "out")


def test_unsupported_schema_fails_clearly(tmp_path):
    input_dir = _write_fixture_dir(tmp_path, summary={**_fixture_summary(), "schema": "SomeOtherSchema.v9"})
    with pytest.raises(ExportError, match="unsupported cohort_summary.json schema"):
        export(input_dir, tmp_path / "out")


def test_empty_per_subject_csv_fails(tmp_path):
    d = tmp_path / "empty_csv"
    d.mkdir()
    (d / "cohort_summary.json").write_text(json.dumps(_fixture_summary()), encoding="utf-8")
    (d / "cohort_per_subject.csv").write_text(
        "subject,bayes_factor,verdict,awake_landscape_area,sedated_landscape_area,awake_beta1,sedated_beta1,awake_mean_plv,sedated_mean_plv\n",
        encoding="utf-8",
    )
    with pytest.raises(ExportError, match="no subject rows"):
        export(d, tmp_path / "out")


def test_missing_sedated_condition_columns_skips_subject_with_reason(tmp_path):
    rows = [_fixture_csv_rows()[0]]
    del rows[0]["sedated_landscape_area"]
    input_dir = _write_fixture_dir(tmp_path, rows=rows, summary=_fixture_summary(subjects=("sub-9001",)))
    with pytest.raises(ExportError, match="no subjects could be exported"):
        export(input_dir, tmp_path / "out")


def test_missing_awake_condition_columns_skips_subject_with_reason(tmp_path):
    rows = [_fixture_csv_rows()[0]]
    del rows[0]["awake_beta1"]
    input_dir = _write_fixture_dir(tmp_path, rows=rows, summary=_fixture_summary(subjects=("sub-9001",)))
    with pytest.raises(ExportError, match="no subjects could be exported"):
        export(input_dir, tmp_path / "out")


def test_partial_bad_subject_is_skipped_not_fatal_when_others_succeed(tmp_path):
    rows = _fixture_csv_rows()
    del rows[0]["awake_beta1"]  # sub-9001 malformed, sub-9002 fine
    input_dir = _write_fixture_dir(tmp_path, rows=rows)
    result = export(input_dir, tmp_path / "out")
    assert len(result["subject_records"]) == 1
    assert result["subject_records"][0].subject_id == "sub-9002"
    assert len(result["skipped"]) == 1
    assert result["skipped"][0]["subject"] == "sub-9001"
    assert "sub-9001" in result["skipped"][0]["reason"]


def test_missing_topology_tests_entry_fails_for_cohort_record(tmp_path):
    summary = _fixture_summary()
    del summary["topology_tests"]["mean_plv"]
    input_dir = _write_fixture_dir(tmp_path, summary=summary)
    with pytest.raises(ExportError, match="missing topology_tests"):
        export(input_dir, tmp_path / "out")


def test_missing_optional_pairing_and_run_record_does_not_fail(tmp_path):
    input_dir = _write_fixture_dir(tmp_path, include_pairing=False, include_run_record=False)
    result = export(input_dir, tmp_path / "out")
    assert len(result["subject_records"]) == 2


# ── Governance ────────────────────────────────────────────────────────────

def test_no_blocked_claim_scope_ever_used(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out")
    for record in result["subject_records"] + [result["cohort_record"]]:
        assert record.claim_scope not in BLOCKED_CLAIM_SCOPES


def test_no_banned_overclaim_text_in_generated_records(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out")
    for record in result["subject_records"] + [result["cohort_record"]]:
        assert record.validate() == []  # validate() includes the banned-phrase scan


def test_cohort_null_control_status_reflects_real_p_values_failed(tmp_path):
    input_dir = _write_fixture_dir(tmp_path, summary=_fixture_summary(landscape_perm_p=0.5, beta1_perm_p=0.5, plv_perm_p=0.5))
    result = export(input_dir, tmp_path / "out")
    assert result["cohort_record"].null_control_summary["status"] == "failed"


def test_cohort_null_control_status_reflects_real_p_values_passed(tmp_path):
    input_dir = _write_fixture_dir(tmp_path, summary=_fixture_summary(landscape_perm_p=0.01, beta1_perm_p=0.5, plv_perm_p=0.5))
    result = export(input_dir, tmp_path / "out")
    assert result["cohort_record"].null_control_summary["status"] == "passed"


def test_no_experimental_features_used_by_this_exporter(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    result = export(input_dir, tmp_path / "out")
    for record in result["subject_records"] + [result["cohort_record"]]:
        assert not any(name.startswith("experimental.") for name in record.feature_names)


# ── Store compatibility ──────────────────────────────────────────────────────

def test_output_directory_contains_valid_transition_record_json(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    out_dir = tmp_path / "out"
    export(input_dir, out_dir)
    store = TransitionStore(out_dir)
    ids = store.list_records()
    assert len(ids) == 3  # 2 subjects + 1 cohort


def test_records_can_be_read_back_via_transition_store(tmp_path):
    input_dir = _write_fixture_dir(tmp_path)
    out_dir = tmp_path / "out"
    result = export(input_dir, out_dir)
    store = TransitionStore(out_dir)
    for record in result["subject_records"] + [result["cohort_record"]]:
        loaded = store.read(record.transition_id)
        assert loaded.to_dict() == record.to_dict()
        header, rows = store.read_trajectory(record.transition_id)
        assert header == record.feature_names
        assert len(rows) == 2  # awake, sedated


def test_cli_end_to_end(tmp_path):
    import subprocess
    import sys

    input_dir = _write_fixture_dir(tmp_path)
    out_dir = tmp_path / "out"
    result = subprocess.run(
        [sys.executable, "tools/export_ds005620_pitnn_transitions.py",
         "--input", str(input_dir), "--out", str(out_dir)],
        capture_output=True, text=True, cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["n_subjects_exported"] == 2
    assert payload["cohort_record_written"] is True
