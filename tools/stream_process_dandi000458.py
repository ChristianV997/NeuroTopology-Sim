#!/usr/bin/env python3
"""Stream-process DANDI dandiset 000458 (Claar/Rembado 2023) — awake vs.
isoflurane-anesthetized head-fixed mouse EEG — one subject (NWB blob) at a time.

First DANDI/NWB dataset in this repo. Unlike the OpenNeuro/PhysioNet EEG
streamers (which `aws s3 sync` a whole subject dir to disk then delete it),
this reads NWB EEG windows LAZILY over HTTP via `data/dandi_nwb_ingest.py`
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
import math
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
    IngestionContractError,
    open_nwb_lazy,
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
        }


def _access_contract(asset: DandiAsset, *, allow_network: bool) -> BoundedDandiAccess:
    contract = BoundedDandiAccess(
        dataset_id=_DANDISET,
        version=_VERSION,
        object_identity=asset.path,
        source_uri=asset.blob_url,
        expected_size_bytes=asset.content_size,
        checksum_status="verified" if getattr(asset, "checksum_sha256", None) else "unknown",
        max_window_bytes=MAX_WINDOW_BYTES,
        cache_budget_bytes=MAX_WINDOW_BYTES,
        eviction_policy="release_after_final_consumer",
        network_permission=allow_network,
    )
    contract.validate()
    return contract


def _write_manifest(out_dir: Path, contracts: list[BoundedDandiAccess], *, allow_network: bool) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "access_manifest.json"
    payload = {
        "schema_version": "NeuroTopology.DandiBoundedAccessManifest.v1",
        "dataset_id": _DANDISET,
        "version": _VERSION,
        "manifest_first": True,
        "network_accessed": bool(allow_network),
        "data_materialization": "lazy_bounded_windows",
        "assets": [c.to_dict() for c in contracts],
    }
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return manifest_path


def _contained_output(out_dir: Path | str, relative_path: str) -> Path:
    base = Path(out_dir).resolve()
    target = (base / relative_path).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"DANDI output path escapes output directory: {target}") from exc
    return target


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def process_asset(
    asset,
    out_dir: Path,
    window_seconds: float,
    max_windows_per_state: int,
    max_channels: int,
    *,
    network_permission: bool = False,
    allow_network: bool | None = None,
) -> dict:
    if allow_network is not None:
        network_permission = allow_network
    if not network_permission:
        raise IngestionContractError(
            "Remote DANDI reads require explicit network permission (--allow-network / allow_network)"
        )
    import sciencer_d.btc_icft.level_m.dandi000458_windows_real as dandi_windows

    # Use subject+session-date as the CSV stem so multi-session subjects don't collide.
    stem = Path(asset.path).name.replace("_behavior+ecephys.nwb", "")
    m_rows, t_rows = dandi_windows.build_and_extract_real_windows(
        asset.blob_url,
        asset.subject_id,
        window_seconds=window_seconds,
        max_windows_per_state=max_windows_per_state,
        max_channels=max_channels,
        network_permission=network_permission,
        source_checksum_sha256=getattr(asset, "checksum_sha256", None),
    )
    output_paths = [_contained_output(out_dir, f"{stem}_features_m.csv"), _contained_output(out_dir, f"{stem}_features_t.csv")]
    base_runner.write_rows_csv(output_paths[0], [asdict(r) for r in m_rows], write_empty_marker=True)
    base_runner.write_rows_csv(output_paths[1], [asdict(r) for r in t_rows], write_empty_marker=True)
    states = {}
    for r in m_rows:
        states[r.state_label] = states.get(r.state_label, 0) + 1
    return {
        "n_m_rows": len(m_rows),
        "n_t_rows": len(t_rows),
        "states": states,
        "source_checksum_sha256": getattr(asset, "checksum_sha256", None),
        "output_paths": [path.name for path in output_paths],
        "output_sha256": {path.name: _sha256_file(path) for path in output_paths},
    }


def _contained_output_dir(out_dir: str, output_root: str | None) -> Path:
    out_path = Path(out_dir).expanduser().resolve()
    root = Path(output_root or out_path.parent).expanduser().resolve()
    try:
        out_path.relative_to(root)
    except ValueError as exc:
        raise IngestionContractError(
            f"DANDI output directory must remain inside output_root: {out_path}"
        ) from exc
    if out_path == root:
        raise IngestionContractError("DANDI output directory must be a child of output_root")
    return out_path


def run(
    out_dir: str,
    window_seconds: float,
    max_windows_per_state: int,
    max_channels: int,
    limit: int | None,
    subjects: list[str] | None,
    *,
    network_permission: bool = False,
    allow_network: bool | None = None,
    output_root: str | None = None,
) -> int:
    if allow_network is not None:
        network_permission = allow_network
    if not network_permission:
        raise IngestionContractError(
            "Remote DANDI reads require explicit network permission (--allow-network / allow_network)"
        )
    if not math.isfinite(window_seconds) or window_seconds <= 0:
        raise IngestionContractError("window_seconds must be finite and positive")
    if max_windows_per_state <= 0 or max_channels <= 0:
        raise IngestionContractError("window and channel bounds must be positive")
    if limit is not None and limit < 0:
        raise IngestionContractError("limit must be non-negative")
    out_path = _contained_output_dir(out_dir, output_root)

    assets = resolve_asset_blobs(
        _DANDISET,
        _VERSION,
        network_permission=network_permission,
        offline=not network_permission,
    )
    if subjects is not None:
        assets = [a for a in assets if a.subject_id in subjects]
    assets = sorted(assets, key=lambda a: a.content_size)  # smallest first (fastest to smoke-test)
    contracts = [_access_contract(asset, allow_network=network_permission) for asset in assets]
    _write_manifest(out_path, contracts, allow_network=network_permission)

    base_runner.run_manifest_loop(
        assets,
        out_path,
        key_fn=lambda a: a.path,
        process_fn=lambda a: process_asset(
            a,
            out_path,
            window_seconds,
            max_windows_per_state,
            max_channels,
            network_permission=network_permission,
            allow_network=network_permission,
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
    p.add_argument("--allow-network", action="store_true", help="Permit bounded DANDI metadata and lazy window reads")
    p.add_argument("--output-root", default="outputs", help="Explicit root containing --out")
    a = p.parse_args()
    try:
        return run(
            a.out,
            a.window_seconds,
            a.max_windows_per_state,
            a.max_channels,
            a.limit,
            a.subjects,
            network_permission=a.allow_network,
            output_root=a.output_root,
        )
    except (IngestionContractError, PermissionError, ValueError) as exc:
        print(f"DANDI access blocked: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
