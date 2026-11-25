"""Synthetic in-memory fixtures for the MNE signal-block boundary.

No network, no filesystem EEG recordings, no MNE import required.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def make_valid_block_payload(
    *,
    n_channels: int = 2,
    n_samples: int = 8,
    sample_rate_hz: float = 100.0,
) -> dict[str, Any]:
    """Return a fully declared block suitable for CONVERTED status."""
    names = [f"CH{i}" for i in range(n_channels)]
    data = [[float(i * 0.1 + j * 0.01) for j in range(n_samples)] for i in range(n_channels)]
    return {
        "channel_names": names,
        "channel_types": ["eeg"] * n_channels,
        "units": ["uV"] * n_channels,
        "sample_rate_hz": sample_rate_hz,
        "time_origin": "1970-01-01T00:00:00+00:00",
        "block_start_sample": 0,
        "block_end_sample": n_samples,
        "bad_channels": [],
        "events": [{"sample": 0, "id": 1, "description": "onset"}],
        "annotations": [{"onset_s": 0.0, "duration_s": 0.1, "description": "stim"}],
        "reference": "average",
        "montage_name": "synthetic-fixture",
        "montage_coordinates": [(0.0, 0.0, 0.0)] * n_channels,
        "preprocessing_history": ["fixture:none"],
        "source_id": "synthetic-in-memory",
        "source_sha256": "0" * 64,
        "data": data,
    }


def make_missing_units_payload() -> dict[str, Any]:
    payload = make_valid_block_payload()
    payload["units"] = [None, None]
    return payload


def make_missing_reference_payload() -> dict[str, Any]:
    payload = make_valid_block_payload()
    payload["reference"] = None
    return payload


def make_missing_montage_payload() -> dict[str, Any]:
    payload = make_valid_block_payload()
    payload["montage_name"] = None
    payload["montage_coordinates"] = None
    return payload


def make_shape_mismatch_payload() -> dict[str, Any]:
    payload = make_valid_block_payload(n_channels=2, n_samples=4)
    payload["data"] = [[0.0, 1.0, 2.0, 3.0]]  # one channel of samples
    return payload


def make_non_finite_payload() -> dict[str, Any]:
    payload = make_valid_block_payload(n_channels=1, n_samples=4)
    payload["data"] = [[0.0, float("nan"), 1.0, 2.0]]
    return payload


def make_empty_block_payload() -> dict[str, Any]:
    payload = make_valid_block_payload(n_channels=2, n_samples=0)
    payload["data"] = [[], []]
    payload["events"] = []
    payload["block_end_sample"] = 0
    return payload


def make_unsupported_channel_type_payload() -> dict[str, Any]:
    payload = make_valid_block_payload(n_channels=1, n_samples=4)
    payload["channel_types"] = ["hbo"]  # not in default allow-list
    return payload


def make_event_misaligned_payload() -> dict[str, Any]:
    payload = make_valid_block_payload(n_channels=1, n_samples=4)
    payload["events"] = [{"sample": 99, "id": 1}]
    return payload


def make_channel_order_payload() -> dict[str, Any]:
    """Distinct ordered channel names to assert order preservation."""
    payload = make_valid_block_payload(n_channels=3, n_samples=5)
    payload["channel_names"] = ["Fz", "Cz", "Pz"]
    payload["channel_types"] = ["eeg", "eeg", "eeg"]
    payload["units"] = ["uV", "uV", "uV"]
    payload["montage_coordinates"] = [(0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0)]
    payload["data"] = [
        [1.0, 2.0, 3.0, 4.0, 5.0],
        [10.0, 20.0, 30.0, 40.0, 50.0],
        [100.0, 200.0, 300.0, 400.0, 500.0],
    ]
    return payload


def clone_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(payload)
