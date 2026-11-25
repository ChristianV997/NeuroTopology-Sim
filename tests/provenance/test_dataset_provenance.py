"""Offline tests for the dataset provenance contract."""
from __future__ import annotations

import json
import math
import socket
from pathlib import Path

import numpy as np
import pytest

from shared.provenance.contract import (
    ATTACHMENT_KEY,
    SCHEMA,
    ProvenanceError,
    attach_provenance,
    consumer_view,
    serialize_record,
    sha256_file,
    validate_declaration,
    write_sidecar,
)

_UNITS = {"time": "s", "sampling_frequency": "Hz", "amplitude": "V"}


def _write_array(path: Path, data: np.ndarray) -> Path:
    np.save(path, data)
    return path


def _base(**overrides):
    declaration = {
        "dataset_identifier": "local-fixture-001",
        "condition_label": "rest",
        "subject_id": "sub-01",
        "session_id": "ses-01",
        "local_path": None,
        "file_checksum_sha256": None,
        "file_format": "npy",
        "channel_count": 4,
        "sample_count": 16,
        "sampling_rate_hz": 250.0,
        "units": dict(_UNITS),
        "montage_source": "10-20-subset",
        "montage_channels": ["Fz", "Cz", "Pz", "Oz"],
        "acquisition_metadata": {"device": "fixture"},
        "preprocessing_steps": ["none"],
        "filtering_bands_hz": {"low_hz": 0.5, "high_hz": 40.0},
        "tda_configuration": {"engine": "none", "maxdim": 1},
        "source_url": "https://example.invalid/ds000000",
        "license": "CC0",
        "access_metadata": {"offline_only": True},
        "origin": "empirical_local",
        "acquisition_timestamp": "2026-01-01T00:00:00Z",
    }
    declaration.update(overrides)
    return declaration


def _complete_empirical(path: Path, data: np.ndarray | None = None) -> dict:
    array = data if data is not None else np.arange(64, dtype=np.float64).reshape(16, 4)
    _write_array(path, array)
    return _base(
        local_path=str(path),
        file_checksum_sha256=sha256_file(path),
        channel_count=int(array.shape[1]),
        sample_count=int(array.shape[0]),
    )


def test_synthetic_fixture(tmp_path):
    path = tmp_path / "synth.npy"
    declaration = _complete_empirical(path)
    declaration["origin"] = "synthetic_demo"
    record = validate_declaration(declaration)
    assert record.validation_status == "PASS_SYNTHETIC"
    assert record.evidence_claim_allowed is False
    assert record.data_finite is True


def test_empirical_local_fixture(tmp_path):
    path = tmp_path / "emp.npy"
    record = validate_declaration(_complete_empirical(path))
    assert record.validation_status == "PASS_EMPIRICAL_LOCAL"
    assert record.evidence_claim_allowed is True
    assert record.schema == SCHEMA
    view = consumer_view(record)
    assert view["evidence_claim_allowed"] is True
    assert view["sampling_rate_hz"] == 250.0


def test_missing_file(tmp_path):
    declaration = _base(local_path=str(tmp_path / "absent.npy"), file_checksum_sha256="abc")
    record = validate_declaration(declaration)
    assert record.validation_status == "FAIL"
    assert record.evidence_claim_allowed is False
    assert any("missing" in item for item in record.warnings)


def test_corrupted_file(tmp_path):
    path = tmp_path / "corrupt.npy"
    path.write_bytes(b"not-a-numpy-file")
    declaration = _base(local_path=str(path), file_checksum_sha256=sha256_file(path))
    record = validate_declaration(declaration)
    assert record.validation_status == "FAIL"
    assert record.evidence_claim_allowed is False


def test_invalid_sample_rate(tmp_path):
    path = tmp_path / "rate.npy"
    declaration = _complete_empirical(path)
    declaration["sampling_rate_hz"] = 0
    record = validate_declaration(declaration)
    assert record.validation_status == "FAIL"
    declaration["sampling_rate_hz"] = float("inf")
    record = validate_declaration(declaration)
    assert record.validation_status == "FAIL"


def test_non_finite_data(tmp_path):
    path = tmp_path / "nan.npy"
    data = np.ones((16, 4), dtype=np.float64)
    data[3, 1] = np.nan
    declaration = _complete_empirical(path, data)
    record = validate_declaration(declaration)
    assert record.validation_status == "FAIL"
    assert record.data_finite is False
    assert record.evidence_claim_allowed is False


def test_checksum_mismatch(tmp_path):
    path = tmp_path / "sum.npy"
    declaration = _complete_empirical(path)
    declaration["file_checksum_sha256"] = "0" * 64
    record = validate_declaration(declaration)
    assert record.validation_status == "FAIL"
    assert record.checksum_ok is False


def test_incomplete_montage(tmp_path):
    path = tmp_path / "montage.npy"
    declaration = _complete_empirical(path)
    declaration["montage_source"] = ""
    declaration["montage_channels"] = []
    record = validate_declaration(declaration)
    assert record.validation_status == "INCOMPLETE"
    assert record.evidence_claim_allowed is False
    assert "montage_source" in record.missing_fields


def test_deterministic_repeat(tmp_path):
    path = tmp_path / "repeat.npy"
    declaration = _complete_empirical(path)
    first = serialize_record(validate_declaration(declaration))
    second = serialize_record(validate_declaration(declaration))
    assert first == second
    loaded = json.loads(first)
    assert loaded["schema"] == SCHEMA


def test_no_network_execution(tmp_path, monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "socket", blocked)
    path = tmp_path / "offline.npy"
    record = validate_declaration(_complete_empirical(path))
    assert record.validation_status == "PASS_EMPIRICAL_LOCAL"
    assert any("source_url is metadata only" in item for item in record.warnings)


def test_schema_round_trip(tmp_path):
    path = tmp_path / "round.npy"
    record = validate_declaration(_complete_empirical(path))
    encoded = serialize_record(record)
    loaded = json.loads(encoded)
    assert loaded["schema"] == SCHEMA
    sidecar_path = write_sidecar(record, tmp_path / "run")
    assert sidecar_path.name == "dataset_provenance.json"
    sidecar = attach_provenance({"run_id_ref": "abc"}, record)
    assert sidecar[ATTACHMENT_KEY]["schema"] == SCHEMA
    with pytest.raises(ProvenanceError):
        attach_provenance({"schema_version": "0.1", "run_kind": "hypothesis"}, record)
    with pytest.raises(ProvenanceError):
        serialize_record({"bad": math.nan})
