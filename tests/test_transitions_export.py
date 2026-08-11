"""Tests for transitions.export_from_results — the CLI/library exporter."""
from __future__ import annotations

import csv
import json

import pytest

from transitions.export_from_results import ExportError, export
from transitions.record import TransitionValidationError
from transitions.store import TransitionStore


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
