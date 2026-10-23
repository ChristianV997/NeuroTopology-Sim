"""OpenNeuro / local BIDS loader facade with fail-closed network defaults.

This module is a narrow access gate for BIDS-shaped local trees and for
*planning* bounded remote windows. It never performs full-dataset downloads,
never enables network by default, and never infers condition labels from
filenames. Structure validation is delegated to
``data.bids_ingest.index_bids_metadata``; scientific truth is not validated.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional

from data.bids_ingest import (
    BIDSAccessRequest,
    BIDSAdapterError,
    BIDSAdapterErrorCode,
    BoundedWindowRequest,
    clear_raw_cache,
    enforce_bids_access_gate,
    index_bids_metadata,
    plan_bounded_window_access,
    read_bounded_window_lazy,
    release_recording,
    serialize_bids_manifest,
)

_EEG_GLOBS = ("*.edf", "*.fif", "*.bdf", "*.set", "*.vhdr")


def find_eeg_files(root: str | Path):
    """List local EEG candidates under an explicit root. Local filesystem only."""
    root_path = Path(root).resolve()
    if not root_path.exists():
        # Privacy: do not echo absolute host paths in diagnostics.
        raise FileNotFoundError("OpenNeuro/BIDS root does not exist")
    files = []
    for ext in _EEG_GLOBS:
        for f in sorted(root_path.rglob(ext)):
            if f.is_file() and f.resolve().is_relative_to(root_path):
                files.append(f)
    return files


def find_events(root: str | Path):
    """List local ``*_events.tsv`` files under an explicit root."""
    root_path = Path(root).resolve()
    if not root_path.exists():
        raise FileNotFoundError("OpenNeuro/BIDS root does not exist")
    return [
        f
        for f in sorted(root_path.rglob("*_events.tsv"))
        if f.is_file() and f.resolve().is_relative_to(root_path)
    ]


def dataset_manifest():
    """Static catalog of known dataset *kinds*. Not a download plan."""
    return {
        "ds002094": {"kind": "tms_eeg", "pci": True},
        "ds005620": {"kind": "eeg_state"},
        "ds001787": {"kind": "eeg_state"},
        "ds003969": {"kind": "eeg_state"},
        "ds003816": {"kind": "eeg_state"},
    }


def reject_full_dataset_download(*, dataset_id: str, allow_full_dataset: bool = False) -> None:
    """Explicit full-dataset rejection seam used by callers and tests.

    Full-dataset materialization is never permitted through this loader,
    including when a caller passes ``allow_full_dataset=True``.
    """
    _ = allow_full_dataset  # accepted only to document the hard reject
    raise BIDSAdapterError(
        BIDSAdapterErrorCode.FULL_DATASET_REJECTED,
        f"full-dataset download for {dataset_id!r} is rejected; "
        "provide an explicit local path or a bounded approved remote window",
    )


def openneuro_download(*_args: Any, **_kwargs: Any) -> None:
    """Compatibility stub: OpenNeuro full downloads are permanently rejected."""
    dataset_id = str(_kwargs.get("dataset_id") or (_args[0] if _args else "unknown"))
    reject_full_dataset_download(dataset_id=dataset_id, allow_full_dataset=True)


def ensure_local_bids_index(
    dataset_id: str,
    local_root: str | Path,
    *,
    condition_manifest: Optional[Mapping[str, Any]] = None,
    require_subject: bool = False,
    require_session: bool = False,
    require_run: bool = False,
    allow_network: bool = False,
) -> dict[str, Any]:
    """Index a local BIDS tree. Network remains disabled by default."""
    if allow_network:
        # Metadata indexing is local-only in this facade.
        raise BIDSAdapterError(
            BIDSAdapterErrorCode.NETWORK_DISABLED,
            "ensure_local_bids_index is local-only; network indexing is not supported",
        )
    request = BIDSAccessRequest(
        dataset_id=dataset_id,
        local_root=str(local_root),
        allow_network=False,
        condition_manifest=condition_manifest,
        require_subject=require_subject,
        require_session=require_session,
        require_run=require_run,
    )
    return index_bids_metadata(request)


def plan_openneuro_bounded_window(
    dataset_id: str,
    *,
    relative_path: str,
    start_s: float,
    end_s: float,
    remote_uri: Optional[str] = None,
    local_root: Optional[str | Path] = None,
    allow_network: bool = False,
    expected_checksum: Optional[str] = None,
    condition_manifest: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Plan a single bounded window. Does not transfer bytes."""
    request = BIDSAccessRequest(
        dataset_id=dataset_id,
        local_root=str(local_root) if local_root is not None else None,
        remote_uri=remote_uri,
        relative_path=relative_path,
        window=BoundedWindowRequest(start_s=start_s, end_s=end_s),
        allow_network=allow_network,
        expected_checksum=expected_checksum,
        condition_manifest=condition_manifest,
    )
    return plan_bounded_window_access(request)


def read_local_bounded_window(
    dataset_id: str,
    local_root: str | Path,
    *,
    relative_path: str,
    start_s: float,
    end_s: float,
    expected_checksum: Optional[str] = None,
    pick: str = "mean",
) -> tuple[dict[str, Any], Any]:
    """Read one bounded window from an explicit local root. No network."""
    request = BIDSAccessRequest(
        dataset_id=dataset_id,
        local_root=str(local_root),
        relative_path=relative_path,
        window=BoundedWindowRequest(start_s=start_s, end_s=end_s),
        allow_network=False,
        expected_checksum=expected_checksum,
    )
    return read_bounded_window_lazy(request, pick=pick)


def access_gate_preflight(request: BIDSAccessRequest) -> dict[str, Any]:
    """Return a deterministic preflight report after enforce_bids_access_gate."""
    enforce_bids_access_gate(request)
    report = {
        "dataset_id": request.dataset_id,
        "allow_network": bool(request.allow_network),
        "has_local_root": bool(request.local_root),
        "has_remote_uri": bool(request.remote_uri),
        "has_window": request.window is not None,
        "relative_path": request.relative_path,
        "state": "PREFLIGHT_OK",
        "scientific_pass": False,
    }
    return report


__all__ = [
    "BIDSAccessRequest",
    "BIDSAdapterError",
    "BIDSAdapterErrorCode",
    "BoundedWindowRequest",
    "access_gate_preflight",
    "clear_raw_cache",
    "dataset_manifest",
    "ensure_local_bids_index",
    "find_eeg_files",
    "find_events",
    "openneuro_download",
    "plan_openneuro_bounded_window",
    "read_local_bounded_window",
    "reject_full_dataset_download",
    "release_recording",
    "serialize_bids_manifest",
]
