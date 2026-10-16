"""Deterministic fixtures and perturbation helpers for synthetic pipeline replay tests."""
from __future__ import annotations

import numpy as np

from tools.synthetic_pipeline_replay.stages import SignalGenerationStage


def get_valid_signal_artifact(seed: int = 42) -> dict:
    """Generate a valid, fully conformant synthetic SignalChunk artifact."""
    stage = SignalGenerationStage(
        channels=("Fp1", "Fp2", "C3", "C4"),
        sfreq_hz=250.0,
        duration_s=2.0,
        units="uV",
        seed=seed,
    )
    return stage.execute()


def get_reordered_channel_artifact(seed: int = 42) -> dict:
    """Generate artifact with channels silently swapped (Fp2, Fp1, C3, C4)."""
    art = get_valid_signal_artifact(seed=seed)
    # Permute channels in channel_ordering list without modifying data row order
    art["channel_ordering"] = ["Fp2", "Fp1", "C3", "C4"]
    return art


def get_mismatched_unit_artifact(seed: int = 42) -> dict:
    """Generate artifact with uncalibrated unit mismatch ('V' instead of 'uV')."""
    art = get_valid_signal_artifact(seed=seed)
    art["observed_units"] = "V"
    return art


def get_missing_timing_artifact(seed: int = 42) -> dict:
    """Generate artifact missing sampling_rate_hz."""
    art = get_valid_signal_artifact(seed=seed)
    art["sampling_rate_hz"] = None
    return art


def get_changed_dimension_artifact(seed: int = 42) -> dict:
    """Generate artifact with unexpected shape dimension."""
    art = get_valid_signal_artifact(seed=seed)
    art["observed_shape"] = [3, 500]  # Expected [4, 500]
    return art


def get_non_finite_artifact(seed: int = 42) -> dict:
    """Generate artifact with NaN and Inf injected."""
    art = get_valid_signal_artifact(seed=seed)
    corrupted_data = art["data"].copy()
    corrupted_data[0, 10] = np.nan
    corrupted_data[1, 20] = np.inf
    art["data"] = corrupted_data
    return art


def get_stale_schema_artifact(seed: int = 42) -> dict:
    """Generate artifact with a stale or deprecated schema version."""
    art = get_valid_signal_artifact(seed=seed)
    art["schema_version"] = "NeuroTopologySim.SignalChunk.v0_legacy_deprecated"
    return art


def get_incompatible_stage_artifact(seed: int = 42) -> dict:
    """Generate artifact with wrong artifact type."""
    art = get_valid_signal_artifact(seed=seed)
    art["artifact_type"] = "DirectedHypergraph"
    return art


def get_contradictory_coordinates_artifact(seed: int = 42) -> dict:
    """Generate artifact where coordinate array length does not match channel count."""
    art = get_valid_signal_artifact(seed=seed)
    # 4 channels, but only 2 coordinate rows
    art["montage_coordinates"] = [[0.0, 1.0, 0.0], [0.0, 1.0, 0.0]]
    return art
