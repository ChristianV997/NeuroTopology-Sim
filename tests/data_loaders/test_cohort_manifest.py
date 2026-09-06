"""Unit and integration tests for local-only BIDS cohort manifest builder."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import urllib.request
import pytest

from shared.data_loaders.cohort_manifest import (
    CohortManifest,
    CohortStatus,
    FileFormat,
    build_paired_cohort_manifest,
    discover_recordings,
    inspect_file,
)
from scripts.build_paired_cohort_manifest import build_parser, main, run_build


def _create_mock_vhdr(
    folder: Path,
    filename: str,
    *,
    channels: int = 64,
    sampling_interval_us: float = 2000.0,
    with_companions: bool = True,
    with_coords: bool = False,
) -> Path:
    stem = Path(filename).stem
    vhdr_path = folder / filename
    eeg_name = f"{stem}.eeg"
    vmrk_name = f"{stem}.vmrk"

    coords_section = """
[Coordinates]
Ch1=0.1,0.2,0.3
""" if with_coords else ""

    vhdr_content = f"""Brain Vision Data Exchange Header File Version 1.0
[Common Infos]
Codepage=UTF-8
DataFile={eeg_name}
MarkerFile={vmrk_name}
DataFormat=BINARY
NumberOfChannels={channels}
SamplingInterval={sampling_interval_us}

