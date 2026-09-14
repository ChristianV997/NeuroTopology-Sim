"""Tests for memory-bounded multimodal physiology stream loader.

Scientific guardrails:
- All fixtures are explicitly synthetic demonstration data.
- Synthetic fixtures must never enter an empirical evidence path.
- Physiological coupling is a candidate mechanism, not proof of a mental-state transition.
- Do not describe respiration or parasympathetic activity as equivalent to calmness,
  detachment, equanimity, or liberation.
- No label inference: never infer awake, sedated, meditation, jhāna, task, or arousal
  states from filenames or paths.
- Strict null-safe JSON serialization.
- No network access.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import numpy as np
import pytest

from shared.data_loaders.physiology_types import (
    AlignmentMode,
    CardiacFeatures,
    PhysiologyCapabilityState,
    PhysiologyChannelType,
    PhysiologyChunk,
    PhysiologySummary,
    RespiratoryFeatures,
    verify_physiology_report_checksum,
)
from shared.data_loaders.physiology_stream import (
    PhysiologyStreamReader,
    _resample_channel_causal,
    classify_channel_type,
    compute_cardiac_features,
    compute_respiratory_features,
)


def test_causal_resampling_never_reads_a_future_sample():
    source = np.array([0.0, 10.0])
    changed_future = np.array([0.0, 100.0])
    first, metadata = _resample_channel_causal(source, 2.0, 4.0)
    second, _ = _resample_channel_causal(changed_future, 2.0, 4.0)
    np.testing.assert_array_equal(first, np.array([0.0, 0.0, 10.0, 10.0]))
    np.testing.assert_array_equal(first[:2], second[:2])
    assert metadata.method == "causal_zero_order_hold"


@pytest.fixture(scope="module")
def synthetic_multimodal_fif(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a module-scoped synthetic FIF containing EEG, ECG, and respiration."""
    mne = pytest.importorskip("mne")
    tmp_path = tmp_path_factory.mktemp("physio_fif")
    ch_names = ["Fz", "Cz", "Pz", "ECG1", "RESP_CHEST", "GSR1"]
    ch_types = ["eeg", "eeg", "eeg", "ecg", "resp", "bio"]
    sfreq = 100.0
    n_samples = 400  # 4.0 seconds at 100 Hz
    np.random.seed(42)
    t = np.arange(n_samples) / sfreq

    data = np.zeros((len(ch_names), n_samples))
    # EEG channels: 10 Hz alpha wave
    data[0] = 10e-6 * np.sin(2.0 * np.pi * 10.0 * t)
    data[1] = 12e-6 * np.sin(2.0 * np.pi * 10.0 * t + 0.5)
    data[2] = 8e-6 * np.sin(2.0 * np.pi * 10.0 * t + 1.0)

    # ECG channel: simulated R-peaks at 1.0 Hz (60 BPM)
    ecg_signal = np.zeros(n_samples)
    for r_peak in range(int(0.5 * sfreq), n_samples, int(1.0 * sfreq)):
        ecg_signal[r_peak] = 1.0e-3
        if r_peak + 1 < n_samples:
            ecg_signal[r_peak + 1] = 0.5e-3
        if r_peak - 1 >= 0:
            ecg_signal[r_peak - 1] = 0.5e-3
    data[3] = ecg_signal

    # Respiration: 0.25 Hz sine wave (15 breaths per minute)
    data[4] = 0.5 * np.sin(2.0 * np.pi * 0.25 * t)

    # GSR: slow linear drift
    data[5] = 5.0 + 0.1 * t

    info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types=ch_types)
    info["description"] = "SYNTHETIC_MULTIMODAL_DEMO"
    raw = mne.io.RawArray(data, info, verbose="ERROR")

    target = tmp_path / "synthetic_physio_raw.fif"
    raw.save(str(target), overwrite=True, verbose="ERROR")
    return target


