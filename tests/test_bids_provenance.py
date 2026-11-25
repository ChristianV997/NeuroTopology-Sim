"""Dependency-light provenance contracts for BIDS inventory records."""
from __future__ import annotations

from data.bids_ingest import BIDSEEGRecord, inventory_from_records


def _record(provenance: str) -> BIDSEEGRecord:
    return BIDSEEGRecord(
        path="/tmp/sub-01/eeg/sub-01_task-rest_eeg.edf",
        relative_path="sub-01/eeg/sub-01_task-rest_eeg.edf",
        subject_id="sub-01",
        session_id=None,
        task_label="rest",
        run_id=None,
        acq_label=None,
        extension=".edf",
        is_eeg_candidate=True,
        provenance=provenance,
    )


def test_inventory_marks_local_fallback_as_unvalidated():
    payload = inventory_from_records("fixture", [_record("local_bids_unvalidated")])
    assert payload["provenance"] == "unvalidated_or_mixed"
    assert payload["eeg_candidates"][0]["provenance"] == "local_bids_unvalidated"


def test_inventory_keeps_only_validated_bids_as_real():
    payload = inventory_from_records("fixture", [_record("real_bids")])
    assert payload["provenance"] == "real_bids"
