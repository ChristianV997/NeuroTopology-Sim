"""Tests for provenance-aware recording-quality gate.

Scientific guardrails:
- All fixtures are explicitly marked as synthetic demonstrations.
- Synthetic fixtures must never enter an empirical evidence path.
- Header validation is not independent empirical validation.
- No network access.
- No clinical or consciousness claims.
- No label inference.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import numpy as np
import pytest

from shared.provenance.recording_quality import (
    CompanionFileInfo,
    InspectionLimits,
    MontageCoverage,
    ProvenanceInfo,
    QualityIssue,
    RecordingMetadata,
    RecordingQualityReport,
    RecordingQualityState,
    compute_file_sha256,
    inspect_recording_quality,
    verify_report_checksum,
)


@pytest.fixture(scope="module")
def shared_synthetic_fif(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a module-scoped synthetic .fif file marked as demonstration fixture."""
    mne = pytest.importorskip("mne")
    tmp_path = tmp_path_factory.mktemp("shared_fif")
    ch_names = ["Fp1", "Fp2", "Fz", "Cz", "Pz", "Oz"]
    sfreq = 100.0
    n_samples = 150  # 1.5 seconds, fast to write and inspect
    np.random.seed(42)
    data = 1e-5 * np.sin(2.0 * np.pi * 10.0 * (np.arange(n_samples) / sfreq))
    data = np.tile(data, (len(ch_names), 1))

    info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
    info["description"] = "SYNTHETIC_DEMO_FIXTURE"
    raw = mne.io.RawArray(data, info, verbose="ERROR")
    annot = mne.Annotations(onset=[0.2], duration=[0.2], description=["SYNTHETIC_TEST"])
    raw.set_annotations(annot)

    target = tmp_path / "synthetic_fixture_raw.fif"
    raw.save(str(target), overwrite=True, verbose="ERROR")
    return target


