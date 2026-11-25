"""Tests for transitions.export_from_results — the CLI/library exporter."""
from __future__ import annotations

import csv
import json

import pytest

from transitions.export_from_results import ExportError, export
from transitions.record import TransitionValidationError
from transitions.store import TransitionConflictError, TransitionStore


def _write_csv(path, rows, fieldnames):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


_FIELDNAMES = ["row_id", "subject_id", "window_start_s", "q_net", "q_abs", "mean_plv", "condition"]
_ROWS = [
    {"row_id": "r1", "subject_id": "sub-1010", "window_start_s": "0.0", "q_net": "0.10", "q_abs": "0.20", "mean_plv": "0.50", "condition": "awake"},
    {"row_id": "r2", "subject_id": "sub-1010", "window_start_s": "10.0", "q_net": "0.30", "q_abs": "0.25", "mean_plv": "0.60", "condition": "awake"},
    {"row_id": "r3", "subject_id": "sub-1010", "window_start_s": "20.0", "q_net": "0.80", "q_abs": "0.40", "mean_plv": "0.70", "condition": "sedated"},
]


def test_export_from_csv_writes_record_and_trajectory(tmp_path):
    input_csv = tmp_path / "metrics.csv"
    _write_csv(input_csv, _ROWS, _FIELDNAMES)
    out_dir = tmp_path / "out"

    result = export(
        dataset_id="ds005620", input_path=input_csv, out_dir=out_dir,
        source_state="awake", target_state="sedated",
        transition_class="anesthesia_induction", modality="eeg",
        subject_id="sub-1010",
    )

    record = result["record"]
    assert record.dataset_id == "ds005620"
    assert record.source_state == "awake"
    assert record.target_state == "sedated"
    assert set(record.feature_names) == {"topology.q_net", "topology.q_abs", "connectivity.mean_plv"}
    assert record.validate() == []

    store = TransitionStore(out_dir)
    loaded = store.read(record.transition_id)
    assert loaded.to_dict() == record.to_dict()
    header, rows = store.read_trajectory(record.transition_id)
    assert len(rows) == 3


def test_export_from_json_list_of_dicts(tmp_path):
    input_json = tmp_path / "metrics.json"
    input_json.write_text(json.dumps(_ROWS), encoding="utf-8")
    out_dir = tmp_path / "out"

    result = export(
        dataset_id="ds005620", input_path=input_json, out_dir=out_dir,
        source_state="awake", target_state="sedated",
        transition_class="anesthesia_induction", modality="eeg",
    )
    assert result["record"].validate() == []


def test_export_from_json_rows_wrapper(tmp_path):
    input_json = tmp_path / "metrics.json"
    input_json.write_text(json.dumps({"rows": _ROWS}), encoding="utf-8")
    out_dir = tmp_path / "out"

    result = export(
        dataset_id="ds005620", input_path=input_json, out_dir=out_dir,
        source_state="awake", target_state="sedated",
        transition_class="anesthesia_induction", modality="eeg",
    )
    assert result["record"].validate() == []


def test_export_without_subject_is_cohort_level(tmp_path):
    input_csv = tmp_path / "metrics.csv"
    _write_csv(input_csv, _ROWS, _FIELDNAMES)
    out_dir = tmp_path / "out"

    result = export(
        dataset_id="ds005620", input_path=input_csv, out_dir=out_dir,
        source_state="awake", target_state="sedated",
        transition_class="anesthesia_induction", modality="eeg",
        subject_id=None,
    )
    assert result["record"].record_level == "cohort"
    assert result["record"].subject_id is None


def test_export_infers_time_axis_from_window_start_column(tmp_path):
    input_csv = tmp_path / "metrics.csv"
    _write_csv(input_csv, _ROWS, _FIELDNAMES)
    out_dir = tmp_path / "out"

    result = export(
        dataset_id="ds005620", input_path=input_csv, out_dir=out_dir,
        source_state="awake", target_state="sedated",
        transition_class="anesthesia_induction", modality="eeg",
    )
    record = result["record"]
    assert record.time_axis["source_column"] == "window_start_s"
    assert record.duration == 20.0


def test_export_default_claim_scope_and_evidence_level_are_conservative(tmp_path):
    input_csv = tmp_path / "metrics.csv"
    _write_csv(input_csv, _ROWS, _FIELDNAMES)
    out_dir = tmp_path / "out"
    result = export(
        dataset_id="ds005620", input_path=input_csv, out_dir=out_dir,
        source_state="awake", target_state="sedated",
        transition_class="anesthesia_induction", modality="eeg",
    )
    assert result["record"].claim_scope == "computational_artifact"
    assert result["record"].evidence_level == "L0_computational_artifact"


