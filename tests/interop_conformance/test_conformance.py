"""End-to-end integration tests for the conformance validator suite."""

from __future__ import annotations

from pathlib import Path
import pytest

from tests.interop_conformance.reference import synthetic_conforming_adapter
from tests.interop_conformance.validator import ConformanceValidator


def test_conformance_suite_self_test(fixture_numpy_path, fixture_csv_path, fixture_fif_metadata_path):
    """Verifies that an idealized reference adapter achieves 100% PASS on all chunk properties."""
    chunks = list(synthetic_conforming_adapter(None, chunk_seconds=1.0, total_seconds=2.0))
    assert len(chunks) == 2

    for chunk in chunks:
        assert ConformanceValidator.validate_property_1_shape(chunk).passed
        assert ConformanceValidator.validate_property_2_channel_order(chunk).passed
        assert ConformanceValidator.validate_property_3_sampling_rate(chunk, 200.0).passed
        assert ConformanceValidator.validate_property_4_units_and_scaling(chunk).passed
        assert ConformanceValidator.validate_property_5_source_checksum(chunk).passed
        assert ConformanceValidator.validate_property_6_montage_coordinates(chunk).passed
        assert ConformanceValidator.validate_property_7_inferred_provenance(chunk).passed
        assert ConformanceValidator.validate_property_8_no_silent_fabrication(chunk).passed
        assert ConformanceValidator.validate_property_16_finite_numeric_values(chunk).passed

    assert ConformanceValidator.validate_property_9_chunk_boundaries(chunks).passed
