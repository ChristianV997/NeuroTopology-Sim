from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from runs.run_record import RunRecordV1
from shared.interop.contracts import (
    InteropValidationError,
    QualityReport,
    QualityStatus,
    RecordingManifest,
    SignalChunk,
    canonical_json,
    json_safe,
    normalize_relative_path,
    serialize_signal_chunk,
    sha256_file,
    sha256_text,
    stable_hash,
    stable_id,
)


def make_chunk(**overrides) -> SignalChunk:
    values = {
        "data": np.arange(12, dtype=np.float64).reshape(3, 4),
        "timestamps": np.arange(4, dtype=np.float64) / 100.0,
        "sample_rate_hz": 100.0,
        "channel_names": ["C1", "C2", "C3"],
        "units": ["uV", "uV", "uV"],
        "source_id": "fixture",
        "recording_id": "recording-1",
        "chunk_index": 0,
        "start_sample": 0,
        "source_sha256": "a" * 64,
        "montage_name": "fixture-montage",
        "montage_coordinates": np.zeros((3, 3)),
    }
    values.update(overrides)
    return SignalChunk(**values)


def test_valid_signal_chunk_preserves_channels_first_shape():
    chunk = make_chunk()
    assert chunk.shape == (3, 4)
    assert chunk.data.shape == (3, 4)
    assert chunk.channel_names == ("C1", "C2", "C3")
    assert chunk.units == ("uV", "uV", "uV")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("data", np.ones(4), "shape"),
        ("timestamps", np.ones((1, 4)), "shape"),
        ("timestamps", np.array([0.0, 0.02, 0.01, 0.03]), "strictly increasing"),
        ("data", np.array([[0.0, np.nan, 1.0, 2.0], [0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 2.0, 3.0]]), "finite"),
        ("timestamps", np.array([0.0, 0.01, np.inf, 0.03]), "finite"),
        ("sample_rate_hz", 0.0, "positive"),
        ("sample_rate_hz", np.inf, "finite"),
        ("channel_names", ["C1", "C1", "C3"], "unique"),
        ("montage_coordinates", np.zeros((3, 2)), "shape"),
        ("montage_coordinates", np.full((3, 3), np.nan), "finite"),
    ],
)
def test_signal_chunk_rejects_invalid_values(field, value, message):
    with pytest.raises(InteropValidationError, match=message):
        make_chunk(**{field: value})


def test_duplicate_channels_can_only_be_enabled_explicitly():
    with pytest.raises(InteropValidationError, match="unique"):
        make_chunk(channel_names=["C1", "C1", "C3"])
    chunk = make_chunk(channel_names=["C1", "C1", "C3"], allow_duplicate_channels=True)
    assert chunk.channel_names[0] == chunk.channel_names[1]


def test_no_silent_transpose_for_mismatched_timestamps():
    with pytest.raises(InteropValidationError, match="does not match"):
        make_chunk(data=np.ones((4, 3)), timestamps=np.arange(4, dtype=float))


def test_manifest_normalizes_relative_paths_and_checks_dimensions():
    manifest = RecordingManifest(
        dataset_id="ds-fixture",
        recording_id="sub-01",
        source_path=Path("raw\\sub-01\\eeg.edf"),
        source_sha256="b" * 64,
        file_format="edf",
        channel_count=2,
        sample_rate_hz=250,
        duration_s=2,
        channel_names=["C1", "C2"],
        units="uV",
        provenance_status="verified",
    )
    assert manifest.source_path == "raw/sub-01/eeg.edf"
    assert manifest.units == ("uV", "uV")

    with pytest.raises(InteropValidationError, match="relative"):
        RecordingManifest(
            dataset_id="ds",
            recording_id="r",
            source_path="C:/raw/eeg.edf",
            source_sha256=None,
            file_format="edf",
            channel_count=1,
            sample_rate_hz=250,
            duration_s=None,
            channel_names=["C1"],
            units="uV",
        )
    with pytest.raises(InteropValidationError, match="traversal"):
        normalize_relative_path("raw/../eeg.edf")


def test_signal_chunk_rejects_incomplete_or_bad_provenance_metadata():
    with pytest.raises(InteropValidationError, match="SHA-256"):
        make_chunk(source_sha256="not-a-hash")
    with pytest.raises(InteropValidationError, match="at least one"):
        make_chunk(data=np.empty((3, 0)), timestamps=np.empty(0))


def test_canonical_serialization_is_stable_and_arrays_are_referenced_separately():
    chunk = make_chunk()
    reference = {"path": "arrays/chunk-000.npy", "sha256": "c" * 64}
    first = serialize_signal_chunk(chunk, array_reference=reference)
    second = serialize_signal_chunk(make_chunk(), array_reference=reference)
    assert first == second
    payload = json.loads(first)
    assert "data" not in payload
    assert payload["array_reference"] == reference
    assert payload["shape"] == [3, 4]

    assert canonical_json({"b": np.int64(2), "a": np.float64(1.5)}) == '{"a":1.5,"b":2}'
    with pytest.raises(TypeError, match="binary"):
        json_safe(np.zeros((2, 2)))


def test_stable_hashes_and_file_hashes(tmp_path):
    value = {"b": 2, "a": [1, 2]}
    assert stable_hash(value) == stable_hash({"a": [1, 2], "b": 2})
    assert stable_hash(value) != stable_hash({"a": [1, 3], "b": 2})
    assert stable_id(value, prefix="chunk-") == "chunk-" + stable_hash(value)[:16]
    path = tmp_path / "payload.bin"
    path.write_bytes(b"interop")
    assert sha256_file(path) == sha256_text("interop")


def test_quality_report_statuses_are_explicit_and_k_guardrail_is_not_weakened():
    assert QualityReport(status="inconclusive").status is QualityStatus.INCONCLUSIVE
    with pytest.raises(InteropValidationError, match="K > 100"):
        QualityReport(status="PASS", metrics={"K": 100.0})
    report = QualityReport(
        status="PASS",
        metrics={"K": 100.1},
        artifact_paths=["outputs/report.json"],
    )
    assert report.status is QualityStatus.PASS


def test_run_record_v1_maps_without_replacing_the_canonical_record():
    record = RunRecordV1.make(
        "run-interop",
        "hypothesis",
        verdict="INCONCLUSIVE",
        dataset_id="ds-fixture",
        metrics={"observations": 1},
        artifacts={"report": "outputs/report.json"},
        source="test",
    )
    report = QualityReport.from_run_record(record)
    assert isinstance(record, RunRecordV1)
    assert report.status is QualityStatus.INCONCLUSIVE
    assert report.provenance["schema_version"] == record.schema_version
    assert report.artifact_paths == ("outputs/report.json",)
