"""Real Level-M + Level-T windows for DANDI dandiset 000458 (Claar, Rembado
et al. 2023) — awake vs. isoflurane-anesthetized head-fixed mouse EEG.

A NEW axis for this repo's anesthesia question: prior anesthesia data is human
(ds004541 EEG-fNIRS, ds005620 propofol). This is mouse 30-channel EEG under
*isoflurane* (a different anesthetic, different species, micro-to-macro scale),
letting us ask whether the awake-vs-unconscious topology contrast is specific
to human propofol or generalizes across species and anesthetic agent.

State labels come from the recording's OWN NWB `intervals/epochs` table
(`isoflurane_induction`, `isoflurane_anesthesia`) — never inferred:
  - `anesthetized` = the labeled `isoflurane_anesthesia` epoch
  - `awake`        = recording start → `isoflurane_induction` start (the
                     pre-anesthesia baseline; its end is the real, labeled
                     induction-onset boundary, not a guessed timestamp)
  - the induction transition itself is EXCLUDED (a grey zone, same discipline
    as ds004541 excluding the loc→roc transition).

A file with no `isoflurane_anesthesia` epoch, or no pre-induction span, yields
zero windows for the missing state rather than a fabricated one.

Because the NWB blobs are streamed lazily over HTTP (some are tens of GB), both
Level-M features (channel-mean) and Level-T topology (multichannel) are computed
in a SINGLE read pass per window here, rather than re-reading the remote file
twice through the local-file-path Level-T wrapper.
"""
from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from data.dandi_nwb_ingest import (  # noqa: E402
    open_nwb_lazy, nwb_eeg_info, nwb_state_epochs, read_nwb_eeg_window,
)
from sciencer_d.btc_icft.level_m.features import extract_level_m_features  # noqa: E402
from sciencer_d.btc_icft.level_m.generic_windows import LevelMWindowRow  # noqa: E402
from sciencer_d.btc_icft.level_t.base_real_topology import LevelTRealTopologyRow  # noqa: E402
from sciencer_d.btc_icft.level_t.eeg_signal_topology import compute_topology_from_channels  # noqa: E402

_ANESTH_TAG = "isoflurane_anesthesia"
_INDUCTION_TAG = "isoflurane_induction"


def _state_intervals(epochs: list[tuple[str, float, float]], rec_t0: float) -> list[tuple[str, float, float]]:
    """(state, start_s, end_s) from the real epoch tags. See module docstring."""
    anesth = next((e for e in epochs if e[0] == _ANESTH_TAG), None)
    induction = next((e for e in epochs if e[0] == _INDUCTION_TAG), None)
    out: list[tuple[str, float, float]] = []
    # awake = recording start -> induction start (real labeled boundary)
    if induction is not None and induction[1] > rec_t0:
        out.append(("awake", rec_t0, induction[1]))
    if anesth is not None and anesth[2] > anesth[1]:
        out.append(("anesthetized", anesth[1], anesth[2]))
    return out


def _even_window_starts(seg_start: float, seg_end: float, window_seconds: float, n_max: int) -> list[float]:
    latest = seg_end - window_seconds
    if latest <= seg_start:
        return [seg_start] if seg_end - seg_start >= window_seconds * 0.5 else []
    n = min(n_max, max(1, int((seg_end - seg_start) // window_seconds)))
    return list(np.linspace(seg_start, latest, n))


def build_and_extract_real_windows(
    blob_url: str,
    subject_id: str,
    window_seconds: float = 10.0,
    max_windows_per_state: int = 10,
    max_channels: int | None = 16,
) -> tuple[list[LevelMWindowRow], list[LevelTRealTopologyRow]]:
    """Stream one NWB blob, window awake/anesthetized states, compute BOTH
    Level-M features and Level-T topology per window in one read pass.

    Returns (m_rows, t_rows) with matching row_ids (so
    `analyze_cohort_stats.py` can join them). `blob_url` is a DANDI S3 blob URL;
    nothing is downloaded to disk.
    """
    nwb = open_nwb_lazy(blob_url)
    info = nwb_eeg_info(nwb)
    epochs = nwb_state_epochs(nwb)
    intervals = _state_intervals(epochs, info["t_start_s"])

    path_hash = hashlib.sha256(blob_url.encode("utf-8")).hexdigest()[:8]
    m_rows: list[LevelMWindowRow] = []
    t_rows: list[LevelTRealTopologyRow] = []

    for state, seg_start, seg_end in intervals:
        starts = _even_window_starts(seg_start, seg_end, window_seconds, max_windows_per_state)
        for idx, w_start in enumerate(starts):
            w_end = w_start + window_seconds
            row_id = f"{subject_id}_{state}-{idx}_{path_hash}"
            warns = ["real-NWB-EEG-derived (provenance=real_dandi_nwb); channel-mean Level M, multichannel Level T"]
            try:
                block = read_nwb_eeg_window(nwb, w_start, w_end, pick="all", max_channels=max_channels)
            except (ValueError, OSError) as exc:
                warns.append(f"window skipped: {exc}")
                block = None

            if block is None or block.size == 0:
                feats = {"spectral_power_proxy": None, "entropy_proxy": None, "lzc_proxy": None, "artifact_score": None}
                q_net = q_abs = f_dress = defect_density = 0.0
                n_tri = n_valid = 0
                topo_q = 0.0
            else:
                chan_mean = block.mean(axis=0)
                raw_power = float(np.mean(chan_mean ** 2))
                std = chan_mean.std()
                norm = (chan_mean - chan_mean.mean()) / std if std > 0 else chan_mean
                feats = extract_level_m_features([float(v) for v in norm])
                feats["spectral_power_proxy"] = raw_power
                channel_data = [list(map(float, ch)) for ch in block]
                (q_net, q_abs, f_dress, defect_density, n_tri, n_valid, topo_q) = \
                    compute_topology_from_channels(channel_data)

            m_rows.append(LevelMWindowRow(
                row_id=row_id, subject_id=subject_id, session_id=None, run_id=None,
                window_id=f"{state}-win-{idx}", task_label="isoflurane_protocol", state_label=state,
                behavior_label=None, report_label=None, y=None,
                source_file=blob_url, window_start_s=w_start, window_end_s=w_end,
                warnings=warns, **feats,
            ))
            t_rows.append(LevelTRealTopologyRow(
                row_id=row_id, subject_id=subject_id, session_id=None, run_id=None,
                window_id=f"{state}-win-{idx}", task_label="isoflurane_protocol",
                q_net=q_net, q_abs=q_abs, f_dress=f_dress, defect_density=defect_density,
                n_triangles=n_tri, n_valid_triangles=n_valid, topology_quality=topo_q,
                null_method="real_none", null_seed=int(int(path_hash, 16) % (2**31 - 1)),
                source_file=blob_url, window_start_s=w_start, window_end_s=w_end,
                warnings=warns,
            ))
    return m_rows, t_rows
