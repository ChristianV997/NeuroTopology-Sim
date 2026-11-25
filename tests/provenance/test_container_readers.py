"""Offline tests for local EEG/MEG container provenance readers."""
from __future__ import annotations

import json
import math
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from shared.provenance.readers import (
    PROVENANCE_SCHEMA,
    SCHEMA,
    ContainerReaderError,
    inspect_local_recording,
    optional_dependency_state,
    sha256_file,
)


def _edf_header(*, n_channels: int = 2, n_records: int = 2, duration: float = 1.0, samples: int = 10) -> bytes:
    header_bytes = 256 + 256 * n_channels

    def field(value: object, width: int) -> bytes:
        return f"{value:<{width}}".encode("ascii")[:width]

    chunks = [
        field("0", 8),
        field("fixture", 80),
        field("recording", 80),
        field("01.01.26", 8),
        field("00.00.00", 8),
        field(header_bytes, 8),
        field("", 44),
        field(n_records, 8),
        field(duration, 8),
        field(n_channels, 8),
    ]
    for index in range(n_channels):
        chunks.append(field(f"Ch{index}", 16))
    chunks.append(field("AgAgCl", 80) * n_channels)
    chunks.append(field("uV", 8) * n_channels)
    chunks.append(field("-100", 8) * n_channels)
    chunks.append(field("100", 8) * n_channels)
    chunks.append(field("-32768", 8) * n_channels)
    chunks.append(field("32767", 8) * n_channels)
    chunks.append(field("HP:0.1", 80) * n_channels)
    chunks.append(field(samples, 8) * n_channels)
    chunks.append(field("", 32) * n_channels)
    header = b"".join(chunks)
    header = header[:header_bytes].ljust(header_bytes, b" ")
    return header + b"\x00" * (n_records * n_channels * samples * 2)


def test_edf_header_without_loading_samples(tmp_path):
    path = tmp_path / "sub-01_ses-02_task-rest_run-01_eeg.edf"
    path.write_bytes(_edf_header())
    record = inspect_local_recording(path, origin="empirical_local")
    assert record.format == "edf"
    assert record.samples_loaded is False
    assert record.channel_count == 2
    assert record.channel_names == ["Ch0", "Ch1"]
    assert record.sampling_rate_hz == 10.0
    assert record.subject_id == "01"
    assert record.session_id == "02"
    assert record.task == "rest"
    assert record.run == "01"
    assert record.checksum_sha256 == sha256_file(path)
    declaration = record.as_provenance_declaration()
    assert declaration["schema"] == PROVENANCE_SCHEMA
    assert declaration["origin"] == "empirical_local"
    assert declaration["file_format"] == "edf"


def test_brainvision_vhdr(tmp_path):
    path = tmp_path / "demo.vhdr"
    path.write_text(
        "\n".join(
            [
                "[Common Infos]",
                "DataFile=demo.eeg",
                "MarkerFile=demo.vmrk",
                "NumberOfChannels=2",
                "SamplingInterval=2000",
                "[Channel Infos]",
                "Ch1=Fz,EEG",
                "Ch2=Cz,EEG",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "demo.eeg").write_bytes(b"x")
    record = inspect_local_recording(path, origin="synthetic_demo")
    assert record.format == "vhdr"
    assert record.sampling_rate_hz == 500.0
    assert record.channel_names == ["Fz", "Cz"]
    assert record.sidecar_present is True
    assert record.origin == "synthetic_demo"
    assert record.samples_loaded is False


def test_bids_sidecar(tmp_path):
    path = tmp_path / "sub-09_task-med_eeg.json"
    path.write_text(
        json.dumps(
            {
                "SamplingFrequency": 250,
                "EEGChannelCount": 3,
                "TaskName": "med",
                "EEGPlacementScheme": "10-20",
                "RecordingDuration": 2.0,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "sub-09_task-med_channels.tsv").write_text("name\nFz\nCz\nPz\n", encoding="utf-8")
    record = inspect_local_recording(path)
    assert record.format == "bids"
    assert record.sampling_rate_hz == 250.0
    assert record.channel_names == ["Fz", "Cz", "Pz"]
    assert record.coordinate_status == "inferred"
    assert record.sidecar_present is True


def test_fif_missing_optional_dependency(tmp_path):
    path = tmp_path / "demo.fif"
    path.write_bytes(b"not-a-real-fif")
    record = inspect_local_recording(path, find_spec=lambda name: False)
    assert record.format == "fif"
    assert record.capability == "missing_optional_dependency"
    assert record.optional_dependency == "mne"
    assert record.channel_count is None


def test_fif_mocked_mne_does_not_preload(tmp_path):
    path = tmp_path / "demo.fif"
    path.write_bytes(b"fif-bytes")
    calls = {}

    class FakeMne:
        class io:
            @staticmethod
            def read_raw_fif(source, preload=True, verbose=None):
                calls["preload"] = preload
                return SimpleNamespace(
                    info={"sfreq": 100.0, "ch_names": ["MEG1", "MEG2"], "nchan": 2, "dig": [{"kind": 1}]},
                    n_times=200,
                )

    record = inspect_local_recording(path, import_module=lambda name: FakeMne, find_spec=lambda name: True)
    assert calls["preload"] is False
    assert record.sampling_rate_hz == 100.0
    assert record.channel_count == 2
    assert record.coordinate_status == "native"
    assert record.duration_s == 2.0
    assert record.samples_loaded is False


def test_non_finite_metadata_fails(tmp_path):
    path = tmp_path / "bad_eeg.json"
    path.write_text(json.dumps({"SamplingFrequency": float("inf"), "EEGChannelCount": 1}), encoding="utf-8")
    with pytest.raises(ContainerReaderError, match="finite"):
        inspect_local_recording(path)


def test_array_format_is_rejected(tmp_path):
    path = tmp_path / "demo.npy"
    path.write_bytes(b"array")
    with pytest.raises(ContainerReaderError, match="array NPY/NPZ"):
        inspect_local_recording(path)


def test_missing_file():
    with pytest.raises(ContainerReaderError, match="missing"):
        inspect_local_recording("/tmp/nts-readers-absent.edf")


def test_no_network(tmp_path, monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "socket", blocked)
    path = tmp_path / "offline.edf"
    path.write_bytes(_edf_header())
    record = inspect_local_recording(path)
    assert record.format == "edf"
    encoded = json.dumps(record.to_dict())
    assert "NaN" not in encoded
    assert optional_dependency_state("mne")["name"] == "mne"


def test_json_nulls_and_schema(tmp_path):
    path = tmp_path / "demo.vhdr"
    path.write_text(
        "[Common Infos]\nNumberOfChannels=1\nSamplingInterval=1000\n[Channel Infos]\nCh1=Oz\n",
        encoding="utf-8",
    )
    payload = inspect_local_recording(path).to_dict()
    assert payload["schema"] == SCHEMA
    assert payload["duration_s"] is None
    assert payload["scientific_support"] == "not_claimed"
    assert payload["checksum_is_empirical_validation"] is False
    with pytest.raises(ContainerReaderError):
        inspect_local_recording(path, origin="not-a-label")
    assert math.isfinite(payload["sampling_rate_hz"])
