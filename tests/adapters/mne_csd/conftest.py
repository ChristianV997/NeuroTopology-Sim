"""Shared duck-typed Raw fixtures for CSD adapter tests (no real EEG / no network)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import pytest


class FakeChannel(dict):
    pass


class FakeRaw:
    """Minimal MNE-like Raw for precondition and forwarding tests."""

    def __init__(
        self,
        ch_names: Sequence[str],
        *,
        ch_types: Optional[Sequence[str]] = None,
        locs: Optional[Sequence[Sequence[float]]] = None,
        data: Optional[List[List[float]]] = None,
        coord_frame: Any = "head",
        unit: Any = "V",
    ):
        self.ch_names = list(ch_names)
        self._ch_types = list(ch_types or ["eeg"] * len(ch_names))
        self._data = data
        chs = []
        for i, name in enumerate(self.ch_names):
            loc = list(locs[i]) if locs is not None else [0.0] * 12
            if len(loc) < 12:
                loc = list(loc) + [0.0] * (12 - len(loc))
            chs.append(
                FakeChannel(
                    ch_name=name,
                    loc=loc,
                    kind=self._ch_types[i],
                    ch_type=self._ch_types[i],
                    coord_frame=coord_frame,
                    unit=unit,
                )
            )
        self.info: Dict[str, Any] = {"chs": chs, "sfreq": 100.0}
        self._pick_calls: List[List[str]] = []
        self.set_eeg_reference_calls: List[Any] = []

    def get_channel_types(self) -> List[str]:
        return list(self._ch_types)

    def copy(self) -> "FakeRaw":
        cloned = FakeRaw(
            self.ch_names,
            ch_types=self._ch_types,
            locs=[ch["loc"] for ch in self.info["chs"]],
            data=None if self._data is None else [row[:] for row in self._data],
            coord_frame=self.info["chs"][0].get("coord_frame"),
            unit=self.info["chs"][0].get("unit"),
        )
        return cloned

    def pick(self, channels: Sequence[str]) -> "FakeRaw":
        channels = list(channels)
        self._pick_calls.append(channels)
        idxs = [self.ch_names.index(c) for c in channels]
        self.ch_names = channels
        self._ch_types = [self._ch_types[i] for i in idxs]
        self.info["chs"] = [self.info["chs"][i] for i in idxs]
        if self._data is not None:
            self._data = [self._data[i] for i in idxs]
        return self

    def set_eeg_reference(self, *args, **kwargs):
        self.set_eeg_reference_calls.append((args, kwargs))
        raise AssertionError("adapter must not call set_eeg_reference")

    def get_data(self):
        if self._data is None:
            return [[0.0, 1.0, 2.0] for _ in self.ch_names]
        return self._data


def standard_locs(n: int = 3) -> List[List[float]]:
    # Distinct non-zero 3D positions in meters (synthetic; not a real montage claim).
    base = [
        [0.00, 0.08, 0.06],
        [-0.05, 0.04, 0.05],
        [0.05, 0.04, 0.05],
        [0.00, 0.00, 0.09],
        [0.00, -0.08, 0.04],
    ]
    out = []
    for i in range(n):
        xyz = base[i % len(base)]
        out.append(list(xyz) + [0.0] * 9)
    return out


@pytest.fixture
def eeg_raw() -> FakeRaw:
    names = ["Fz", "Cz", "Pz"]
    return FakeRaw(names, locs=standard_locs(3))


@pytest.fixture
def eeg_raw_with_eog() -> FakeRaw:
    names = ["Fz", "Cz", "Pz", "EOG"]
    types = ["eeg", "eeg", "eeg", "eog"]
    locs = standard_locs(3) + [[0.0] * 12]
    return FakeRaw(names, ch_types=types, locs=locs)
