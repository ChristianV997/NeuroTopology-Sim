"""Deterministic synthetic fixtures for Batch-2 pipeline benchmarks.

Fixed seeds only. No remote data. Not scientific evidence.
"""
from __future__ import annotations

import hashlib
import struct
from typing import Any, Dict, List


def _u32(seed: int, salt: int) -> int:
    digest = hashlib.sha256(f"{seed}:{salt}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "little")


def make_recording(seed: int, n_samples: int, n_channels: int) -> bytes:
    """Return a deterministic packed float32 recording (little-endian)."""
    if n_samples < 1 or n_channels < 1:
        raise ValueError("n_samples and n_channels must be >= 1")
    out = bytearray()
    for i in range(n_samples * n_channels):
        # Bound to a stable float in [-1, 1]
        raw = _u32(seed, i) / 0xFFFFFFFF
        value = (raw * 2.0) - 1.0
        out.extend(struct.pack("<f", value))
    return bytes(out)


def make_fixture(seed: int, size: int) -> Dict[str, Any]:
    """Build a synthetic subject/window workload scaled by ``size``.

    ``size`` controls samples and window count. Seeds are fixed so checksums
    are reproducible across hosts.
    """
    if size < 1:
        raise ValueError("size must be >= 1")
    n_channels = 4
    n_windows = max(4, min(size, 64))
    window_samples = 32
    n_samples = n_windows * window_samples
    recording = make_recording(seed, n_samples, n_channels)
    subjects = [f"sub-{i:02d}" for i in range(1, max(2, min(size // 4, 8)) + 1)]
    windows: List[Dict[str, int]] = [
        {"index": i, "start": i * window_samples, "stop": (i + 1) * window_samples}
        for i in range(n_windows)
    ]
    return {
        "seed": seed,
        "size": size,
        "n_channels": n_channels,
        "n_samples": n_samples,
        "window_samples": window_samples,
        "n_windows": n_windows,
        "recording": recording,
        "windows": windows,
        "subjects": subjects,
        "manifest_items": [
            {"id": f"item-{i:03d}", "payload": f"{seed}:{i}:{size}".encode("utf-8")}
            for i in range(max(4, min(size, 48)))
        ],
    }
