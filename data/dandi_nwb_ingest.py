"""Real DANDI/NWB EEG ingestion for the topology pipeline — a NEW data source
alongside OpenNeuro BIDS (`data/bids_ingest.py`) and PhysioNet.

DANDI stores Neurodata-Without-Borders (NWB, an HDF5 dialect) files, NOT BIDS,
so `mne-bids` cannot read them. This module provides the two responsibilities
`bids_ingest.py` provides for BIDS, but for NWB streamed lazily over HTTP from
DANDI's public S3 (no download of multi-GB raw files — only the EEG windows we
actually need are read, via HDF5 partial reads through `remfile`):

1. `resolve_asset_blobs(dandiset_id, version)` — list a dandiset's NWB assets
   (logical path + real content-addressed S3 blob URL) from the public
   `dandiarchive` bucket, unsigned/anonymous (same access model as OpenNeuro).

2. `open_nwb_lazy(blob_url)` / `read_nwb_eeg_window(...)` — open an NWB file
   lazily and return REAL samples for one time window of its EEG
   `ElectricalSeries` as a (n_channels, n_samples) array, plus
   `nwb_state_epochs(...)` to read the recording's own labeled state epochs
   (e.g. isoflurane_anesthesia) from the NWB `intervals/epochs` table.

Provenance is explicit: every window is real signal streamed from the
published DANDI blob. Nothing is fabricated; a window that can't be read
raises, matching `read_window_signal`'s contract.

Dependencies (both permissive-licensed, declared in requirements.txt):
`pynwb`/`hdmf` (BSD-3-Clause), `h5py` (BSD-3-Clause), `remfile` (Apache-2.0).
Only `h5py` + `remfile` are needed for the streaming read path here; `pynwb`
is listed for callers wanting the full NWB object model.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

_DANDI_BUCKET = "dandiarchive"


@dataclass(frozen=True)
class DandiAsset:
    dandiset_id: str
    version: str
    path: str  # logical BIDS-like path, e.g. sub-521885/sub-521885_ses-..._behavior+ecephys.nwb
    subject_id: str
    blob_url: str  # direct S3 blob URL (content-addressed)
    content_size: int


def _s3_client():
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    return boto3.client("s3", config=Config(signature_version=UNSIGNED, max_pool_connections=32))


def resolve_asset_blobs(dandiset_id: str, version: str) -> list[DandiAsset]:
    """List a published dandiset's NWB assets with real content-addressed blob URLs.

    Reads the dandiset's `assets.yaml` manifest from the public bucket. The
    logical `path` in the manifest is NOT the physical S3 key (DANDI
    content-addresses blobs under `blobs/`), so we take the S3 blob URL from
    each asset's `contentUrl` list.
    """
    import yaml

    s3 = _s3_client()
    key = f"dandisets/{dandiset_id}/{version}/assets.yaml"
    assets = yaml.safe_load(s3.get_object(Bucket=_DANDI_BUCKET, Key=key)["Body"].read())

    out: list[DandiAsset] = []
    for a in assets:
        path = a.get("path", "")
        if not path.endswith(".nwb"):
            continue
        blob = next((u for u in a.get("contentUrl", []) if "s3.amazonaws.com/blobs" in u), None)
        if blob is None:
            continue
        subject = path.split("/")[0] if "/" in path else path
        out.append(
            DandiAsset(
                dandiset_id=dandiset_id, version=version, path=path,
                subject_id=subject, blob_url=blob,
                content_size=int(a.get("contentSize", 0)),
            )
        )
    return out


def open_nwb_lazy(blob_url: str):
    """Open an NWB (HDF5) file lazily over HTTP — no full download. Returns an
    open `h5py.File`. Only the byte ranges actually accessed are fetched."""
    import h5py
    import remfile

    return h5py.File(remfile.File(blob_url), "r")


def _eeg_series(nwb, eeg_series_name: str = "ElectricalSeriesEEG"):
    acq = nwb["acquisition"]
    if eeg_series_name not in acq:
        raise ValueError(f"no {eeg_series_name!r} in acquisition (have {list(acq.keys())})")
    return acq[eeg_series_name]


def nwb_eeg_info(nwb, eeg_series_name: str = "ElectricalSeriesEEG") -> dict:
    """(n_samples, n_channels, sampling_rate_hz, t_start_s, t_end_s) for the EEG series."""
    es = _eeg_series(nwb, eeg_series_name)
    data = es["data"]
    n_samples, n_channels = int(data.shape[0]), int(data.shape[1])
    if "timestamps" in es:
        ts = es["timestamps"]
        t0 = float(ts[0])
        t1 = float(ts[-1])
        # robust rate from the first samples (uniform within a session)
        head = ts[: min(500, n_samples)]
        rate = 1.0 / float(np.mean(np.diff(head)))
    else:
        st = es["starting_time"]
        rate = float(st.attrs.get("rate"))
        t0 = float(st[()]) if st.shape == () else float(st[0])
        t1 = t0 + n_samples / rate
    return {
        "n_samples": n_samples, "n_channels": n_channels,
        "rate_hz": rate, "t_start_s": t0, "t_end_s": t1,
    }


def nwb_state_epochs(nwb) -> list[tuple[str, float, float]]:
    """Read the NWB `intervals/epochs` table as (tag, start_s, stop_s) tuples.

    Uses the recording's OWN labeled epochs — never inferred. For dandiset
    000458 these are `isoflurane_induction` / `isoflurane_anesthesia`; the
    awake baseline is defined by the caller as the pre-induction span, from a
    real labeled boundary (induction start), not fabricated."""
    if "intervals" not in nwb or "epochs" not in nwb["intervals"]:
        return []
    ep = nwb["intervals"]["epochs"]
    starts = ep["start_time"][:]
    stops = ep["stop_time"][:]
    tags_flat = ep["tags"][:]
    tags_index = ep["tags_index"][:]
    # tags is a ragged VLEN column indexed by tags_index (NWB DynamicTable convention):
    # row i's tags are tags_flat[tags_index[i-1]:tags_index[i]].
    out: list[tuple[str, float, float]] = []
    prev = 0
    for i in range(len(starts)):
        end_idx = int(tags_index[i])
        row_tags = tags_flat[prev:end_idx]
        prev = end_idx
        tag = ""
        if len(row_tags):
            t0 = row_tags[0]
            tag = t0.decode() if isinstance(t0, bytes) else str(t0)
        out.append((tag, float(starts[i]), float(stops[i])))
    return out


def read_nwb_eeg_window(
    nwb,
    window_start_s: float,
    window_end_s: float,
    pick: str = "all",
    max_channels: Optional[int] = None,
    eeg_series_name: str = "ElectricalSeriesEEG",
    info: Optional[dict] = None,
) -> np.ndarray:
    """Return REAL EEG samples for one time window as a (n_channels, n_samples)
    array (pick="all") or a 1-D channel-mean (pick="mean").

    Mirrors `data.bids_ingest.read_window_signal`'s contract: raises ValueError
    if the window is out of range. Only the requested sample rows are read from
    the remote HDF5 dataset (partial read), so this is cheap even on 27 GB files.

    `info` is the dict from `nwb_eeg_info`; pass it to avoid re-reading the
    timestamps header on every window (a real cost over HTTP — one recording is
    windowed dozens of times). Computed once if omitted.
    """
    es = _eeg_series(nwb, eeg_series_name)
    if info is None:
        info = nwb_eeg_info(nwb, eeg_series_name)
    rate = info["rate_hz"]
    t0 = info["t_start_s"]
    n_total = info["n_samples"]

    start = int(round((window_start_s - t0) * rate))
    stop = int(round((window_end_s - t0) * rate))
    if start < 0 or stop > n_total or stop <= start:
        raise ValueError(
            f"window [{window_start_s},{window_end_s}]s out of range "
            f"(recording {t0:.1f}-{info['t_end_s']:.1f}s, {n_total} samples)"
        )

    n_channels = info["n_channels"]
    ch_stop = n_channels if max_channels is None else min(n_channels, max_channels)
    block = es["data"][start:stop, :ch_stop]  # (n_samples, n_channels) partial read
    block = np.asarray(block, dtype=float).T   # -> (n_channels, n_samples)

    if pick == "mean":
        return block.mean(axis=0)
    return block
