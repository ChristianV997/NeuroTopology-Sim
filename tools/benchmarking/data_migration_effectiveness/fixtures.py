"""Local synthetic fixtures for bounded-access vs rejected full-object measurements.

Never contacts OpenNeuro, AWS, DANDI, or other remote services.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict


def _checksum(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def make_fixture(seed: int, size: int) -> Dict[str, Any]:
    """Deterministic local bytes + BIDS-like paths. Size is chunk bytes, not subjects."""
    n = max(int(size), 16)
    payload = bytes((seed + i) % 256 for i in range(n))
    dataset_id = "ds000000"
    bids_path = "sub-01/eeg/sub-01_task-rest_eeg.edf"
    source_uri = f"mock://local/{dataset_id}/{bids_path}"
    extra_uri = f"mock://local/{dataset_id}/sub-02/eeg/sub-02_task-rest_eeg.edf"
    extra = bytes((seed + 17 + i) % 256 for i in range(n))
    return {
        "seed": seed,
        "size": n,
        "dataset_id": dataset_id,
        "bids_path": bids_path,
        "source_uri": source_uri,
        "payload": payload,
        "payload_sha256": _checksum(payload),
        "extra_bids_path": "sub-02/eeg/sub-02_task-rest_eeg.edf",
        "extra_uri": extra_uri,
        "extra_payload": extra,
        "extra_sha256": _checksum(extra),
        "chunk_index": 0,
        "manifest_payload": {
            "processed_subjects": {"sub-01": {"status": "COMPLETE", "checksum": _checksum(payload)}},
            "failed_subjects": {},
        },
        "stream_n_samples": min(512, max(64, n)),
        "stream_n_channels": 4,
        "stream_chunk": 32,
    }


def fixture_root(tmp: Path) -> Path:
    root = tmp / "migration_bench"
    root.mkdir(parents=True, exist_ok=True)
    return root
