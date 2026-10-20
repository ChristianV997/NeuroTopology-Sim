"""Regression coverage for strict MNE sample-bound validation."""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

import numpy as np

from adapters.mne_signal_blocks import BlockStatus, convert_from_mne_object
from adapters.mne_signal_blocks.schema import ReasonCode


class _FakeRaw:
    """Small synthetic Raw-like object; no MNE installation or files needed."""

    def __init__(self) -> None:
        self.info = {
            "ch_names": ["Cz"],
            "chs": [{"unit": "uV"}],
            "sfreq": 100.0,
            "bads": [],
            "custom_ref_applied": "average",
            "meas_date": None,
            "highpass": 0.0,
            "lowpass": 50.0,
        }
        self.data = np.arange(8, dtype=float).reshape(1, 8)
        self.n_times = 8
        self.preload = True
        self.slice_calls = 0

    def __getitem__(self, key: tuple[object, slice]) -> tuple[np.ndarray, np.ndarray]:
        self.slice_calls += 1
        selection = key[1]
        selected = self.data[:, selection]
        times = np.arange(selected.shape[1], dtype=float) / 100.0
        return selected, times

    def get_montage(self) -> types.SimpleNamespace:
        return types.SimpleNamespace(kind="standard_1020")


class TestMneSampleBounds(unittest.TestCase):
    def setUp(self) -> None:
        self.mne = types.ModuleType("mne")
        self.mne.__version__ = "synthetic-test-fixture"
        self.mne.channel_type = lambda _info, _index: "eeg"
        self.mne_context = patch.dict(sys.modules, {"mne": self.mne})
        self.mne_context.start()
        self.addCleanup(self.mne_context.stop)

    def _convert(self, start: object, stop: object):
        raw = _FakeRaw()
        result = convert_from_mne_object(
            raw, source_id="synthetic-fixture", start_sample=start, stop_sample=stop
        )
        return raw, result

    def _assert_rejected_bounds(self, start: object, stop: object) -> None:
        raw, result = self._convert(start, stop)
        self.assertEqual(result.block.status, BlockStatus.REJECTED)
        self.assertIn(ReasonCode.INVALID_SAMPLE_BOUNDS.value, result.block.reason_codes)
        self.assertEqual(raw.slice_calls, 0, "invalid bounds must be rejected before slicing")
        rendered = " ".join(result.block.warnings) + " " + " ".join(result.block.reason_codes)
        self.assertNotIn(str(start), rendered)
        self.assertNotIn(str(stop), rendered)

    def test_fractional_bounds_are_rejected_before_slicing(self) -> None:
        for start, stop in ((1.25, 6), (1, 6.75)):
            with self.subTest(start=start, stop=stop):
                self._assert_rejected_bounds(start, stop)

    def test_boolean_bounds_are_rejected_before_slicing(self) -> None:
        for start, stop in ((False, 6), (1, True)):
            with self.subTest(start=start, stop=stop):
                self._assert_rejected_bounds(start, stop)

    def test_numeric_string_bounds_are_rejected_without_echoing_values(self) -> None:
        for start, stop in (("1", 6), (1, "6")):
            with self.subTest(start_type=type(start).__name__, stop_type=type(stop).__name__):
                self._assert_rejected_bounds(start, stop)

    def test_negative_bounds_are_rejected_before_slicing(self) -> None:
        for start, stop in ((-1, 3), (1, -1)):
            with self.subTest(start=start, stop=stop):
                self._assert_rejected_bounds(start, stop)

    def test_reversed_bounds_are_rejected_before_slicing(self) -> None:
        self._assert_rejected_bounds(6, 2)

    def test_out_of_range_bounds_are_rejected_before_slicing(self) -> None:
        for start, stop in ((1, 9), (8, 9)):
            with self.subTest(start=start, stop=stop):
                self._assert_rejected_bounds(start, stop)

    def test_valid_python_and_numpy_integer_bounds_are_preserved(self) -> None:
        for start, stop in ((1, 6), (np.int64(1), np.int64(6))):
            with self.subTest(start_type=type(start).__name__):
                raw, result = self._convert(start, stop)
                self.assertEqual(result.block.status, BlockStatus.CONVERTED)
                self.assertEqual(result.block.block_start_sample, 1)
                self.assertEqual(result.block.block_end_sample, 6)
                self.assertEqual(result.block.data_shape, (1, 5))
                self.assertEqual(raw.slice_calls, 1)

    def test_omitted_stop_defaults_to_source_length(self) -> None:
        raw = _FakeRaw()
        result = convert_from_mne_object(
            raw, source_id="synthetic-fixture", start_sample=2
        )
        self.assertEqual(result.block.status, BlockStatus.CONVERTED)
        self.assertEqual(result.block.block_start_sample, 2)
        self.assertEqual(result.block.block_end_sample, raw.n_times)
        self.assertEqual(result.block.data_shape, (1, raw.n_times - 2))


if __name__ == "__main__":
    unittest.main()
