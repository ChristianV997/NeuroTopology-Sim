"""Comprehensive tests validating the 16 signal interoperability contract rules."""

from __future__ import annotations

import copy
import json
import math
import numpy as np
import pytest

from tests.interop_conformance.reference import (
    ConformingSignalChunk,
    create_synthetic_chunk,
    synthetic_conforming_adapter,
)
from tests.interop_conformance.validator import ConformanceValidator


class TestContractRules:
    """Rigorous conformance validation of the 16 contract properties."""

    def test_rule_1_shape_channels_samples(self):
        # Passing case
        chunk = create_synthetic_chunk(channels=4, samples=128)
        eval_pass = ConformanceValidator.validate_property_1_shape(chunk)
        assert eval_pass.passed
        assert eval_pass.diagnostics["channels"] == 4
        assert eval_pass.diagnostics["samples"] == 128

        # Failing case: transposed shape (1D or 3D)
        bad_chunk = copy.deepcopy(chunk)
        bad_chunk.data = np.zeros(128)
        eval_fail_1d = ConformanceValidator.validate_property_1_shape(bad_chunk)
        assert not eval_fail_1d.passed

        bad_chunk.data = np.zeros((1, 4, 128))
        eval_fail_3d = ConformanceValidator.validate_property_1_shape(bad_chunk)
        assert not eval_fail_3d.passed

    def test_rule_2_channel_order_deterministic(self):
        # Passing case
        channels = ["Fp1", "Fp2", "Cz", "Oz"]
        chunk = create_synthetic_chunk(channels=4, channel_names=channels)
        eval_pass = ConformanceValidator.validate_property_2_channel_order(chunk, expected_channels=channels)
        assert eval_pass.passed

        # Failing case: channel count mismatch
        bad_chunk = copy.deepcopy(chunk)
        bad_chunk.channel_names = ("Fp1", "Fp2")
        eval_fail_count = ConformanceValidator.validate_property_2_channel_order(bad_chunk)
        assert not eval_fail_count.passed

        # Failing case: channel order reversed
        eval_fail_order = ConformanceValidator.validate_property_2_channel_order(chunk, expected_channels=list(reversed(channels)))
        assert not eval_fail_order.passed

    def test_rule_3_sampling_frequency_exact(self):
        # Passing case
        chunk = create_synthetic_chunk(sample_rate=256.0)
        eval_pass = ConformanceValidator.validate_property_3_sampling_rate(chunk, nominal_rate=256.0)
        assert eval_pass.passed

        # Failing case: rate modified or non-positive
        bad_chunk = copy.deepcopy(chunk)
        bad_chunk.sample_rate_hz = 0.0
        eval_fail_zero = ConformanceValidator.validate_property_3_sampling_rate(bad_chunk)
        assert not eval_fail_zero.passed

        eval_fail_nominal = ConformanceValidator.validate_property_3_sampling_rate(chunk, nominal_rate=512.0)
        assert not eval_fail_nominal.passed

    def test_rule_4_units_and_scaling_explicit(self):
        # Passing case
        chunk = create_synthetic_chunk(channels=3, units=["uV", "uV", "uV"])
        eval_pass = ConformanceValidator.validate_property_4_units_and_scaling(chunk)
        assert eval_pass.passed

        # Failing case: missing or empty units
        bad_chunk = copy.deepcopy(chunk)
        bad_chunk.units = ["uV", ""]
        eval_fail = ConformanceValidator.validate_property_4_units_and_scaling(bad_chunk)
        assert not eval_fail.passed

    def test_rule_5_source_checksum_deterministic(self):
        # Passing case
        chunk = create_synthetic_chunk()
        eval_pass = ConformanceValidator.validate_property_5_source_checksum(chunk, expected_checksum=chunk.source_sha256)
        assert eval_pass.passed

        # Failing case: invalid hex or wrong length
        bad_chunk = copy.deepcopy(chunk)
        bad_chunk.source_sha256 = "not_a_valid_sha256"
        eval_fail = ConformanceValidator.validate_property_5_source_checksum(bad_chunk)
        assert not eval_fail.passed

    def test_rule_6_montage_coordinates_state(self):
        # Native/provided coordinates
        chunk_with_coords = create_synthetic_chunk(channels=3, has_coordinates=True)
        eval_coords = ConformanceValidator.validate_property_6_montage_coordinates(chunk_with_coords)
        assert eval_coords.passed

        # Explicitly unavailable coordinates (None)
        chunk_no_coords = create_synthetic_chunk(channels=3, has_coordinates=False)
        chunk_no_coords.montage_coordinates = None
        eval_none = ConformanceValidator.validate_property_6_montage_coordinates(chunk_no_coords)
        assert eval_none.passed
        assert eval_none.diagnostics["state"] == "unavailable"

        # Invalid shape for coordinates
        bad_chunk = copy.deepcopy(chunk_with_coords)
        bad_chunk.montage_coordinates = [[1.0, 2.0]]  # 2D instead of 3D
        eval_bad = ConformanceValidator.validate_property_6_montage_coordinates(bad_chunk)
        assert not eval_bad.passed

    def test_rule_7_inferred_coordinates_provenance(self):
        # Coordinates with valid provenance
        chunk = create_synthetic_chunk(has_coordinates=True)
        chunk.montage_name = "standard_1020"
        eval_pass = ConformanceValidator.validate_property_7_inferred_provenance(chunk)
        assert eval_pass.passed

        # Coordinates without provenance
        bad_chunk = copy.deepcopy(chunk)
        bad_chunk.montage_name = ""
        eval_fail = ConformanceValidator.validate_property_7_inferred_provenance(bad_chunk)
        assert not eval_fail.passed

    def test_rule_8_no_silent_coordinate_fabrication(self):
        # Clean coordinates
        chunk = create_synthetic_chunk(has_coordinates=True)
        eval_pass = ConformanceValidator.validate_property_8_no_silent_fabrication(chunk)
        assert eval_pass.passed

        # Coordinates containing NaN
        bad_chunk = copy.deepcopy(chunk)
        bad_chunk.montage_coordinates[0][0] = float("nan")
        eval_fail = ConformanceValidator.validate_property_8_no_silent_fabrication(bad_chunk)
        assert not eval_fail.passed

    def test_rule_9_reproducible_chunk_boundaries(self):
        chunks = list(synthetic_conforming_adapter(None, chunk_seconds=1.0, total_seconds=3.0))
        eval_pass = ConformanceValidator.validate_property_9_chunk_boundaries(chunks)
        assert eval_pass.passed

        # Corrupt chunk index
        bad_chunks = copy.deepcopy(chunks)
        bad_chunks[1].chunk_index = 5
        eval_fail = ConformanceValidator.validate_property_9_chunk_boundaries(bad_chunks)
        assert not eval_fail.passed

    def test_rule_10_structured_capability_state(self):
        # Proper capability state
        def check_cap():
            return {"installed": True, "version": "1.2.0"}
        eval_pass = ConformanceValidator.validate_property_10_capability_state("test_adapter", check_cap)
        assert eval_pass.passed

        # Improper capability state (not a dict or missing installed)
        eval_fail = ConformanceValidator.validate_property_10_capability_state("test_adapter", lambda: ["installed"])
        assert not eval_fail.passed

    def test_rule_11_actionable_malformed_errors(self, fixture_malformed_path):
        def failing_adapter(path):
            raise ValueError("Malformed header in signal file")

        eval_pass = ConformanceValidator.validate_property_11_malformed_errors(failing_adapter, fixture_malformed_path)
        assert eval_pass.passed

        # Silent success on malformed file
        def silent_adapter(path):
            return iter([])

        eval_fail = ConformanceValidator.validate_property_11_malformed_errors(silent_adapter, fixture_malformed_path)
        assert not eval_fail.passed

    def test_rule_12_no_network_access(self):
        def offline_fn():
            return 42

        eval_pass = ConformanceValidator.validate_property_12_no_network(offline_fn)
        assert eval_pass.passed

        def online_fn():
            import socket
            s = socket.socket()

        eval_fail = ConformanceValidator.validate_property_12_no_network(online_fn)
        assert not eval_fail.passed

    def test_rule_13_lazy_imports(self):
        # We test that a built-in module does not import mne eagerly
        eval_res = ConformanceValidator.validate_property_13_lazy_imports("math", "mne")
        assert eval_res.passed

    def test_rule_14_metadata_preservation(self, fixture_fif_metadata_path):
        with open(fixture_fif_metadata_path, "r", encoding="utf-8") as f:
            meta = json.load(f)

        chunk = create_synthetic_chunk(
            channels=len(meta["channels"]),
            sample_rate=meta["sample_rate_hz"],
            channel_names=meta["channels"],
            units=meta["units"],
        )
        chunk.source_sha256 = meta["source_sha256"]

        eval_pass = ConformanceValidator.validate_property_14_metadata_preservation(meta, chunk)
        assert eval_pass.passed

        # Mismatched sample rate
        bad_chunk = copy.deepcopy(chunk)
        bad_chunk.sample_rate_hz = 1000.0
        eval_fail = ConformanceValidator.validate_property_14_metadata_preservation(meta, bad_chunk)
        assert not eval_fail.passed

    def test_rule_15_edge_case_inputs(self, tmp_path):
        empty_file = tmp_path / "empty.bin"
        empty_file.write_bytes(b"")

        def strict_adapter(path):
            if path.stat().st_size == 0:
                raise ValueError("Empty signal input")
            return iter([])

        eval_pass = ConformanceValidator.validate_property_15_edge_cases(strict_adapter, empty_file)
        assert eval_pass.passed

    def test_rule_16_finite_numeric_values(self):
        chunk = create_synthetic_chunk()
        eval_pass = ConformanceValidator.validate_property_16_finite_numeric_values(chunk)
        assert eval_pass.passed

        # Non-finite data
        bad_chunk = copy.deepcopy(chunk)
        bad_chunk.data[0, 0] = np.nan
        eval_fail = ConformanceValidator.validate_property_16_finite_numeric_values(bad_chunk)
        assert not eval_fail.passed
