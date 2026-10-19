"""Synthetic pipeline stages executing existing interfaces on current main.

Stages:
1. SignalGenerationStage: Generates synthetic multichannel SignalChunk with explicit channels, units, and coordinates.
2. PreprocessingWindowStage: Bounded window extraction preserving channel order and sampling rate.
3. FeatureExtractionStage: Produces CanonicalFeatureBundle (PSD and Pairwise FC) preserving channel identities.
4. TopologySummaryStage: Computes persistent homology / topological summaries from pairwise connectivity.
"""
from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np

from shared.feature_contracts.models import (
    CanonicalFeatureBundle,
    CanonicalFeatureRecord,
    CoordinateStatus,
    EvidenceClass,
    FeatureFamily,
)
from shared.interop.contracts import SignalChunk


class SignalGenerationStage:
    """Stage 1: Generates synthetic multichannel raw SignalChunk."""

    STAGE_ID = "stage_1_signal_generation"
    SCHEMA_VERSION = "NeuroTopologySim.SignalChunk.v1"

    def __init__(
        self,
        channels: Sequence[str] = ("Fp1", "Fp2", "C3", "C4"),
        sfreq_hz: float = 250.0,
        duration_s: float = 2.0,
        units: str = "uV",
        montage_coordinates: Sequence[Sequence[float]] | None = None,
        seed: int = 42,
    ) -> None:
        self.channels = list(channels)
        self.sfreq_hz = float(sfreq_hz)
        self.duration_s = float(duration_s)
        self.units = units
        self.montage_coordinates = (
            [list(c) for c in montage_coordinates]
            if montage_coordinates is not None
            else [[0.0, 1.0, 0.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [1.0, 0.0, 0.0]][:len(self.channels)]
        )
        self.seed = seed

    def execute(self) -> dict[str, Any]:
        """Generate deterministic synthetic signal chunk."""
        rng = np.random.default_rng(self.seed)
        n_channels = len(self.channels)
        n_samples = int(round(self.duration_s * self.sfreq_hz))

        t = np.arange(n_samples) / self.sfreq_hz
        data = np.zeros((n_channels, n_samples), dtype=np.float64)

        for ch in range(n_channels):
            # Slow carrier (10 Hz alpha) + harmonic (20 Hz beta) + noise
            phase_offset = 0.2 * ch
            carrier = 25.0 * np.sin(2.0 * np.pi * 10.0 * t + phase_offset)
            harmonic = 10.0 * np.sin(2.0 * np.pi * 20.0 * t + phase_offset)
            noise = rng.normal(0.0, 2.0, n_samples)
            data[ch] = carrier + harmonic + noise

        # Instantiate canonical SignalChunk contract from main
        chunk = SignalChunk(
            data=data,
            timestamps=t,
            sample_rate_hz=self.sfreq_hz,
            channel_names=self.channels,
            units=self.units,
            source_id="synthetic_generator",
            recording_id="replay_session_001",
            chunk_index=0,
            start_sample=0,
            montage_name="synthetic_4ch_montage",
            montage_coordinates=np.asarray(self.montage_coordinates, dtype=float),
        )

        return {
            "artifact_id": "raw_signal_chunk_001",
            "artifact_type": "SignalChunk",
            "schema_version": self.SCHEMA_VERSION,
            "signal_chunk": chunk,
            "data": data,
            "timestamps": t,
            "sampling_rate_hz": self.sfreq_hz,
            "channel_ordering": list(self.channels),
            "observed_units": self.units,
            "observed_shape": list(data.shape),
            "sample_count": n_samples,
            "coordinate_status": "3d_montage",
            "montage_coordinates": self.montage_coordinates,
        }


class PreprocessingWindowStage:
    """Stage 2: Bounded window extraction and quality check."""

    STAGE_ID = "stage_2_preprocessing"
    SCHEMA_VERSION = "NeuroTopologySim.PreprocessedWindow.v1"

    def __init__(self, window_duration_s: float = 1.0) -> None:
        self.window_duration_s = float(window_duration_s)

    def execute(self, input_artifact: Mapping[str, Any]) -> dict[str, Any]:
        """Extract preprocessed analysis window from input SignalChunk."""
        data = np.asarray(input_artifact["data"])
        timestamps = np.asarray(input_artifact["timestamps"])
        sfreq = float(input_artifact["sampling_rate_hz"])
        channels = list(input_artifact["channel_ordering"])
        units = input_artifact["observed_units"]
        coords = input_artifact.get("montage_coordinates")

        # Take first window
        window_samples = int(round(self.window_duration_s * sfreq))
        window_data = data[:, :window_samples]
        window_timestamps = timestamps[:window_samples]

        return {
            "artifact_id": "preprocessed_window_001",
            "artifact_type": "PreprocessedWindow",
            "schema_version": self.SCHEMA_VERSION,
            "data": window_data,
            "timestamps": window_timestamps,
            "sampling_rate_hz": sfreq,
            "channel_ordering": list(channels),
            "observed_units": units,
            "observed_shape": list(window_data.shape),
            "sample_count": window_samples,
            "start_s": 0.0,
            "duration_s": self.window_duration_s,
            "coordinate_status": input_artifact.get("coordinate_status", "missing"),
            "montage_coordinates": coords,
        }


class FeatureExtractionStage:
    """Stage 3: Extracts CanonicalFeatureBundle (PSD and Pairwise FC)."""

    STAGE_ID = "stage_3_feature_extraction"
    SCHEMA_VERSION = "NeuroTopologySim.CanonicalFeatureBundle.v1"

    def execute(self, input_artifact: Mapping[str, Any]) -> dict[str, Any]:
        """Extract canonical features into versioned CanonicalFeatureBundle."""
        data = np.asarray(input_artifact["data"])
        sfreq = float(input_artifact["sampling_rate_hz"])
        channels = list(input_artifact["channel_ordering"])
        n_channels, n_samples = data.shape

        # 1. Feature: Power Spectral Density (PSD)
        # One-sided periodogram power spectral density via discrete rfft.
        # For real-valued signals, Parseval's theorem states:
        #   (1 / N) * sum_{n=0}^{N-1} x[n]^2 = sum_{k=0}^{N_bins-1} S_1[k] * delta_f
        # where delta_f = sfreq / N.
        # Two-sided raw power is |X[k]|^2 / (sfreq * N).
        # In the one-sided spectrum, DC (bin 0) and Nyquist (bin N//2 for even N)
        # do not have negative frequency conjugates and remain unscaled.
        # All interior positive-frequency bins (1 <= k < N//2 for even N,
        # 1 <= k <= (N-1)//2 for odd N) are multiplied by 2.0 to conserve total energy.
        fft_vals = np.fft.rfft(data, axis=1)
        freqs = np.fft.rfftfreq(n_samples, 1.0 / sfreq)
        psd_matrix = (np.abs(fft_vals) ** 2) / (sfreq * n_samples)
        if n_samples % 2 == 0:
            if psd_matrix.shape[1] > 2:
                psd_matrix[:, 1:-1] *= 2.0
        else:
            if psd_matrix.shape[1] > 1:
                psd_matrix[:, 1:] *= 2.0

        delta_f = float(sfreq / n_samples)
        psd_record = CanonicalFeatureRecord(
            feature_family=FeatureFamily.PSD.value,
            feature_name="psd_multichannel",
            mathematical_definition=(
                "One-sided periodogram power spectral density via rfft with interior positive-frequency "
                "bins scaled by 2 (DC and Nyquist unscaled), conserving discrete Parseval energy."
            ),
            units="uV^2/Hz",
            sampling_rate_hz=sfreq,
            channel_node_identity=list(channels),
            axes=["channels", "frequencies"],
            shape=list(psd_matrix.shape),
            values=psd_matrix.tolist(),
            frequency_axis={
                "frequencies_hz": freqs.tolist(),
                "spectral_density_convention": "one_sided",
                "scaling": "interior_bins_doubled_parseval_conserved",
                "delta_f_hz": delta_f,
            },
            time_window={"start_s": 0.0, "duration_s": input_artifact["duration_s"]},
            is_synthetic=True,
            evidence_class=EvidenceClass.SYNTHETIC_SCAFFOLDING.value,
        )

        # 2. Feature: Pairwise Functional Connectivity (PLV or correlation)
        # Phase locking value (PLV) across channels
        from scipy.signal import hilbert
        phases = np.angle(hilbert(data, axis=1))
        diff = phases[:, None, :] - phases[None, :, :]
        plv_matrix = np.abs(np.mean(np.exp(1j * diff), axis=2))
        np.fill_diagonal(plv_matrix, 0.0)
        plv_matrix = np.clip(plv_matrix, 0.0, 1.0)
        plv_matrix = (plv_matrix + plv_matrix.T) / 2.0

        fc_record = CanonicalFeatureRecord(
            feature_family=FeatureFamily.PAIRWISE_FC.value,
            feature_name="pairwise_fc_plv",
            mathematical_definition="Phase Locking Value adjacency matrix",
            units="dimensionless",
            sampling_rate_hz=sfreq,
            channel_node_identity=list(channels),
            axes=["channels", "channels"],
            shape=list(plv_matrix.shape),
            values=plv_matrix.tolist(),
            time_window={"start_s": 0.0, "duration_s": input_artifact["duration_s"]},
            is_synthetic=True,
            evidence_class=EvidenceClass.SYNTHETIC_SCAFFOLDING.value,
        )

        bundle = CanonicalFeatureBundle(
            bundle_id="feature_bundle_replay_001",
            records=[psd_record, fc_record],
            is_synthetic=True,
        )

        return {
            "artifact_id": bundle.bundle_id,
            "artifact_type": "CanonicalFeatureBundle",
            "schema_version": self.SCHEMA_VERSION,
            "feature_bundle": bundle,
            "fc_record": fc_record,
            "psd_record": psd_record,
            "pairwise_fc_matrix": plv_matrix,
            "channel_ordering": list(channels),
            "observed_units": "dimensionless",
            "observed_shape": list(plv_matrix.shape),
            "feature_family": FeatureFamily.PAIRWISE_FC.value,
            "coordinate_status": input_artifact.get("coordinate_status", "missing"),
            "montage_coordinates": input_artifact.get("montage_coordinates"),
        }


class TopologySummaryStage:
    """Stage 4: Persistent homology and topological graph summary.

    Extracts persistence intervals across dimensions 0 and 1 via Vietoris-Rips filtration.
    Raw diagram counts represent total persistence intervals across the entire filtration,
    not Betti numbers at a specific threshold. If a filtration_threshold is declared,
    evaluates actual Betti numbers beta_k(epsilon) = #{ (b, d) | b <= epsilon < d }.
    """

    STAGE_ID = "stage_4_topology_summary"
    SCHEMA_VERSION = "NeuroTopologySim.TopologicalSummary.v1"

    def __init__(self, filtration_threshold: float | None = None) -> None:
        self.filtration_threshold = filtration_threshold

    def execute(self, input_artifact: Mapping[str, Any]) -> dict[str, Any]:
        """Compute persistence-interval counts and optional thresholded Betti numbers from pairwise connectivity."""
        plv = np.asarray(input_artifact["pairwise_fc_matrix"])
        channels = list(input_artifact["channel_ordering"])
        n_channels = len(channels)

        # Distance matrix for filtration: d_ij = 1 - PLV_ij
        dist_matrix = 1.0 - plv
        np.fill_diagonal(dist_matrix, 0.0)

        # Ripser persistent homology
        from ripser import ripser
        dgm_data = ripser(dist_matrix, distance_matrix=True, maxdim=1)
        dgms = dgm_data["dgms"]
        dgm0 = dgms[0] if len(dgms) > 0 else np.empty((0, 2))
        dgm1 = dgms[1] if len(dgms) > 1 else np.empty((0, 2))

        # Total persistence intervals across the entire filtration
        h0_interval_count = len(dgm0)
        h1_interval_count = len(dgm1)

        # Evaluate Betti numbers only if an explicit filtration threshold is declared
        betti_at_threshold = None
        if self.filtration_threshold is not None:
            eps = float(self.filtration_threshold)
            # Count intervals alive at epsilon: birth <= epsilon < death
            betti_0 = int(np.sum((dgm0[:, 0] <= eps) & (eps < dgm0[:, 1]))) if len(dgm0) > 0 else 0
            betti_1 = int(np.sum((dgm1[:, 0] <= eps) & (eps < dgm1[:, 1]))) if len(dgm1) > 0 else 0
            betti_at_threshold = {
                "threshold_epsilon": eps,
                "betti_0": betti_0,
                "betti_1": betti_1,
            }

        return {
            "artifact_id": "topological_summary_001",
            "artifact_type": "TopologicalSummary",
            "schema_version": self.SCHEMA_VERSION,
            "node_count": n_channels,
            "channel_ordering": list(channels),
            # Renamed from beta interval counts to persistence-interval counts
            "persistence_interval_count_h0": h0_interval_count,
            "persistence_interval_count_h1": h1_interval_count,
            # Backward-compatibility aliases
            "beta0_interval_count": h0_interval_count,
            "beta1_interval_count": h1_interval_count,
            "filtration_threshold": self.filtration_threshold,
            "betti_numbers_at_threshold": betti_at_threshold,
            "betti_number_status": (
                "evaluated_at_declared_threshold"
                if self.filtration_threshold is not None
                else "not_evaluated_no_declared_threshold"
            ),
            "observed_shape": [n_channels],
            "observed_units": "count",
            "finite_status": True,
        }