def test_export_null_control_summary_defaults_to_not_provided(tmp_path):
    input_csv = tmp_path / "metrics.csv"
    _write_csv(input_csv, _ROWS, _FIELDNAMES)
    out_dir = tmp_path / "out"
    result = export(
        dataset_id="ds005620", input_path=input_csv, out_dir=out_dir,
        source_state="awake", target_state="sedated",
        transition_class="anesthesia_induction", modality="eeg",
    )
    assert result["record"].null_control_summary == {"status": "not_provided"}


def test_export_records_limitations_mentioning_not_a_biomarker(tmp_path):
    input_csv = tmp_path / "metrics.csv"
    _write_csv(input_csv, _ROWS, _FIELDNAMES)
    out_dir = tmp_path / "out"
    result = export(
        dataset_id="ds005620", input_path=input_csv, out_dir=out_dir,
        source_state="awake", target_state="sedated",
        transition_class="anesthesia_induction", modality="eeg",
    )
    joined = " ".join(result["record"].limitations).lower()
    assert "not a validated consciousness" in joined


def test_export_with_no_numeric_columns_fails_closed(tmp_path):
    input_csv = tmp_path / "metrics.csv"
    _write_csv(
        input_csv,
        [{"row_id": "r1", "subject_id": "s1", "window_start_s": "0.0", "q_net": "", "q_abs": "", "mean_plv": "", "condition": "awake"}],
        _FIELDNAMES,
    )
    out_dir = tmp_path / "out"
    with pytest.raises(ExportError):
        export(
            dataset_id="ds005620", input_path=input_csv, out_dir=out_dir,
            source_state="awake", target_state="sedated",
            transition_class="anesthesia_induction", modality="eeg",
        )


def test_export_unsupported_extension_fails_closed(tmp_path):
    input_path = tmp_path / "metrics.txt"
    input_path.write_text("not a csv or json", encoding="utf-8")
    with pytest.raises(ExportError):
        export(
            dataset_id="ds005620", input_path=input_path, out_dir=tmp_path / "out",
            source_state="awake", target_state="sedated",
            transition_class="anesthesia_induction", modality="eeg",
        )


def test_export_empty_csv_fails_closed(tmp_path):
    input_csv = tmp_path / "metrics.csv"
    input_csv.write_text("row_id,q_net\n", encoding="utf-8")
    with pytest.raises(ExportError):
        export(
            dataset_id="ds005620", input_path=input_csv, out_dir=tmp_path / "out",
            source_state="awake", target_state="sedated",
            transition_class="anesthesia_induction", modality="eeg",
        )


def test_export_claim_scope_stronger_than_supported_evidence_fails_validation(tmp_path):
    input_csv = tmp_path / "metrics.csv"
    _write_csv(input_csv, _ROWS, _FIELDNAMES)
    out_dir = tmp_path / "out"
    with pytest.raises(TransitionValidationError):
        export(
            dataset_id="ds005620", input_path=input_csv, out_dir=out_dir,
            source_state="awake", target_state="sedated",
            transition_class="anesthesia_induction", modality="eeg",
            claim_scope="dataset_specific",  # state_label_confidence never supplied by this exporter
            evidence_level="L3_dataset_specific_effect",
        )


def test_cli_main_missing_required_args_exits_nonzero():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "transitions.export_from_results"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0


