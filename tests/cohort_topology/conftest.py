"""Pytest fixtures for cohort topology runner tests."""

from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pytest

from shared.data_loaders.cohort_manifest import (
    CohortManifest,
    CohortStatus,
    PairedSubjectRecord,
    ProvenanceRecord,
    RecordingRecord,
)


@pytest.fixture
def make_mock_npy(tmp_path: Path):
    """Creates a 2D synthetic EEG array shaped (channels, samples)."""
    def _maker(
        folder: Path,
        name: str,
        channels: int = 4,
        samples: int = 2000,
        freq: float = 10.0,
        sfreq: float = 250.0,
        noise: float = 0.05,
        seed: int = 42,
    ) -> Path:
        rng = np.random.default_rng(seed)
        t = np.arange(samples) / sfreq
        data = np.zeros((channels, samples), dtype=np.float64)
        for c in range(channels):
            phase_shift = c * (np.pi / channels)
            data[c] = np.sin(2 * np.pi * freq * t + phase_shift) + noise * rng.standard_normal(samples)
        p = folder / name
        p.parent.mkdir(parents=True, exist_ok=True)
        np.save(p, data)
        return p
    return _maker


@pytest.fixture
def make_paired_manifest(tmp_path: Path, make_mock_npy):
    """Generates a populated valid PairedCohortManifest with synthetic recordings."""
    def _maker(
        n_pairs: int = 2,
        status: CohortStatus = CohortStatus.VALID_PAIRED_COHORT,
        is_synthetic: bool = True,
        ambiguous_matches: list | None = None,
    ) -> Path:
        data_dir = tmp_path / "cohort_data"
        data_dir.mkdir(parents=True, exist_ok=True)

        paired_records = []
        all_recs = []

        for i in range(1, n_pairs + 1):
            sub_id = f"sub-{i:03d}"
            fa = make_mock_npy(data_dir, f"{sub_id}_task-awake_eeg.npy", freq=10.0, seed=100 + i)
            fb = make_mock_npy(data_dir, f"{sub_id}_task-sedated_eeg.npy", freq=4.0, seed=200 + i)

            rec_a = RecordingRecord(
                file_path=str(fa),
                format="npy",
                checksum=f"mock_sha_a_{i:04d}",
                subject=sub_id,
                condition="awake",
                sample_rate=250.0,
                channel_count=4,
                is_synthetic=is_synthetic,
                provenance=ProvenanceRecord(subject_source="bids_filename", condition_source="bids_task"),
            )
            rec_b = RecordingRecord(
                file_path=str(fb),
                format="npy",
                checksum=f"mock_sha_b_{i:04d}",
                subject=sub_id,
                condition="sedated",
                sample_rate=250.0,
                channel_count=4,
                is_synthetic=is_synthetic,
                provenance=ProvenanceRecord(subject_source="bids_filename", condition_source="bids_task"),
            )

            pair = PairedSubjectRecord(
                pairing_key={"subject": sub_id},
                condition_a_record=rec_a,
                condition_b_record=rec_b,
            )
            paired_records.append(pair)
            all_recs.extend([rec_a, rec_b])

        manifest = CohortManifest(
            input_dir=str(data_dir),
            condition_a="awake",
            condition_b="sedated",
            pairing_keys=["subject"],
            min_pairs=2,
            status=status,
            status_reason=f"Status is {status.value}",
            allow_synthetic=is_synthetic,
            total_recordings=len(all_recs),
            empirical_paired_count=0 if is_synthetic else n_pairs,
            synthetic_paired_count=n_pairs if is_synthetic else 0,
            paired_records=paired_records,
            all_recordings=all_recs,
            ambiguous_matches=ambiguous_matches or [],
        )

        manifest_file = tmp_path / f"manifest_{status.value}.json"
        manifest.to_json(manifest_file)
        return manifest_file

    return _maker
