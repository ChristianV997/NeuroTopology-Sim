#!/usr/bin/env python3
"""Stream-process DANDI dandiset 000458 (Claar/Rembado 2023) — awake vs.
isoflurane-anesthetized head-fixed mouse EEG — one subject (NWB blob) at a time.

First DANDI/NWB dataset in this repo. Unlike legacy full-subject transfer
streamers, this reads NWB EEG windows LAZILY over HTTP via
`data/dandi_nwb_ingest.py`
(HDF5 partial reads through `remfile`), so nothing is downloaded — even the
27 GB raw-Neuropixels files are handled by reading only the ~1-2 MB of EEG
samples each window needs. Manifest-resumable like the fMRI streamers.

State labels come from each recording's own NWB epochs table
(`isoflurane_anesthesia`; awake = pre-induction baseline) — see
`sciencer_d/btc_icft/level_m/dandi000458_windows_real.py`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.streaming import base_runner  # noqa: E402
from data.dandi_nwb_ingest import (  # noqa: E402
    MAX_WINDOW_BYTES,
    DandiAsset,
    open_nwb_lazy,
    nwb_eeg_info,
    nwb_state_epochs,
    read_nwb_eeg_window,
    resolve_asset_blobs,
)

_DANDISET = "000458"
_VERSION = "0.230317.0039"


@dataclass(frozen=True)
class BoundedDandiAccess:
    """The manifest admission record for one lazy DANDI NWB object.

    DANDI's assets manifest supplies an object identity and size, but the
    compatibility listing does not supply a SHA-256 digest.  ``checksum`` is
    therefore explicitly ``unknown`` rather than fabricated.  No NWB object
    bytes are materialized: the cache budget is the maximum in-memory window
    and the release policy applies after each window's final consumer.
    """

    dataset_id: str
    version: str
    object_identity: str
    source_uri: str
    expected_size_bytes: int
    checksum_status: str
    max_window_bytes: int
    cache_budget_bytes: int
    eviction_policy: str
    network_permission: bool

    def validate(self) -> None:
        if not self.dataset_id or not self.version or not self.object_identity:
            raise ValueError("DANDI manifest identity is required")
        if not self.source_uri:
            raise ValueError("DANDI source URI is required")
        if self.expected_size_bytes <= 0:
            raise ValueError("DANDI manifest content size is required and must be positive")
        if self.checksum_status not in {"verified", "unknown"}:
            raise ValueError("checksum_status must be verified or unknown")
        if self.max_window_bytes <= 0 or self.cache_budget_bytes < self.max_window_bytes:
            raise ValueError("DANDI window and cache bounds must be positive and compatible")
        if self.eviction_policy != "release_after_final_consumer":
            raise ValueError("unsupported DANDI eviction policy")

    def to_dict(self) -> dict:
        self.validate()
        return {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "object_identity": self.object_identity,
            "source_uri": self.source_uri,
            "expected_size_bytes": self.expected_size_bytes,
            "checksum_status": self.checksum_status,
            "expected_checksum": None,
            "max_window_bytes": self.max_window_bytes,
            "cache_budget_bytes": self.cache_budget_bytes,
            "eviction_policy": self.eviction_policy,
            "network_permission": self.network_permission,
            "data_access": "lazy_bounded_windows",
            "synthetic": False,
        }


def _access_contract(asset: DandiAsset, *, allow_network: bool) -> BoundedDandiAccess:
    contract = BoundedDandiAccess(
        dataset_id=asset.dandiset_id,
        version=asset.version,
        object_identity=f"{asset.dandiset_id}/{asset.version}/{asset.path}",
        source_uri=asset.blob_url,
        expected_size_bytes=int(asset.content_size),
        checksum_status="unknown",
        max_window_bytes=MAX_WINDOW_BYTES,
        cache_budget_bytes=MAX_WINDOW_BYTES,
        eviction_policy="release_after_final_consumer",
        network_permission=allow_network,
    )
    contract.validate()
    return contract


def _contained_output(out_dir: Path, filename: str) -> Path:
    root = out_dir.resolve()
    candidate = (root / filename).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"output path escapes explicit root: {filename}")
    return candidate


def _write_manifest(out_dir: Path, contracts: list[BoundedDandiAccess], *, allow_network: bool) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "NeuroTopology.DandiBoundedAccess.v1",
        "dataset_id": _DANDISET,
        "version": _VERSION,
        "metadata_network_permission": bool(allow_network),
        "data_materialization": "lazy_bounded_windows",
        "network_accessed": bool(allow_network),
        "manifest_first": True,
        "assets": [item.to_dict() for item in contracts],
    }
    target = _contained_output(out_dir, "access_manifest.json")
    partial = target.with_name(target.name + ".part")
    partial.write_text(json.dumps(payload, allow_nan=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    partial.replace(target)
    return target


def _state_intervals(epochs: list[tuple[str, float, float]], rec_t0: float) -> list[tuple[str, float, float]]:
    anesth = next((e for e in epochs if e[0] == "isoflurane_anesthesia"), None)
    induction = next((e for e in epochs if e[0] == "isoflurane_induction"), None)
    intervals: list[tuple[str, float, float]] = []
    if induction is not None and induction[1] > rec_t0:
        intervals.append(("awake", rec_t0, induction[1]))
    if anesth is not None and anesth[2] > anesth[1]:
        intervals.append(("anesthetized", anesth[1], anesth[2]))
    return intervals


def _window_starts(start: float, end: float, window_seconds: float, maximum: int) -> list[float]:
    latest = end - window_seconds
    if latest <= start:
        return [start] if end - start >= window_seconds * 0.5 else []
    count = min(maximum, max(1, int((end - start) // window_seconds)))
    return list(np.linspace(start, latest, count))


def process_asset(
    asset: DandiAsset,
    out_dir: Path,
    window_seconds: float,
    max_windows_per_state: int,
    max_channels: int,
    *,
    allow_network: bool = False,
) -> dict:
    """Process one manifest asset through bounded lazy NWB windows.

    The older downstream helper opened the blob without receiving an explicit
    permission flag.  Keeping the implementation here makes the permission
    and bounded-window contract visible at the actual opener; no compatibility
    path can silently re-enable remote access.
    """
    contract = _access_contract(asset, allow_network=allow_network)
    if not contract.network_permission:
        raise PermissionError("DANDI signal access is disabled; pass allow_network=True explicitly")

    from sciencer_d.btc_icft.level_m.features import extract_level_m_features
    from sciencer_d.btc_icft.level_m.generic_windows import LevelMWindowRow
    from sciencer_d.btc_icft.level_t.base_real_topology import LevelTRealTopologyRow
    from sciencer_d.btc_icft.level_t.eeg_signal_topology import compute_topology_from_channels

    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(asset.path).name.replace("_behavior+ecephys.nwb", "")
    nwb = open_nwb_lazy(
        asset.blob_url,
        network_permission=contract.network_permission,
        offline=not contract.network_permission,
    )
    try:
        info = nwb_eeg_info(nwb)
        intervals = _state_intervals(nwb_state_epochs(nwb), info["t_start_s"])
        path_hash = hashlib.sha256(asset.blob_url.encode("utf-8")).hexdigest()[:8]
        m_rows = []
        t_rows = []
        for state, start, end in intervals:
            starts = _window_starts(start, end, window_seconds, max_windows_per_state)
            for index, window_start in enumerate(starts):
                window_end = window_start + window_seconds
                row_id = f"{asset.subject_id}_{state}-{index}_{path_hash}"
                warnings = [
                    "real-DANDI-NWB-EEG-derived (provenance=real_dandi_nwb); "
                    "checksum_status=unknown; bounded lazy window"
                ]
                try:
                    block = read_nwb_eeg_window(
                        nwb, window_start, window_end, pick="all", max_channels=max_channels, info=info
                    )
                except (ValueError, OSError) as exc:
                    warnings.append(f"window skipped: {exc}")
                    block = None

                if block is None or block.size == 0:
                    features = {
                        "spectral_power_proxy": None,
                        "entropy_proxy": None,
                        "lzc_proxy": None,
                        "artifact_score": None,
                    }
                    q_net = q_abs = f_dress = defect_density = 0.0
                    n_tri = n_valid = 0
                    topology_q = 0.0
                else:
                    channel_mean = block.mean(axis=0)
                    raw_power = float(np.mean(channel_mean ** 2))
                    standard_deviation = channel_mean.std()
                    normalized = ((channel_mean - channel_mean.mean()) / standard_deviation
                                  if standard_deviation > 0 else channel_mean)
                    features = extract_level_m_features([float(value) for value in normalized])
                    features["spectral_power_proxy"] = raw_power
                    channel_data = [list(map(float, channel)) for channel in block]
                    (q_net, q_abs, f_dress, defect_density, n_tri, n_valid, topology_q) = \
                        compute_topology_from_channels(channel_data)

                m_rows.append(LevelMWindowRow(
                    row_id=row_id, subject_id=asset.subject_id, session_id=None, run_id=None,
                    window_id=f"{state}-win-{index}", task_label="isoflurane_protocol", state_label=state,
                    behavior_label=None, report_label=None, y=None, source_file=asset.blob_url,
                    window_start_s=window_start, window_end_s=window_end, warnings=warnings, **features,
                ))
                t_rows.append(LevelTRealTopologyRow(
                    row_id=row_id, subject_id=asset.subject_id, session_id=None, run_id=None,
                    window_id=f"{state}-win-{index}", task_label="isoflurane_protocol",
                    q_net=q_net, q_abs=q_abs, f_dress=f_dress, defect_density=defect_density,
                    n_triangles=n_tri, n_valid_triangles=n_valid, topology_quality=topology_q,
                    null_method="real_none", null_seed=int(int(path_hash, 16) % (2**31 - 1)),
                    source_file=asset.blob_url, window_start_s=window_start, window_end_s=window_end,
                    warnings=warnings,
                ))
                # The lazy reader has no persistent data cache.  Drop the
                # window reference as soon as both consumers have completed so
                # the manifest's per-window memory bound is also an explicit
                # release/eviction boundary.
                del block
    finally:
        close = getattr(nwb, "close", None)
        if callable(close):
            close()

    base_runner.write_rows_csv(_contained_output(out_dir, f"{stem}_features_m.csv"), [asdict(r) for r in m_rows], write_empty_marker=True)
    base_runner.write_rows_csv(_contained_output(out_dir, f"{stem}_features_t.csv"), [asdict(r) for r in t_rows], write_empty_marker=True)
    states = {}
    for r in m_rows:
        states[r.state_label] = states.get(r.state_label, 0) + 1
    return {"n_m_rows": len(m_rows), "n_t_rows": len(t_rows), "states": states}


def run(out_dir: str, window_seconds: float, max_windows_per_state: int, max_channels: int,
        limit: int | None, subjects: list[str] | None, *, allow_network: bool = False) -> int:
    """Run only after explicit network permission and manifest admission.

    The default is deliberately fail-closed before DANDI metadata is queried.
    A successful run always writes the metadata-derived access manifest before
    opening a lazy NWB handle; no full object is copied to the output root.
    """
    if not allow_network:
        raise PermissionError("DANDI access is disabled; pass --allow-network explicitly")
    if window_seconds <= 0 or max_windows_per_state <= 0 or max_channels <= 0:
        raise ValueError("window and channel limits must be positive")
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive when provided")
    out_path = Path(out_dir).resolve()

    assets = resolve_asset_blobs(_DANDISET, _VERSION, network_permission=True, offline=False)
    if subjects is not None:
        assets = [a for a in assets if a.subject_id in subjects]
    assets = sorted(assets, key=lambda a: a.content_size)  # smallest first (fastest to smoke-test)
    contracts = [_access_contract(asset, allow_network=True) for asset in assets]
    _write_manifest(out_path, contracts, allow_network=True)

    base_runner.run_manifest_loop(
        assets, out_path,
        key_fn=lambda a: a.path,
        process_fn=lambda a: process_asset(
            a, out_path, window_seconds, max_windows_per_state, max_channels, allow_network=True
        ),
        limit=limit,
        label_fn=lambda a: f"{a.path} ({a.content_size/1e6:.0f} MB, lazy-read)",
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default="outputs/btc_icft/dandi000458/stream")
    p.add_argument("--window-seconds", type=float, default=10.0)
    p.add_argument("--max-windows-per-state", type=int, default=10)
    p.add_argument("--max-channels", type=int, default=16)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--subjects", nargs="*", default=None)
    p.add_argument("--allow-network", action="store_true",
                   help="Explicitly allow DANDI metadata and bounded lazy-window reads")
    a = p.parse_args()
    try:
        return run(
            a.out, a.window_seconds, a.max_windows_per_state, a.max_channels,
            a.limit, a.subjects, allow_network=a.allow_network,
        )
    except (PermissionError, ValueError) as exc:
        print(f"DATA_ACCESS_BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
