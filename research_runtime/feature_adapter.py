"""Real EEG feature enrichment performed while a streamed subject is local."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import numpy as np


def enrich_transition_window(
    m_row: dict[str, Any],
    t_row: dict[str, Any],
    *,
    max_channels: int = 16,
    spectral_frequency_bins: int = 16,
    spectral_max_frequencies: int = 16,
) -> dict[str, Any]:
    """Return the preregistered feature panel from one real EEG window."""
    from data.bids_ingest import get_sample_rate, read_window_signal
    from dual_engine.spectral_tda import coherence_spectrum, spectral_landscape, spectral_landscape_band_summary
    from validation.analytic_phase import bandpass_hilbert_phase
    from sim.pitnn.empirical_pipeline import topology_from_phase
    from analysis.connectivity_topology import compute_plv

    source = str(m_row.get("source_file") or "")
    start = float(m_row.get("window_start_s") or 0.0)
    end = float(m_row.get("window_end_s") or 0.0)
    channels = np.asarray(read_window_signal(source, start, end, pick="all", max_channels=max_channels), dtype=float)
    sfreq = float(get_sample_rate(source))
    plv = compute_plv(channels)
    off_diagonal = plv[~np.eye(plv.shape[0], dtype=bool)]
    beta_phase = bandpass_hilbert_phase(channels, sfreq, 13.0, 30.0)
    _, _, beta_proxy = topology_from_phase(beta_phase.T)
    # Fixed low-resolution spectral settings keep the enrichment bounded while
    # retaining the preregistered beta-band landscape feature.
    coherence = coherence_spectrum(channels, sfreq, fmin=1.0, fmax=min(45.0, sfreq / 2.0 - 1.0), n_freq_bins=spectral_frequency_bins)
    landscape = spectral_landscape(coherence["coherence"], coherence["freqs"], max_freqs=spectral_max_frequencies)
    band_summary = spectral_landscape_band_summary(landscape)["band_mass"]["beta"]
    if band_summary is None:
        raise ValueError("beta spectral topology mass is unavailable for this window")
    return {
        "row_id": str(m_row["row_id"]),
        "subject_id": str(m_row["subject_id"]),
        "sequence_id": f"{m_row.get('source_file')}|{m_row.get('state_label')}",
        "condition": str(m_row.get("state_label") or ""),
        "window_start_s": start,
        "window_end_s": end,
        "q_net": float(t_row["q_net"]),
        "q_abs": float(t_row["q_abs"]),
        "f_dress": float(t_row["f_dress"]),
        "defect_density": float(t_row["defect_density"]),
        "mean_plv": float(np.mean(off_diagonal)),
        "phase_discontinuity_proxy": float(np.mean(beta_proxy)),
        "beta_spectral_topology_mass": float(band_summary),
        "topology_quality": float(t_row["topology_quality"]),
    }
