"""Tests for memory-bounded MNE streaming adapter.

Scientific guardrails:
- All fixtures are explicitly synthetic.
- No network access or external downloads.
- No clinical or consciousness claims.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import pytest
import numpy as np

from sciencer_d.btc_icft.io import eeg_mne_adapter as adapter


@pytest.fixture
def synthetic_fif_file(tmp_path: Path) -> Path:
    """Create a temporary synthetic .fif file with standard 10-20 channels."""
    mne = pytest.importorskip("mne")
    ch_names = ["Fp1", "Fp2", "Fz", "Cz", "Pz", "Oz"]
    sfreq = 200.0
    n_samples = 1000  # 5.0 seconds
    np.random.seed(42)
    # Synthetic test fixture signal: sine waves + gaussian noise
    t = np.arange(n_samples) / sfreq
    data = np.zeros((len(ch_names), n_samples))
    for i in range(len(ch_names)):
        data[i] = 10e-6 * np.sin(2.0 * np.pi * (i + 1) * 5.0 * t) + 1e-6 * np.random.randn(n_samples)

    info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types="eeg")
    raw = mne.io.RawArray(data, info, verbose="ERROR")
    # Add synthetic annotation
    annot = mne.Annotations(onset=[1.0], duration=[0.5], description=["SYNTHETIC_STIM"])
    raw.set_annotations(annot)

    fif_path = tmp_path / "synthetic_sample_raw.fif"
    raw.save(str(fif_path), overwrite=True, verbose="ERROR")
    return fif_path


class TestFormatDispatch:
    """Test format recognition and reader dispatch configuration."""

    @pytest.mark.parametrize(
        "ext",
        [".edf", ".bdf", ".gdf", ".set", ".fdt", ".vhdr", ".vmrk", ".eeg", ".cnt", ".fif", ".fif.gz"],
    )
    def test_supported_extensions(self, ext: str):
        det = adapter.detect_mne_supported_file(f"recording{ext}")
        assert det["supported"] is True
        assert det["extension"] == ext

    def test_unsupported_extension(self):
        det = adapter.detect_mne_supported_file("recording.mat")
        assert det["supported"] is False
        assert det["extension"] == ".mat"

    def test_fif_gz_compound_extension(self):
        det = adapter.detect_mne_supported_file("/path/to/subject_eeg.fif.gz")
        assert det["supported"] is True
        assert det["extension"] == ".fif.gz"


class TestChecksumAndProvenance:
    """Test file SHA-256 provenance calculation."""

    def test_compute_file_sha256(self, tmp_path: Path):
        f = tmp_path / "sample.dat"
        content = b"NeuroTopology-Sim synthetic EEG test payload"
        f.write_bytes(content)
        expected = hashlib.sha256(content).hexdigest()
        assert adapter.compute_file_sha256(f) == expected

    def test_compute_file_sha256_missing_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            adapter.compute_file_sha256(tmp_path / "nonexistent.dat")


class TestMNEStreamingChunks:
    """Test memory-bounded streaming via iter_mne_signal_chunks."""

    def test_streaming_chunk_shapes_and_timestamps(self, synthetic_fif_file: Path):
        chunks = list(
            adapter.iter_mne_signal_chunks(
                synthetic_fif_file,
                chunk_seconds=2.0,
                return_dict=False,
            )
        )
        # 5.0 seconds at 2.0s per chunk yields 3 chunks: [0-2s, 2-4s, 4-5s]
        assert len(chunks) == 3

        # Chunk 0
        c0 = chunks[0]
        assert c0.chunk_index == 0
        assert c0.chunk_start_s == 0.0
        assert c0.chunk_end_s == 2.0
        assert c0.sample_start == 0
        assert c0.sample_end == 400
        assert c0.data.shape == (6, 400)
        assert c0.sfreq == 200.0
        assert c0.n_channels == 6
        assert c0.n_samples == 400
        assert c0.channel_names == ["Fp1", "Fp2", "Fz", "Cz", "Pz", "Oz"]
        assert all(c0.units[ch] == "V" for ch in c0.channel_names)
        assert len(c0.source_sha256) == 64

        # Chunk 2 (remainder chunk)
        c2 = chunks[2]
        assert c2.chunk_index == 2
        assert c2.chunk_start_s == 4.0
        assert c2.chunk_end_s == 5.0
        assert c2.sample_start == 800
        assert c2.sample_end == 1000
        assert c2.data.shape == (6, 200)

    def test_streaming_return_dict(self, synthetic_fif_file: Path):
        chunks = list(
            adapter.iter_mne_signal_chunks(
                synthetic_fif_file,
                chunk_seconds=2.5,
                return_dict=True,
            )
        )
        assert len(chunks) == 2
        assert isinstance(chunks[0], dict)
        assert "data" in chunks[0]
        assert isinstance(chunks[0]["data"], list)
        assert len(chunks[0]["data"]) == 6
        assert len(chunks[0]["data"][0]) == 500

    def test_picks_filtering(self, synthetic_fif_file: Path):
        picked = ["Fz", "Cz"]
        chunks = list(
            adapter.iter_mne_signal_chunks(
                synthetic_fif_file,
                chunk_seconds=2.0,
                picks=picked,
            )
        )
        for c in chunks:
            assert c.n_channels == 2
            assert c.channel_names == picked
            assert c.data.shape[0] == 2

    def test_window_range_slicing(self, synthetic_fif_file: Path):
        chunks = list(
            adapter.iter_mne_signal_chunks(
                synthetic_fif_file,
                chunk_seconds=1.0,
                start_s=1.0,
                stop_s=3.0,
            )
        )
        assert len(chunks) == 2
        assert chunks[0].chunk_start_s == 1.0
        assert chunks[0].chunk_end_s == 2.0
        assert chunks[1].chunk_start_s == 2.0
        assert chunks[1].chunk_end_s == 3.0

    def test_annotations_passed_in_chunk(self, synthetic_fif_file: Path):
        chunks = list(
            adapter.iter_mne_signal_chunks(
                synthetic_fif_file,
                chunk_seconds=2.0,
            )
        )
        # Annotation is at onset=1.0s, duration=0.5s -> should fall into chunk 0 (0-2s)
        assert len(chunks[0].annotations) == 1
        assert chunks[0].annotations[0]["description"] == "SYNTHETIC_STIM"
        # Chunk 1 (2-4s) should have no annotations
        assert len(chunks[1].annotations) == 0

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            list(adapter.iter_mne_signal_chunks(tmp_path / "missing.fif"))

    def test_unsupported_format_raises(self, tmp_path: Path):
        f = tmp_path / "dummy.rawxyz"
        f.write_text("dummy")
        with pytest.raises(ValueError, match="Unsupported file format"):
            list(adapter.iter_mne_signal_chunks(f))

    def test_missing_mne_graceful_failure(self, monkeypatch, synthetic_fif_file: Path):
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: None if name == "mne" else object())
        with pytest.raises(ImportError, match="mne package is required"):
            list(adapter.iter_mne_signal_chunks(synthetic_fif_file))

    def test_banned_phrases_guard(self):
        for phrase in adapter.BANNED_PHRASES:
            with pytest.raises(ValueError, match="Banned phrase detected"):
                adapter._validate_safe_text(f"This result {phrase}")
