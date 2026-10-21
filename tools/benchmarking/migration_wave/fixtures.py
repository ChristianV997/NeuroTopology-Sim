"""Deterministic synthetic BIDS/NWB/S3 fixtures. No remote bytes."""
from __future__ import annotations

import hashlib
from typing import Any, Dict


DATASET_ID = "ds009999"
BIDS_PATH = "sub-syn001/eeg/sub-syn001_task-rest_eeg.edf"
EXTRA_BIDS_PATH = "sub-syn001/eeg/sub-syn001_task-rest_run-02_eeg.edf"
NWB_NAME = "sub-syn001_task-rest.nwb"
S3_BUCKET = "local-synthetic-bucket"
S3_KEY = "ds009999/sub-syn001/eeg/sub-syn001_task-rest_eeg.bin"


def _payload(seed: int, size: int, tag: bytes = b"mw") -> bytes:
    size = max(16, int(size))
    body = (tag + bytes([seed & 0xFF]) + bytes((i + seed) % 251 for i in range(size)))[:size]
    return body


def make_fixture(seed: int = 0, size: int = 64) -> Dict[str, Any]:
    size = max(16, int(size))
    payload = _payload(seed, size, b"mw1")
    extra = _payload(seed + 1, size, b"mw2")
    return {
        "seed": seed,
        "size": size,
        "dataset_id": DATASET_ID,
        "bids_path": BIDS_PATH,
        "extra_bids_path": EXTRA_BIDS_PATH,
        "payload": payload,
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "extra_payload": extra,
        "extra_sha256": hashlib.sha256(extra).hexdigest(),
        "source_uri": f"file:///synthetic/{DATASET_ID}/{BIDS_PATH}",
        "extra_uri": f"file:///synthetic/{DATASET_ID}/{EXTRA_BIDS_PATH}",
        "nwb_name": NWB_NAME,
        "s3_bucket": S3_BUCKET,
        "s3_key": S3_KEY,
        "s3_uri": f"s3://{S3_BUCKET}/{S3_KEY}",
        "range_end": max(0, size // 2),
        "synthetic": True,
        "evidence_class": "performance_only",
    }