@pytest.fixture(scope="module")
def synthetic_eeg_only_fif(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create a synthetic FIF containing only EEG channels (missing ECG & respiration)."""
    mne = pytest.importorskip("mne")
    tmp_path = tmp_path_factory.mktemp("eeg_only_fif")
    ch_names = ["Cz", "Pz"]
    sfreq = 100.0
    n_samples = 200
    data = 1e-5 * np.sin(2.0 * np.pi * 10.0 * (np.arange(n_samples) / sfreq))
    data = np.tile(data, (2, 1))

    info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
    info["description"] = "SYNTHETIC_EEG_ONLY"
    raw = mne.io.RawArray(data, info, verbose="ERROR")

    target = tmp_path / "synthetic_eeg_only_raw.fif"
    raw.save(str(target), overwrite=True, verbose="ERROR")
    return target


class TestChannelClassification:
    """Verify robust physiological modality classification."""

    def test_eeg_channel_names(self):
        assert classify_channel_type("Cz") == PhysiologyChannelType.EEG
        assert classify_channel_type("Fp1") == PhysiologyChannelType.EEG
        assert classify_channel_type("Oz") == PhysiologyChannelType.EEG

    def test_ecg_channel_names(self):
        assert classify_channel_type("ECG1") == PhysiologyChannelType.ECG
        assert classify_channel_type("EKG_LeadII") == PhysiologyChannelType.ECG
        assert classify_channel_type("HEART_RATE") == PhysiologyChannelType.ECG

    def test_respiration_channel_names(self):
        assert classify_channel_type("RESP_CHEST") == PhysiologyChannelType.RESPIRATION
        assert classify_channel_type("Thoracic_Belt") == PhysiologyChannelType.RESPIRATION
        assert classify_channel_type("Abdominal_Breathing") == PhysiologyChannelType.RESPIRATION

    def test_autonomic_channel_names(self):
        assert classify_channel_type("GSR1") == PhysiologyChannelType.GSR_EDA
        assert classify_channel_type("EDA_Conductance") == PhysiologyChannelType.GSR_EDA
        assert classify_channel_type("PPG_Finger") == PhysiologyChannelType.PPG
        assert classify_channel_type("Skin_Temp") == PhysiologyChannelType.TEMPERATURE


class TestMultiChannelStreaming:
    """Test memory-bounded multimodal streaming and chunk emission."""

    def test_iter_chunks_yields_typed_windows(self, synthetic_multimodal_fif: Path):
        reader = PhysiologyStreamReader(
            synthetic_multimodal_fif,
            alignment_mode=AlignmentMode.CAUSAL,
        )
        assert reader.capability_state == PhysiologyCapabilityState.AVAILABLE.value
        assert reader.is_synthetic is True

        chunks = list(reader.iter_chunks(chunk_duration_s=1.0, max_chunks=3))
        assert len(chunks) == 3

        first_chunk = chunks[0]
        assert isinstance(first_chunk, PhysiologyChunk)
        assert first_chunk.chunk_index == 0
        assert first_chunk.data.shape == (6, 100)  # 6 channels, 1.0s * 100 Hz
        assert first_chunk.sample_rate_hz == 100.0
        assert first_chunk.finite_status is True
        assert first_chunk.is_synthetic is True
        assert "ECG" in first_chunk.channel_types
        assert "RESPIRATION" in first_chunk.channel_types
        assert "EEG" in first_chunk.channel_types

    def test_preload_is_strictly_disabled(self, synthetic_multimodal_fif: Path):
        reader = PhysiologyStreamReader(synthetic_multimodal_fif)
        assert reader._raw is not None
        assert reader._raw.preload is False


class TestCommonClockAlignment:
    """Verify common clock resampling and causal alignment metadata."""

    def test_resampling_to_common_clock(self, synthetic_multimodal_fif: Path):
        target_fs = 50.0  # Resample from 100 Hz down to 50 Hz
        reader = PhysiologyStreamReader(
            synthetic_multimodal_fif,
            common_sfreq_hz=target_fs,
            alignment_mode=AlignmentMode.CAUSAL,
        )
        chunks = list(reader.iter_chunks(chunk_duration_s=1.0, max_chunks=2))
        assert len(chunks) == 2

        chunk = chunks[0]
        assert chunk.sample_rate_hz == 50.0
        assert chunk.data.shape == (6, 50)  # 50 samples per second
        assert chunk.clock_alignment is not None
        assert chunk.clock_alignment.alignment_mode == "CAUSAL"
        assert chunk.clock_alignment.common_clock_sfreq_hz == 50.0

        for ch_meta in chunk.clock_alignment.resampling.values():
            assert ch_meta.target_sfreq_hz == 50.0
            assert ch_meta.interpolated is True


class TestMissingPhysiologyHandling:
    """Verify graceful missingness handling when modalities are absent."""

    def test_missing_cardiac_and_respiration(self, synthetic_eeg_only_fif: Path):
        reader = PhysiologyStreamReader(synthetic_eeg_only_fif)
        summary = reader.compute_summary()

        assert summary.capability_state == PhysiologyCapabilityState.AVAILABLE.value
        assert summary.respiration is None
        assert summary.cardiac is None
        assert summary.quality is not None
        assert summary.quality.missingness_ratio > 0.5  # ECG and RESP are missing
        assert "ECG" in summary.clock_alignment.missing_channels
        assert "RESPIRATION" in summary.clock_alignment.missing_channels


class TestFeatureReadySummaries:
    """Test bounded feature extractors for respiratory and cardiac dynamics."""

    def test_respiratory_rate_and_phase(self):
        sfreq = 50.0
        t = np.arange(500) / sfreq  # 10.0 seconds (2.5 cycles)
        resp = np.sin(2.0 * np.pi * 0.25 * t)  # 0.25 Hz = 15 BPM
        feats = compute_respiratory_features(resp, sfreq)
        assert feats.respiratory_rate_bpm is not None
        assert abs(feats.respiratory_rate_bpm - 15.0) < 2.0
        assert feats.ie_ratio is not None
        assert feats.respiratory_phase_rad is not None

    def test_cardiac_rate_and_hrv(self):
        sfreq = 100.0
        n_samples = 400
        ecg = np.zeros(n_samples)
        # R-peaks every 1.0s (100 samples) = 60 BPM
        for p in range(50, n_samples, 100):
            ecg[p] = 1.0
            ecg[p - 1] = 0.4
            ecg[p + 1] = 0.4

        feats = compute_cardiac_features(ecg, sfreq)
        assert feats.heart_rate_bpm is not None
        assert abs(feats.heart_rate_bpm - 60.0) < 2.0
        assert feats.rmssd_ms is not None
        assert feats.sdnn_ms is not None


class TestErrorAndCapabilityStates:
    """Test absent files, unsupported extensions, and missing dependencies."""

    def test_unavailable_file(self, tmp_path: Path):
        missing = tmp_path / "absent_physio.fif"
        reader = PhysiologyStreamReader(missing)
        assert reader.capability_state == PhysiologyCapabilityState.UNAVAILABLE_FILE.value
        summary = reader.compute_summary()
        assert summary.capability_state == PhysiologyCapabilityState.UNAVAILABLE_FILE.value

    def test_unsupported_format(self, tmp_path: Path):
        bad_file = tmp_path / "recording.xyz"
        bad_file.write_text("dummy", encoding="utf-8")
        reader = PhysiologyStreamReader(bad_file)
        assert reader.capability_state == PhysiologyCapabilityState.UNSUPPORTED_FORMAT.value

    def test_simulated_missing_mne(self, synthetic_multimodal_fif: Path):
        from shared.data_loaders import physiology_stream as ps
        orig_find_spec = ps.importlib.util.find_spec
        try:
            ps.importlib.util.find_spec = lambda name: None if name == "mne" else orig_find_spec(name)
            reader = ps.PhysiologyStreamReader(synthetic_multimodal_fif, mne_override=None)
            assert reader.capability_state == PhysiologyCapabilityState.MISSING_OPTIONAL_DEPENDENCY.value
        finally:
            ps.importlib.util.find_spec = orig_find_spec


class TestAntiInferenceAndGuardrails:
    """Verify strict prohibition of label inference and mental-state equivalence claims."""

    def test_no_label_inference_from_deceptive_filename(self, tmp_path: Path, synthetic_multimodal_fif: Path):
        deceptive = tmp_path / "sub-01_task-meditation_awake_sedated_jhana_arousal_physio_raw.fif"
        deceptive.write_bytes(synthetic_multimodal_fif.read_bytes())

        reader = PhysiologyStreamReader(deceptive, supplied_labels=None)
        assert reader.supplied_labels == {}
        for banned in ("meditation", "awake", "sedated", "jhana", "arousal"):
            assert banned not in reader.supplied_labels

    def test_supplied_labels_preserved_verbatim(self, synthetic_multimodal_fif: Path):
        labels = {"cohort": "EXP_A", "session": "02", "subject": "S01"}
        reader = PhysiologyStreamReader(synthetic_multimodal_fif, supplied_labels=labels)
        assert reader.supplied_labels == labels


class TestSerializationAndDeterminism:
    """Verify strict null-safe JSON, deterministic repeat, and SHA-256 report verification."""

    def test_deterministic_streaming_repeat(self, synthetic_multimodal_fif: Path):
        reader1 = PhysiologyStreamReader(synthetic_multimodal_fif)
        chunks1 = list(reader1.iter_chunks(chunk_duration_s=1.0, max_chunks=2))

        reader2 = PhysiologyStreamReader(synthetic_multimodal_fif)
        chunks2 = list(reader2.iter_chunks(chunk_duration_s=1.0, max_chunks=2))

        assert len(chunks1) == len(chunks2)
        for c1, c2 in zip(chunks1, chunks2):
            np.testing.assert_array_equal(c1.data, c2.data)
            assert c1.timestamps == c2.timestamps
            assert c1.source_checksum == c2.source_checksum

    def test_json_rejects_nan_and_inf(self):
        summary = PhysiologySummary(
            source_file="dummy.fif",
            respiration=RespiratoryFeatures(
                respiratory_rate_bpm=float("nan"),  # Illegal NaN
                inspiratory_duration_s=None,
                expiratory_duration_s=None,
                ie_ratio=None,
                respiratory_phase_rad=None,
            ),
        )
        with pytest.raises(ValueError, match="Non-compliant float"):
            summary.to_json()

    def test_null_preservation_and_checksum_verification(self, synthetic_multimodal_fif: Path):
        reader = PhysiologyStreamReader(synthetic_multimodal_fif)
        summary = reader.compute_summary()
        json_str = summary.to_json()
        parsed = json.loads(json_str)

        assert verify_physiology_report_checksum(parsed) is True
        assert "schema_version" in parsed
        assert parsed["schema_version"] == "v1.0.0"


class TestCLIExecution:
    """Test CLI subprocess execution."""

    def test_cli_json_inspection(self, synthetic_multimodal_fif: Path):
        cmd = [
            sys.executable,
            "scripts/inspect_physiology_stream.py",
            str(synthetic_multimodal_fif),
            "--format",
            "json",
            "--max-chunks",
            "2",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        assert res.returncode == 0
        parsed = json.loads(res.stdout)
        assert "summary" in parsed
        assert parsed["summary"]["capability_state"] == PhysiologyCapabilityState.AVAILABLE.value
        assert len(parsed["inspected_chunks"]) == 2

    def test_cli_markdown_inspection(self, synthetic_multimodal_fif: Path):
        cmd = [
            sys.executable,
            "scripts/inspect_physiology_stream.py",
            str(synthetic_multimodal_fif),
            "--format",
            "markdown",
            "--max-chunks",
            "2",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        assert res.returncode == 0
        assert "# Multimodal Physiology Stream Inspection Report" in res.stdout
        assert "Modality Type" in res.stdout