def test_cli_main_end_to_end(tmp_path):
    import subprocess
    import sys

    input_csv = tmp_path / "metrics.csv"
    _write_csv(input_csv, _ROWS, _FIELDNAMES)
    out_dir = tmp_path / "out"

    result = subprocess.run(
        [
            sys.executable, "-m", "transitions.export_from_results",
            "--dataset", "ds005620", "--input", str(input_csv), "--out", str(out_dir),
            "--source-state", "awake", "--target-state", "sedated",
            "--transition-class", "anesthesia_induction", "--modality", "eeg",
            "--subject", "sub-1010",
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "transition_id=" in result.stdout
    store = TransitionStore(out_dir)
    assert len(store.list_records()) == 1


def test_export_irregular_sampling_computes_elapsed_time_velocity(tmp_path):
    irregular_rows = [
        {"row_id": "r1", "subject_id": "sub-1010", "window_start_s": "0.0", "q_net": "0.0", "q_abs": "1.0", "mean_plv": "0.2", "condition": "awake"},
        {"row_id": "r2", "subject_id": "sub-1010", "window_start_s": "2.0", "q_net": "4.0", "q_abs": "3.0", "mean_plv": "0.6", "condition": "awake"},
        {"row_id": "r3", "subject_id": "sub-1010", "window_start_s": "10.0", "q_net": "12.0", "q_abs": "11.0", "mean_plv": "1.4", "condition": "sedated"},
    ]
    input_csv = tmp_path / "irregular.csv"
    _write_csv(input_csv, irregular_rows, _FIELDNAMES)
    out_dir = tmp_path / "out"

    result = export(
        dataset_id="ds005620", input_path=input_csv, out_dir=out_dir,
        source_state="awake", target_state="sedated",
        transition_class="anesthesia_induction", modality="eeg",
        subject_id="sub-1010",
    )
    rec = result["record"]
    assert rec.duration == pytest.approx(10.0)
    v = rec.velocity_summary["velocity_per_step"]
    # Step 1 (dt=2.0): dq_net/dt = 4.0/2.0 = 2.0, dq_abs/dt = 1.0, dplv/dt = 0.2
    assert v[0] == pytest.approx([2.0, 1.0, 0.2])
    # Step 2 (dt=8.0): dq_net/dt = 8.0/8.0 = 1.0, dq_abs/dt = 1.0, dplv/dt = 0.1
    assert v[1] == pytest.approx([1.0, 1.0, 0.1])


def test_export_reordered_rows_reject_vs_sort_policy(tmp_path):
    reordered_rows = [_ROWS[2], _ROWS[0], _ROWS[1]]  # 20.0, 0.0, 10.0
    reordered_csv = tmp_path / "reordered.csv"
    _write_csv(reordered_csv, reordered_rows, _FIELDNAMES)

    ordered_csv = tmp_path / "ordered.csv"
    _write_csv(ordered_csv, _ROWS, _FIELDNAMES)

    with pytest.raises(ExportError, match="non-monotonic timestamps"):
        export(
            dataset_id="ds005620", input_path=reordered_csv, out_dir=tmp_path / "out_reject",
            source_state="awake", target_state="sedated",
            transition_class="anesthesia_induction", modality="eeg",
            subject_id="sub-1010", timestamp_policy="reject",
        )

    res_ordered = export(
        dataset_id="ds005620", input_path=ordered_csv, out_dir=tmp_path / "out_ordered",
        source_state="awake", target_state="sedated",
        transition_class="anesthesia_induction", modality="eeg",
        subject_id="sub-1010", timestamp_policy="sort",
    )
    res_sorted = export(
        dataset_id="ds005620", input_path=reordered_csv, out_dir=tmp_path / "out_sorted",
        source_state="awake", target_state="sedated",
        transition_class="anesthesia_induction", modality="eeg",
        subject_id="sub-1010", timestamp_policy="sort",
    )
    assert res_sorted["record"].transition_id == res_ordered["record"].transition_id
    assert res_sorted["record"].delta_summary == res_ordered["record"].delta_summary
    assert res_sorted["record"].velocity_summary == res_ordered["record"].velocity_summary
    assert res_sorted["record"].time_axis["rows_reordered"] is True
    assert res_ordered["record"].time_axis["rows_reordered"] is False

    store_sorted = TransitionStore(tmp_path / "out_sorted")
    store_ordered = TransitionStore(tmp_path / "out_ordered")
    assert store_sorted.read_trajectory(res_sorted["record"].transition_id) == (
        store_ordered.read_trajectory(res_ordered["record"].transition_id)
    )


@pytest.mark.parametrize("policy", ["reject", "sort"])
def test_export_duplicate_timestamps_fail_closed(tmp_path, policy):
    dup_rows = [
        {"row_id": "r1", "subject_id": "sub-1010", "window_start_s": "0.0", "q_net": "0.10", "q_abs": "0.20", "mean_plv": "0.50", "condition": "awake"},
        {"row_id": "r2", "subject_id": "sub-1010", "window_start_s": "10.0", "q_net": "0.30", "q_abs": "0.25", "mean_plv": "0.60", "condition": "awake"},
        {"row_id": "r3", "subject_id": "sub-1010", "window_start_s": "10.0", "q_net": "0.80", "q_abs": "0.40", "mean_plv": "0.70", "condition": "sedated"},
    ]
    input_csv = tmp_path / "dup.csv"
    _write_csv(input_csv, dup_rows, _FIELDNAMES)
    with pytest.raises(ExportError, match="duplicate timestamps"):
        export(
            dataset_id="ds005620", input_path=input_csv, out_dir=tmp_path / "out",
            source_state="awake", target_state="sedated",
            transition_class="anesthesia_induction", modality="eeg",
            subject_id="sub-1010", timestamp_policy=policy,
        )


@pytest.mark.parametrize("bad_ts", ["", "NaN", "inf", "not_a_num"])
def test_export_missing_or_nonfinite_timestamp_fails_closed(tmp_path, bad_ts):
    bad_rows = [
        {"row_id": "r1", "subject_id": "sub-1010", "window_start_s": "0.0", "q_net": "0.10", "q_abs": "0.20", "mean_plv": "0.50", "condition": "awake"},
        {"row_id": "r2", "subject_id": "sub-1010", "window_start_s": bad_ts, "q_net": "0.30", "q_abs": "0.25", "mean_plv": "0.60", "condition": "awake"},
    ]
    input_csv = tmp_path / "bad_ts.csv"
    _write_csv(input_csv, bad_rows, _FIELDNAMES)
    with pytest.raises(ExportError, match="missing or non-finite timestamp"):
        export(
            dataset_id="ds005620", input_path=input_csv, out_dir=tmp_path / "out",
            source_state="awake", target_state="sedated",
            transition_class="anesthesia_induction", modality="eeg",
            subject_id="sub-1010",
        )


def test_export_preserves_missingness_when_no_timestamps_or_single_row(tmp_path):
    no_ts_fields = ["row_id", "subject_id", "q_net", "q_abs"]
    no_ts_rows = [
        {"row_id": "r1", "subject_id": "sub-1010", "q_net": "0.1", "q_abs": "0.2"},
        {"row_id": "r2", "subject_id": "sub-1010", "q_net": "0.5", "q_abs": "0.6"},
    ]
    csv_no_ts = tmp_path / "no_ts.csv"
    _write_csv(csv_no_ts, no_ts_rows, no_ts_fields)
    res_no_ts = export(
        dataset_id="ds005620", input_path=csv_no_ts, out_dir=tmp_path / "out_no_ts",
        source_state="awake", target_state="sedated",
        transition_class="anesthesia_induction", modality="eeg",
        subject_id="sub-1010",
    )
    assert res_no_ts["record"].duration is None
    assert res_no_ts["record"].time_axis["unit"] == "sample_index"

    single_csv = tmp_path / "single.csv"
    _write_csv(single_csv, [_ROWS[0]], _FIELDNAMES)
    res_single = export(
        dataset_id="ds005620", input_path=single_csv, out_dir=tmp_path / "out_single",
        source_state="awake", target_state="sedated",
        transition_class="anesthesia_induction", modality="eeg",
        subject_id="sub-1010",
    )
    assert res_single["record"].duration is None
    assert res_single["record"].delta_summary["status"] == "insufficient_data"
    assert res_single["record"].velocity_summary["status"] == "insufficient_data"


def test_export_distinct_episodes_interventions_and_collision_guard(tmp_path):
    csv1 = tmp_path / "ep1.csv"
    _write_csv(csv1, _ROWS, _FIELDNAMES)

    # Same window/subject/features, DIFFERENT metric values -> same ID without discriminator -> conflict!
    modified_rows = [dict(r) for r in _ROWS]
    modified_rows[2]["q_net"] = "9.99"
    csv2 = tmp_path / "ep2_modified.csv"
    _write_csv(csv2, modified_rows, _FIELDNAMES)

    out_dir = tmp_path / "store"
    r1 = export(
        dataset_id="ds005620", input_path=csv1, out_dir=out_dir,
        source_state="awake", target_state="sedated",
        transition_class="anesthesia_induction", modality="eeg",
        subject_id="sub-1010",
    )

    with pytest.raises(TransitionConflictError):
        export(
            dataset_id="ds005620", input_path=csv2, out_dir=out_dir,
            source_state="awake", target_state="sedated",
            transition_class="anesthesia_induction", modality="eeg",
            subject_id="sub-1010",
        )

    # Supplying distinct episode_id, intervention, or revision_key yields distinct non-colliding records
    r_ep2 = export(
        dataset_id="ds005620", input_path=csv2, out_dir=out_dir,
        source_state="awake", target_state="sedated",
        transition_class="anesthesia_induction", modality="eeg",
        subject_id="sub-1010", episode_id="ep-02",
    )
    r_int = export(
        dataset_id="ds005620", input_path=csv2, out_dir=out_dir,
        source_state="awake", target_state="sedated",
        transition_class="anesthesia_induction", modality="eeg",
        subject_id="sub-1010", intervention={"agent": "propofol", "dose_level": "high"},
    )
    store = TransitionStore(out_dir)
    ids = store.list_records()
    assert len({r1["record"].transition_id, r_ep2["record"].transition_id, r_int["record"].transition_id}) == 3
    assert set(ids) == {
        r1["record"].transition_id,
        r_ep2["record"].transition_id,
        r_int["record"].transition_id,
    }