@pytest.fixture
def synthetic_brainvision_triplet(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create a valid synthetic BrainVision (.vhdr, .vmrk, .eeg) file triplet."""
    vhdr = tmp_path / "synthetic_bv.vhdr"
    vmrk = tmp_path / "synthetic_bv.vmrk"
    eeg = tmp_path / "synthetic_bv.eeg"

    n_channels = 4
    n_samples = 100
    np.random.seed(123)
    raw_data = (np.random.randn(n_samples, n_channels) * 50).astype(np.int16)
    with eeg.open("wb") as f:
        f.write(raw_data.tobytes())

    vmrk_content = """Brain Vision Data Exchange Marker File, Version 1.0
[Common Infos]
Codepage=UTF-8
DataFile=synthetic_bv.eeg

[Marker Infos]
Mk1=Stimulus,S  1,50,1,0
"""
    vmrk.write_text(vmrk_content, encoding="utf-8")

    vhdr_content = f"""Brain Vision Data Exchange Header File Version 1.0
; Synthetic Demonstration Fixture
[Common Infos]
Codepage=UTF-8
DataFile=synthetic_bv.eeg
MarkerFile=synthetic_bv.vmrk
DataFormat=BINARY
DataOrientation=MULTIPLEXED
NumberOfChannels={n_channels}
SamplingInterval=10000

[Binary Infos]
BinaryFormat=INT_16

[Channel Infos]
Ch1=Fp1,,0.1,µV
Ch2=Fp2,,0.1,µV
Ch3=Cz,,0.1,µV
Ch4=Pz,,0.1,µV
"""
    vhdr.write_text(vhdr_content, encoding="utf-8")

    return vhdr, vmrk, eeg


class TestQualityStateDefinitions:
    """Verify state catalog and strict taxonomy."""

    def test_all_expected_states_exist(self):
        expected_states = {
            "VALIDATED_EMPIRICAL_LOCAL",
            "VALIDATED_SYNTHETIC_ONLY",
            "INCOMPLETE_METADATA",
            "INVALID_RECORDING",
            "MISSING_OPTIONAL_DEPENDENCY",
            "UNSUPPORTED_FORMAT",
            "UNAVAILABLE_FILE",
        }
        actual_states = {s.value for s in RecordingQualityState}
        assert actual_states == expected_states


class TestContainerInspection:
    """Test file availability, format validation, and bounded inspection."""

    def test_unavailable_file(self, tmp_path: Path):
        missing = tmp_path / "non_existent_recording.fif"
        report = inspect_recording_quality(missing)
        assert report.quality_state == RecordingQualityState.UNAVAILABLE_FILE.value
        assert report.passed_validation is False
        assert any(QualityIssue.FILE_NOT_FOUND.value in i for i in report.issues)

    def test_unsupported_format(self, tmp_path: Path):
        bad_file = tmp_path / "recording.mat"
        bad_file.write_text("dummy", encoding="utf-8")
        report = inspect_recording_quality(bad_file)
        assert report.quality_state == RecordingQualityState.UNSUPPORTED_FORMAT.value
        assert report.passed_validation is False
        assert any(QualityIssue.UNSUPPORTED_EXTENSION.value in i for i in report.issues)

    def test_synthetic_fif_validation(self, shared_synthetic_fif: Path):
        report = inspect_recording_quality(shared_synthetic_fif, bounded_samples=50)
        assert report.passed_validation is True
        assert report.is_synthetic is True
        assert report.quality_state == RecordingQualityState.VALIDATED_SYNTHETIC_ONLY.value
        assert report.metadata is not None
        assert report.metadata.channel_count == 6
        assert report.metadata.sampling_rate_hz == 100.0
        assert report.inspection_limits is not None
        assert report.inspection_limits.inspected_samples == 50
        assert report.inspection_limits.preload is False

    def test_synthetic_fixture_cannot_masquerade_as_empirical(self, shared_synthetic_fif: Path):
        """Even if an operator hints 'empirical', synthetic markers force synthetic state."""
        report = inspect_recording_quality(shared_synthetic_fif, provenance_hint="empirical")
        assert report.passed_validation is True
        assert report.is_synthetic is True
        assert report.quality_state == RecordingQualityState.VALIDATED_SYNTHETIC_ONLY.value
        assert any("synthetic" in w.lower() for w in report.warnings)

    def test_clean_file_empirical_hint(self, tmp_path: Path):
        """A clean file with no synthetic markers under empirical hint validates as empirical."""
        mne = pytest.importorskip("mne")
        ch_names = ["C3", "C4"]
        sfreq = 100.0
        data = np.ones((2, 50)) * 1e-6
        info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
        raw = mne.io.RawArray(data, info, verbose="ERROR")
        clean_path = tmp_path / "recording_001_raw.fif"
        raw.save(str(clean_path), overwrite=True, verbose="ERROR")

        report = inspect_recording_quality(clean_path, provenance_hint="empirical")
        assert report.passed_validation is True
        assert report.is_synthetic is False
        assert report.quality_state == RecordingQualityState.VALIDATED_EMPIRICAL_LOCAL.value

    def test_brainvision_complete_triplet(self, synthetic_brainvision_triplet: tuple[Path, Path, Path]):
        vhdr, vmrk, eeg = synthetic_brainvision_triplet
        report = inspect_recording_quality(vhdr, bounded_samples=50)
        assert report.passed_validation is True
        assert report.is_synthetic is True
        assert report.quality_state == RecordingQualityState.VALIDATED_SYNTHETIC_ONLY.value
        assert report.metadata is not None
        assert report.metadata.channel_count == 4
        assert len(report.metadata.companion_files) == 2
        assert all(c.exists for c in report.metadata.companion_files)

    def test_brainvision_missing_eeg_companion(self, synthetic_brainvision_triplet: tuple[Path, Path, Path]):
        vhdr, vmrk, eeg = synthetic_brainvision_triplet
        eeg.unlink()
        report = inspect_recording_quality(vhdr)
        assert report.passed_validation is False
        assert report.quality_state == RecordingQualityState.INVALID_RECORDING.value
        assert any(QualityIssue.MISSING_COMPANION_FILE.value in i for i in report.issues)

    def test_brainvision_missing_vmrk_companion(self, synthetic_brainvision_triplet: tuple[Path, Path, Path]):
        vhdr, vmrk, eeg = synthetic_brainvision_triplet
        vmrk.unlink()
        report = inspect_recording_quality(vhdr)
        assert report.passed_validation is False
        assert report.quality_state == RecordingQualityState.INVALID_RECORDING.value
        assert any(QualityIssue.MISSING_COMPANION_FILE.value in i for i in report.issues)

    def test_non_finite_sample_chunk_detected(self, tmp_path: Path):
        mne = pytest.importorskip("mne")
        ch_names = ["Fz", "Cz"]
        sfreq = 100.0
        data = np.ones((2, 50)) * 1e-6
        data[0, 5] = np.nan
        info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
        raw = mne.io.RawArray(data, info, verbose="ERROR")
        nan_fif = tmp_path / "nan_recording_raw.fif"
        raw.save(str(nan_fif), overwrite=True, verbose="ERROR")

        report = inspect_recording_quality(nan_fif, bounded_samples=20)
        assert report.passed_validation is False
        assert report.quality_state == RecordingQualityState.INVALID_RECORDING.value
        assert any(QualityIssue.NON_FINITE_SAMPLE_VALUES.value in i for i in report.issues)

    def test_duplicate_channels_detected(self, tmp_path: Path):
        class MockRaw:
            ch_names = ["Cz", "Pz", "Cz"]
            info = {"sfreq": 100.0, "bads": []}
            n_times = 50
            def get_data(self, start=0, stop=10):
                return np.zeros((3, stop - start))
            def get_montage(self):
                return None

        from shared.provenance.recording_quality import _validate_opened_raw
        mock_rep = _validate_opened_raw(
            raw=MockRaw(),
            path=tmp_path / "dummy.fif",
            source_format="FIF",
            file_sha256="0000",
            bounded_samples=10,
            provenance_hint="auto",
            supplied_labels={},
            timestamp_utc="2026-09-07T00:00:00Z",
            companion_infos=[],
        )
        assert mock_rep.passed_validation is False
        assert mock_rep.quality_state == RecordingQualityState.INVALID_RECORDING.value
        assert any(QualityIssue.DUPLICATE_CHANNEL_NAMES.value in i for i in mock_rep.issues)

    def test_bids_container_structure(self, tmp_path: Path, shared_synthetic_fif: Path):
        bids_root = tmp_path / "bids_test_container"
        bids_root.mkdir()
        desc = bids_root / "dataset_description.json"
        desc.write_text(
            json.dumps({"Name": "Synthetic BIDS Container", "BIDSVersion": "1.8.0", "DatasetType": "raw"}),
            encoding="utf-8",
        )
        sub_eeg_dir = bids_root / "sub-01" / "eeg"
        sub_eeg_dir.mkdir(parents=True)
        fif_target = sub_eeg_dir / "sub-01_task-rest_eeg.fif"
        fif_target.write_bytes(shared_synthetic_fif.read_bytes())

        report = inspect_recording_quality(bids_root, bounded_samples=20)
        assert report.passed_validation is True
        assert report.is_synthetic is True
        assert report.quality_state == RecordingQualityState.VALIDATED_SYNTHETIC_ONLY.value

    def test_bids_missing_description_fails(self, tmp_path: Path):
        empty_bids = tmp_path / "empty_bids"
        empty_bids.mkdir()
        report = inspect_recording_quality(empty_bids)
        assert report.passed_validation is False
        assert report.quality_state == RecordingQualityState.INCOMPLETE_METADATA.value


class TestDependencyAndCapabilityHandling:
    """Ensure missing optional dependencies yield capability states, not failures or false passes."""

    def test_missing_mne_yields_capability_state(self, shared_synthetic_fif: Path):
        from shared.provenance import recording_quality as rq
        orig_spec = rq.importlib.util.find_spec
        try:
            rq.importlib.util.find_spec = lambda name: None if name == "mne" else orig_spec(name)
            rep = rq.inspect_recording_quality(shared_synthetic_fif, mne_override=None)
            assert rep.quality_state == RecordingQualityState.MISSING_OPTIONAL_DEPENDENCY.value
            assert rep.passed_validation is False
            assert "mne" in rep.missing_dependencies
        finally:
            rq.importlib.util.find_spec = orig_spec


class TestAntiInferenceAndGuardrails:
    """Verify strict prohibition on label inference from file paths."""

    def test_no_label_inference_from_filename(self, tmp_path: Path):
        # Plain text header with deceptive filename
        deceptive_vhdr = tmp_path / "sub-01_task-meditation_run-01_sedated_awake_eeg.vhdr"
        deceptive_vhdr.write_text(
            """Brain Vision Data Exchange Header File Version 1.0
[Common Infos]
DataFile=data.eeg
MarkerFile=data.vmrk
NumberOfChannels=1
SamplingInterval=10000
[Channel Infos]
Ch1=Cz,,0.1,µV
""",
            encoding="utf-8",
        )
        report = inspect_recording_quality(deceptive_vhdr, supplied_labels=None)
        assert report.provenance is not None
        assert report.provenance.supplied_labels == {}
        assert "meditation" not in report.provenance.supplied_labels
        assert "sedated" not in report.provenance.supplied_labels
        assert "awake" not in report.provenance.supplied_labels

    def test_supplied_labels_preserved_verbatim(self, tmp_path: Path):
        test_file = tmp_path / "explicit_labels.vhdr"
        test_file.write_text(
            """Brain Vision Data Exchange Header File Version 1.0
[Common Infos]
DataFile=data.eeg
MarkerFile=data.vmrk
NumberOfChannels=1
SamplingInterval=10000
[Channel Infos]
Ch1=Cz,,0.1,µV
""",
            encoding="utf-8",
        )
        labels = {"cohort_id": "CONTROL_A", "session": "01", "operator_note": "verified"}
        report = inspect_recording_quality(test_file, supplied_labels=labels)
        assert report.provenance is not None
        assert report.provenance.supplied_labels == labels


class TestSerializationAndChecksums:
    """Verify strict JSON serialization and checksum determinism."""

    def test_json_serialization_rejects_nan_and_inf(self):
        report = RecordingQualityReport(
            target_path="dummy.fif",
            quality_state=RecordingQualityState.VALIDATED_EMPIRICAL_LOCAL.value,
            passed_validation=True,
            metadata=RecordingMetadata(
                source_format="FIF",
                sampling_rate_hz=float("nan"),
                channel_count=1,
                channel_names=["Cz"],
                duration_s=None,
                bad_channels=[],
                montage=None,
            ),
        )
        with pytest.raises(ValueError, match="Non-compliant float"):
            report.to_json()

    def test_json_serialization_preserves_null_for_none(self):
        report = RecordingQualityReport(
            target_path="dummy.fif",
            quality_state=RecordingQualityState.VALIDATED_EMPIRICAL_LOCAL.value,
            passed_validation=True,
            metadata=RecordingMetadata(
                source_format="FIF",
                sampling_rate_hz=250.0,
                channel_count=1,
                channel_names=["Cz"],
                duration_s=None,
                bad_channels=[],
                montage=None,
            ),
        )
        json_str = report.to_json()
        parsed = json.loads(json_str)
        assert parsed["metadata"]["duration_s"] is None
        assert "duration_s\": null" in json_str

    def test_deterministic_checksum_verification(self, shared_synthetic_fif: Path):
        report = inspect_recording_quality(shared_synthetic_fif)
        json_str = report.to_json()
        data = json.loads(json_str)
        assert verify_report_checksum(data) is True

        tampered = dict(data)
        tampered["target_path"] = "tampered_path.fif"
        assert verify_report_checksum(tampered) is False


class TestCLIExecution:
    """Test CLI script execution in isolated subprocess."""

    def test_cli_json_output(self, shared_synthetic_fif: Path):
        cmd = [
            sys.executable,
            "scripts/validate_recording_quality.py",
            str(shared_synthetic_fif),
            "--format",
            "json",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        assert res.returncode == 0
        parsed = json.loads(res.stdout)
        assert parsed["quality_state"] == RecordingQualityState.VALIDATED_SYNTHETIC_ONLY.value
        assert parsed["passed_validation"] is True

    def test_cli_markdown_output(self, shared_synthetic_fif: Path):
        cmd = [
            sys.executable,
            "scripts/validate_recording_quality.py",
            str(shared_synthetic_fif),
            "--format",
            "markdown",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        assert res.returncode == 0
        assert "# Recording Quality Gate Evaluation Report" in res.stdout
        assert "VALIDATED_SYNTHETIC_ONLY" in res.stdout

    def test_cli_strict_empirical_flag_fails_on_synthetic(self, shared_synthetic_fif: Path):
        cmd = [
            sys.executable,
            "scripts/validate_recording_quality.py",
            str(shared_synthetic_fif),
            "--strict-empirical",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode != 0