[Channel Infos]
Ch1=Fp1,,0.1,µV
Ch2=Fp2,,0.1,µV
{coords_section}
"""
    vhdr_path.write_text(vhdr_content, encoding="utf-8")

    if with_companions:
        (folder / eeg_name).write_bytes(b"\x00" * 256)
        (folder / vmrk_name).write_text("Brain Vision Data Exchange Marker File\n", encoding="utf-8")

    return vhdr_path


def _create_mock_edf(
    folder: Path,
    filename: str,
    *,
    channels: int = 1,
    nr_samples: int = 250,
    record_duration: float = 1.0,
    is_bdf: bool = False,
) -> Path:
    edf_path = folder / filename
    magic = b"\xffBIOSEMI" if is_bdf else b"0       "
    patient = b"MOCK_PATIENT".ljust(80)
    recording = b"MOCK_RECORDING".ljust(80)
    start_date = b"01.01.26"
    start_time = b"12.00.00"
    header_bytes = f"{256 + 256 * channels:<8}".encode("ascii")
    reserved = b" ".ljust(44)
    num_records = f"{10:<8}".encode("ascii")
    duration_str = f"{record_duration:<8.1f}".encode("ascii")
    ns_str = f"{channels:<4}".encode("ascii")

    fixed = magic + patient + recording + start_date + start_time + header_bytes + reserved + num_records + duration_str + ns_str

    per_channel = (
        b"EEG Fz".ljust(16)
        + b"AgAgCl".ljust(80)
        + b"uV".ljust(8)
        + b"-500".ljust(8)
        + b"500".ljust(8)
        + b"-2048".ljust(8)
        + b"2047".ljust(8)
        + b"HP:0.1Hz LP:70Hz".ljust(80)
        + f"{nr_samples:<8}".encode("ascii")
        + b" ".ljust(32)
    )

    full_header = fixed + (per_channel * channels)
    # Write full header plus dummy data record
    data_record = b"\x00\x00" * (channels * nr_samples)
    edf_path.write_bytes(full_header + data_record)
    return edf_path


def _create_mock_fixture_npy(folder: Path, filename: str, *, shape: tuple[int, int] = (64, 500)) -> Path:
    npy_path = folder / filename
    magic = b"\x93NUMPY"
    version = b"\x01\x00"
    header_dict = f"{{'descr': '<f8', 'fortran_order': False, 'shape': {shape}, }}".encode("ascii")
    # Pad header to 64-byte alignment
    pad_len = 64 - ((10 + len(header_dict) + 1) % 64)
    header_padded = header_dict + (b" " * pad_len) + b"\n"
    header_len = len(header_padded).to_bytes(2, byteorder="little")
    npy_path.write_bytes(magic + version + header_len + header_padded)
    return npy_path


# 1. Valid paired recordings
def test_valid_paired_recordings(tmp_path: Path) -> None:
    data_dir = tmp_path / "bids_dataset"
    data_dir.mkdir()
    _create_mock_vhdr(data_dir, "sub-01_task-awake_eeg.vhdr", sampling_interval_us=2000.0, channels=64)
    _create_mock_vhdr(data_dir, "sub-01_task-sed2_eeg.vhdr", sampling_interval_us=2000.0, channels=64)
    _create_mock_vhdr(data_dir, "sub-02_task-awake_eeg.vhdr", sampling_interval_us=2000.0, channels=32)
    _create_mock_vhdr(data_dir, "sub-02_task-sed2_eeg.vhdr", sampling_interval_us=2000.0, channels=32)

    manifest = build_paired_cohort_manifest(
        input_dir=data_dir,
        condition_a="awake",
        condition_b="sed2",
        min_pairs=2,
    )

    assert manifest.status == CohortStatus.VALID_PAIRED_COHORT
    assert manifest.empirical_paired_count == 2
    assert len(manifest.paired_records) == 2
    assert len(manifest.unpaired_records) == 0
    assert len(manifest.missing_files) == 0
    assert len(manifest.invalid_files) == 0

    p1 = manifest.paired_records[0]
    assert p1.pairing_key == {"subject": "sub-01"}
    assert p1.condition_a_record.condition == "awake"
    assert p1.condition_b_record.condition == "sed2"
    assert p1.condition_a_record.sample_rate == 500.0
    assert p1.condition_a_record.channel_count == 64
    assert p1.condition_a_record.provenance.subject_source == "bids_filename"
    assert p1.condition_a_record.provenance.condition_source == "bids_task"
    assert p1.condition_a_record.provenance.sample_rate_source == "file_header"


# 2. Unpaired subjects
def test_unpaired_subjects(tmp_path: Path) -> None:
    data_dir = tmp_path / "unpaired_data"
    data_dir.mkdir()
    _create_mock_vhdr(data_dir, "sub-01_task-awake_eeg.vhdr")
    _create_mock_vhdr(data_dir, "sub-01_task-sed2_eeg.vhdr")
    # sub-02 has only awake
    _create_mock_vhdr(data_dir, "sub-02_task-awake_eeg.vhdr")
    # sub-03 has only sed2
    _create_mock_vhdr(data_dir, "sub-03_task-sed2_eeg.vhdr")

    manifest = build_paired_cohort_manifest(
        data_dir,
        condition_a="awake",
        condition_b="sed2",
        min_pairs=2,
    )

    assert manifest.status == CohortStatus.INSUFFICIENT_PAIRS
    assert manifest.empirical_paired_count == 1
    assert len(manifest.paired_records) == 1
    assert len(manifest.unpaired_records) == 2

    unpaired_subs = {u["pairing_key"]["subject"]: u for u in manifest.unpaired_records}
    assert "sub-02" in unpaired_subs
    assert unpaired_subs["sub-02"]["present_condition"] == "awake"
    assert unpaired_subs["sub-02"]["missing_condition"] == "sed2"
    assert "sub-03" in unpaired_subs
    assert unpaired_subs["sub-03"]["present_condition"] == "sed2"
    assert unpaired_subs["sub-03"]["missing_condition"] == "awake"


# 3. Duplicate runs
def test_duplicate_runs(tmp_path: Path) -> None:
    data_dir = tmp_path / "dup_runs"
    data_dir.mkdir()
    _create_mock_vhdr(data_dir, "sub-01_task-awake_run-01_eeg.vhdr")
    _create_mock_vhdr(data_dir, "sub-01_task-awake_run-02_eeg.vhdr")
    _create_mock_vhdr(data_dir, "sub-01_task-sed2_run-01_eeg.vhdr")

    manifest = build_paired_cohort_manifest(
        data_dir,
        condition_a="awake",
        condition_b="sed2",
        min_pairs=1,
    )

    assert len(manifest.duplicate_candidates) == 1
    dup = manifest.duplicate_candidates[0]
    assert dup["pairing_key"] == {"subject": "sub-01"}
    assert dup["condition"] == "awake"
    assert dup["count"] == 2


# 4. Ambiguous labels and condition preservation
def test_ambiguous_labels_and_exact_preservation(tmp_path: Path) -> None:
    data_dir = tmp_path / "ambig_data"
    data_dir.mkdir()
    # Notice: sedation is NOT automatically mapped to sed2!
    _create_mock_vhdr(data_dir, "sub-01_task-awake_eeg.vhdr")
    _create_mock_vhdr(data_dir, "sub-01_task-sedation_eeg.vhdr")

    # Without alias: exact condition "sedation" does not match "sed2"
    manifest = build_paired_cohort_manifest(
        data_dir,
        condition_a="awake",
        condition_b="sed2",
        min_pairs=1,
    )
    assert manifest.empirical_paired_count == 0
    assert manifest.status == CohortStatus.INSUFFICIENT_PAIRS
    assert len(manifest.unpaired_records) >= 1

    # With explicitly configured alias:
    manifest_aliased = build_paired_cohort_manifest(
        data_dir,
        condition_a="awake",
        condition_b="sed2",
        condition_alias={"sedation": "sed2"},
        min_pairs=1,
    )
    assert manifest_aliased.empirical_paired_count == 1
    assert manifest_aliased.status == CohortStatus.VALID_PAIRED_COHORT


# 5. Malformed filenames
def test_malformed_filenames(tmp_path: Path) -> None:
    data_dir = tmp_path / "malformed"
    data_dir.mkdir()
    _create_mock_vhdr(data_dir, "random_garbage_filename.vhdr")

    manifest = build_paired_cohort_manifest(
        data_dir,
        condition_a="awake",
        condition_b="sed2",
        min_pairs=1,
    )
    assert manifest.status == CohortStatus.MALFORMED_COHORT
    assert len(manifest.ambiguous_matches) == 1
    assert "missing_required_pairing_key_field" in manifest.ambiguous_matches[0]["reason"]


# 6. Missing metadata
def test_missing_metadata(tmp_path: Path) -> None:
    data_dir = tmp_path / "missing_meta"
    data_dir.mkdir()
    # Minimal vhdr without sample rate or channel count
    vhdr = data_dir / "sub-01_task-awake_eeg.vhdr"
    vhdr.write_text("[Common Infos]\nCodepage=UTF-8\n", encoding="utf-8")

    rec = inspect_file(vhdr, root=data_dir)
    assert rec.sample_rate is None
    assert rec.channel_count is None
    assert rec.montage_state is None
    assert rec.provenance.sample_rate_source == "null"
    assert rec.provenance.channel_count_source == "null"
    assert rec.provenance.montage_state_source == "null"

    data = rec.to_dict()
    assert data["sample_rate"] is None
    assert data["channel_count"] is None


# 7. Missing companion files
def test_missing_companion_files(tmp_path: Path) -> None:
    data_dir = tmp_path / "missing_companions"
    data_dir.mkdir()
    # Create vhdr without creating the .eeg or .vmrk
    _create_mock_vhdr(data_dir, "sub-01_task-awake_eeg.vhdr", with_companions=False)
    _create_mock_vhdr(data_dir, "sub-01_task-sed2_eeg.vhdr", with_companions=False)

    manifest = build_paired_cohort_manifest(
        data_dir,
        condition_a="awake",
        condition_b="sed2",
        min_pairs=1,
    )
    assert len(manifest.missing_files) >= 2
    missing_issues = [m["issue"] for m in manifest.missing_files]
    assert any("missing_companion_data_file" in iss for iss in missing_issues)
    assert any("missing_companion_marker_file" in iss for iss in missing_issues)


# 8. Mixed file formats
def test_mixed_file_formats(tmp_path: Path) -> None:
    data_dir = tmp_path / "mixed_cohort"
    data_dir.mkdir()
    # sub-01: BrainVision (.vhdr)
    _create_mock_vhdr(data_dir, "sub-01_task-awake_eeg.vhdr", channels=64, sampling_interval_us=2000.0)
    _create_mock_vhdr(data_dir, "sub-01_task-sed2_eeg.vhdr", channels=64, sampling_interval_us=2000.0)

    # sub-02: EDF (.edf)
    _create_mock_edf(data_dir, "sub-02_task-awake_eeg.edf", channels=1, nr_samples=250, record_duration=1.0)
    _create_mock_edf(data_dir, "sub-02_task-sed2_eeg.edf", channels=1, nr_samples=250, record_duration=1.0)

    # sub-03: BDF (.bdf)
    _create_mock_edf(data_dir, "sub-03_task-awake_eeg.bdf", channels=1, nr_samples=2048, record_duration=1.0, is_bdf=True)
    _create_mock_edf(data_dir, "sub-03_task-sed2_eeg.bdf", channels=1, nr_samples=2048, record_duration=1.0, is_bdf=True)

    manifest = build_paired_cohort_manifest(
        data_dir,
        condition_a="awake",
        condition_b="sed2",
        min_pairs=3,
    )

    assert manifest.status == CohortStatus.VALID_PAIRED_COHORT
    assert manifest.empirical_paired_count == 3
    fmts = {p.condition_a_record.format for p in manifest.paired_records}
    assert fmts == {"brainvision", "edf", "bdf"}


# 9. Deterministic checksums
def test_deterministic_checksums(tmp_path: Path) -> None:
    data_dir = tmp_path / "checksums"
    data_dir.mkdir()
    p = _create_mock_vhdr(data_dir, "sub-01_task-awake_eeg.vhdr")

    rec1 = inspect_file(p, root=data_dir)
    rec2 = inspect_file(p, root=data_dir)

    assert rec1.checksum == rec2.checksum
    assert len(rec1.checksum) == 64
    assert all(c in "0123456789abcdef" for c in rec1.checksum)


# 10. Synthetic fixture labeling
def test_synthetic_fixture_labeling(tmp_path: Path) -> None:
    data_dir = tmp_path / "synthetic_tests"
    data_dir.mkdir()
    npy_path = _create_mock_fixture_npy(data_dir, "fixture_sub-01_task-awake_eeg.npy")
    csv_path = data_dir / "synthetic_sub-01_task-sed2_eeg.csv"
    csv_path.write_text("Fp1,Fp2,F3,F4\n0.1,0.2,0.3,0.4\n", encoding="utf-8")

    manifest = build_paired_cohort_manifest(
        data_dir,
        condition_a="awake",
        condition_b="sed2",
        allow_synthetic=False,
        min_pairs=1,
    )

    assert manifest.empirical_paired_count == 0
    assert manifest.total_recordings == 2
    for r in manifest.all_recordings:
        assert r.is_synthetic is True


# 11. Minimum-pair gate
def test_minimum_pair_gate(tmp_path: Path) -> None:
    data_dir = tmp_path / "gate_data"
    data_dir.mkdir()
    _create_mock_vhdr(data_dir, "sub-01_task-awake_eeg.vhdr")
    _create_mock_vhdr(data_dir, "sub-01_task-sed2_eeg.vhdr")
    _create_mock_vhdr(data_dir, "sub-02_task-awake_eeg.vhdr")
    _create_mock_vhdr(data_dir, "sub-02_task-sed2_eeg.vhdr")

    # With min_pairs=2 -> PASS
    m2 = build_paired_cohort_manifest(data_dir, condition_a="awake", condition_b="sed2", min_pairs=2)
    assert m2.status == CohortStatus.VALID_PAIRED_COHORT

    # With min_pairs=3 -> INSUFFICIENT
    m3 = build_paired_cohort_manifest(data_dir, condition_a="awake", condition_b="sed2", min_pairs=3)
    assert m3.status == CohortStatus.INSUFFICIENT_PAIRS

    # Empty directory -> NO_DATA
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    m_empty = build_paired_cohort_manifest(empty_dir, condition_a="awake", condition_b="sed2", min_pairs=2)
    assert m_empty.status == CohortStatus.NO_DATA


# 12. No-network behavior
def test_no_network_behavior(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail_on_network(*args, **kwargs):
        raise AssertionError("Network access attempted during offline cohort discovery!")

    monkeypatch.setattr(socket, "socket", _fail_on_network)
    monkeypatch.setattr(socket, "create_connection", _fail_on_network)
    monkeypatch.setattr(urllib.request, "urlopen", _fail_on_network)

    data_dir = tmp_path / "offline_data"
    data_dir.mkdir()
    _create_mock_vhdr(data_dir, "sub-01_task-awake_eeg.vhdr")
    _create_mock_vhdr(data_dir, "sub-01_task-sed2_eeg.vhdr")

    manifest = build_paired_cohort_manifest(data_dir, condition_a="awake", condition_b="sed2", min_pairs=1)
    assert manifest.status == CohortStatus.VALID_PAIRED_COHORT


# 13. JSON finite and null compliance
def test_json_finite_null_compliance(tmp_path: Path) -> None:
    data_dir = tmp_path / "json_compliance"
    data_dir.mkdir()
    _create_mock_vhdr(data_dir, "sub-01_task-awake_eeg.vhdr")
    _create_mock_vhdr(data_dir, "sub-01_task-sed2_eeg.vhdr")

    manifest = build_paired_cohort_manifest(data_dir, condition_a="awake", condition_b="sed2", min_pairs=1)
    json_path = tmp_path / "manifest.json"
    raw_json = manifest.to_json(json_path)

    # Valid JSON parsing
    parsed = json.loads(raw_json)
    assert parsed["schema"] == "NeuroTopologySim.PairedCohortManifest.v1"
    assert parsed["status"] == "valid_paired_cohort"

    # Strict check: no NaN or Infinity strings
    assert "NaN" not in raw_json
    assert "Infinity" not in raw_json


# 14. CLI execution
def test_cli_execution(tmp_path: Path) -> None:
    data_dir = tmp_path / "cli_data"
    data_dir.mkdir()
    out_dir = tmp_path / "cli_out"

    _create_mock_vhdr(data_dir, "sub-01_task-awake_eeg.vhdr")
    _create_mock_vhdr(data_dir, "sub-01_task-sed2_eeg.vhdr")
    _create_mock_vhdr(data_dir, "sub-02_task-awake_eeg.vhdr")
    _create_mock_vhdr(data_dir, "sub-02_task-sed2_eeg.vhdr")

    cmd = [
        "--input-dir", str(data_dir),
        "--condition-a", "awake",
        "--condition-b", "sed2",
        "--output-dir", str(out_dir),
        "--min-pairs", "2",
        "--strict",
    ]
    exit_code = main(cmd)
    assert exit_code == 0

    assert (out_dir / "paired_cohort_manifest.json").is_file()
    assert (out_dir / "paired_cohort_manifest.csv").is_file()
    assert (out_dir / "paired_cohort_summary.json").is_file()

    summary = json.loads((out_dir / "paired_cohort_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "valid_paired_cohort"
    assert summary["empirical_paired_count"] == 2
    assert summary["paired_subjects"] == ["sub-01", "sub-02"]


# 15. Configurable pairing keys (session-aware)
def test_session_aware_pairing_keys(tmp_path: Path) -> None:
    data_dir = tmp_path / "session_data"
    data_dir.mkdir()
    # sub-01 has ses-01 with awake & sed2, and ses-02 with awake only
    _create_mock_vhdr(data_dir, "sub-01_ses-01_task-awake_eeg.vhdr")
    _create_mock_vhdr(data_dir, "sub-01_ses-01_task-sed2_eeg.vhdr")
    _create_mock_vhdr(data_dir, "sub-01_ses-02_task-awake_eeg.vhdr")

    manifest = build_paired_cohort_manifest(
        data_dir,
        condition_a="awake",
        condition_b="sed2",
        pairing_keys=("subject", "session"),
        min_pairs=1,
    )

    assert manifest.status == CohortStatus.VALID_PAIRED_COHORT
    assert manifest.empirical_paired_count == 1
    assert manifest.paired_records[0].pairing_key == {"subject": "sub-01", "session": "ses-01"}
    assert len(manifest.unpaired_records) == 1
    assert manifest.unpaired_records[0]["pairing_key"] == {"subject": "sub-01", "session": "ses-02"}


# 16. BIDS sidecars augmentation
def test_bids_sidecars_augmentation(tmp_path: Path) -> None:
    data_dir = tmp_path / "sidecar_data"
    data_dir.mkdir()
    vhdr = _create_mock_vhdr(data_dir, "sub-01_task-rest_eeg.vhdr")
    
    # Add sidecar json, channels.tsv, electrodes.tsv
    (data_dir / "sub-01_task-rest_eeg.json").write_text(json.dumps({
        "SamplingFrequency": 1000.0,
        "EEGChannelCount": 128,
        "TaskName": "rest",
    }), encoding="utf-8")
    (data_dir / "sub-01_task-rest_channels.tsv").write_text("name\ttype\tunits\nFp1\tEEG\tuV\nFp2\tEEG\tuV\n", encoding="utf-8")
    (data_dir / "sub-01_task-rest_electrodes.tsv").write_text("name\tx\ty\tz\nFp1\t0.1\t0.2\t0.3\n", encoding="utf-8")

    rec = inspect_file(vhdr, root=data_dir)
    assert rec.montage_state == "bids_electrodes_tsv"
    assert rec.provenance.montage_state_source == "electrodes_tsv"


# 17. CLI strict mode non-zero exit on insufficient pairs
def test_cli_strict_failure(tmp_path: Path) -> None:
    data_dir = tmp_path / "insufficient_cli"
    data_dir.mkdir()
    out_dir = tmp_path / "insufficient_out"

    # Only 1 pair when min_pairs=2
    _create_mock_vhdr(data_dir, "sub-01_task-awake_eeg.vhdr")
    _create_mock_vhdr(data_dir, "sub-01_task-sed2_eeg.vhdr")

    cmd = [
        "--input-dir", str(data_dir),
        "--condition-a", "awake",
        "--condition-b", "sed2",
        "--output-dir", str(out_dir),
        "--min-pairs", "2",
        "--strict",
    ]
    exit_code = main(cmd)
    assert exit_code == 2

    summary = json.loads((out_dir / "paired_cohort_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "insufficient_pairs"
    assert summary["empirical_paired_count"] == 1


# 18. Corrupt / invalid binary headers trigger malformed cohort
def test_corrupt_binary_header_malformed_cohort(tmp_path: Path) -> None:
    data_dir = tmp_path / "corrupt_data"
    data_dir.mkdir()
    corrupt_edf = data_dir / "sub-01_task-awake_eeg.edf"
    corrupt_edf.write_bytes(b"\x00" * 50)  # Truncated header

    manifest = build_paired_cohort_manifest(
        data_dir,
        condition_a="awake",
        condition_b="sed2",
        min_pairs=1,
    )
    assert manifest.status == CohortStatus.MALFORMED_COHORT
    assert len(manifest.invalid_files) >= 1
    assert "truncated_edf_bdf_header" in manifest.invalid_files[0]["issue"]

