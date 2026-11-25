from __future__ import annotations

import json
import socket

import pytest

from tools.higher_order_integration.spectral_adapter import (
    SCHEMA_VERSION,
    adapt_spectral_feature_report,
    contract_to_json,
    contract_to_markdown,
)


def _report(*, synthetic=False, taper="hann", segment_length=256, sampling_rate=256.0):
    axis = {"frequencies_hz": [0.0, 1.0, 2.0], "resolution_hz": 1.0, "nyquist_hz": 128.0, "units": "Hz"}
    matrix = [[0.0, 0.1, 0.2], [0.1, 0.4, 0.2], [0.2, 0.2, 0.3]]
    return {
        "schema_version": "NeuroTopologySim.HigherOrderSpectra.v1",
        "provenance": {
            "source": "fixture",
            "sampling_rate_hz": sampling_rate,
            "synthetic": synthetic,
            "checksum_sha256": "a" * 64,
            "n_channels": 2,
            "n_samples": 1024,
            "frequency_units": "Hz",
        },
        "segment_configuration": {
            "segment_length": segment_length,
            "n_fft": segment_length,
            "overlap": 0.5,
            "taper": taper,
            "frequency_bins": 3,
            "memory_budget_bytes": 1024 * 1024,
        },
        "channel_identity": ["left", "right"],
        "condition_label": "amplitude_modulated_carrier",
        "preprocessing": {"filtering": "none"},
        "diagnostics": {"edge_effect_warning": "finite segments"},
        "bispectrum": {
            "frequency_axis": axis,
            "magnitude": matrix,
            "bicoherence": matrix,
            "segment_count": 7,
        },
        "trispectrum": {
            "frequency_axis": axis,
            "slice_frequencies_hz": [1.0],
            "magnitude": [matrix],
            "segment_count": 7,
        },
        "modulogram": {
            "carrier_axis": axis,
            "modulation_axis": axis,
            "magnitude": matrix,
            "segment_count": 7,
        },
        "comparisons": {
            "psd": {"frequency_axis": axis, "power": [0.1, 0.2, 0.3]},
            "cross_spectrum": {"available": True, "frequency_axis": axis, "magnitude": [0.1, 0.2, 0.3], "phase_radians": [0.0, 0.1, -0.1]},
            "phase_amplitude_coupling": {"available": True, "phase_band_hz": [4.0, 8.0], "amplitude_band_hz": [30.0, 80.0], "modulation_index": 0.2},
            "pairwise_cross_frequency": {"available": True, "frequency_axis": axis, "magnitude": matrix},
        },
        "surrogates": [{"method": "phase_randomized", "seed": 7, "surrogate_count": 8}],
    }


def test_amplitude_modulated_carrier_normalizes_all_comparison_families():
    contract = adapt_spectral_feature_report(_report(), channel_identity="left-right")
    families = {record.feature_family for record in contract.records}
    assert {"psd", "cross_spectrum", "pac", "bispectrum", "trispectrum_slice", "modulogram"}.issubset(families)
    modulogram = next(record for record in contract.records if record.feature_family == "modulogram")
    assert modulogram.metadata["condition_label"] == "amplitude_modulated_carrier"
    assert modulogram.metadata["channel_identity"] == "left-right"
    assert modulogram.edge_effects["declared"] is True
    assert not contract.validation_errors


def test_gaussian_null_preserves_synthetic_status_and_descriptive_class():
    contract = adapt_spectral_feature_report(_report(synthetic=True))
    assert contract.synthetic is True
    assert contract.evidence_class == "synthetic_signal_processing_descriptive"
    assert all(record.metadata["synthetic"] is True for record in contract.records)


def test_frequency_axis_error_is_explicit():
    report = _report()
    report["bispectrum"]["frequency_axis"]["frequencies_hz"] = [0.0, 2.0, 1.0]
    contract = adapt_spectral_feature_report(report)
    assert any("strictly monotonic" in error for error in contract.validation_errors)


def test_nonfinite_input_values_are_not_silently_accepted():
    report = _report()
    report["comparisons"]["psd"]["power"][1] = float("nan")
    contract = adapt_spectral_feature_report(report)
    assert any("nonfinite" in error for error in contract.validation_errors)
    psd = next(record for record in contract.records if record.feature_family == "psd")
    assert psd.values[1] is None


def test_complex_value_representation_is_explicit_and_finite():
    report = _report()
    report["comparisons"]["cross_spectrum"]["magnitude"] = [
        {"real": 0.1, "imag": -0.2}, {"real": 0.2, "imag": 0.0}, {"real": 0.3, "imag": 0.1}
    ]
    contract = adapt_spectral_feature_report(report)
    cross = next(record for record in contract.records if record.feature_family == "cross_spectrum")
    assert cross.values["magnitude"][0] == {"real": 0.1, "imag": -0.2}
    assert not contract.validation_errors


def test_negative_psd_like_values_are_rejected():
    report = _report()
    report["comparisons"]["psd"]["power"][0] = -0.1
    contract = adapt_spectral_feature_report(report)
    assert any("nonnegative" in error for error in contract.validation_errors)


def test_taper_and_segment_sensitivity_are_preserved():
    hann = adapt_spectral_feature_report(_report(taper="hann", segment_length=256))
    blackman = adapt_spectral_feature_report(_report(taper="blackman", segment_length=128))
    assert hann.records[0].metadata["taper"] == "hann"
    assert blackman.records[0].metadata["taper"] == "blackman"
    assert hann.records[0].metadata["segment_length"] != blackman.records[0].metadata["segment_length"]


def test_missing_sampling_rate_is_invalid():
    report = _report()
    del report["provenance"]["sampling_rate_hz"]
    contract = adapt_spectral_feature_report(report)
    assert any("sampling_rate_hz" in error for error in contract.validation_errors)


def test_deterministic_json_and_markdown_outputs():
    first = adapt_spectral_feature_report(_report())
    second = adapt_spectral_feature_report(_report())
    assert contract_to_json(first) == contract_to_json(second)
    markdown = contract_to_markdown(first)
    assert "Spectral feature contract" in markdown
    assert SCHEMA_VERSION in markdown


def test_no_network_behavior(monkeypatch):
    def fail_socket(*args, **kwargs):
        raise AssertionError("adapter must not use a network")

    monkeypatch.setattr(socket, "socket", fail_socket)
    assert adapt_spectral_feature_report(_report()).records


def test_missing_filter_and_edge_metadata_are_explicit_warnings():
    report = _report()
    del report["preprocessing"]
    del report["diagnostics"]
    contract = adapt_spectral_feature_report(report)
    assert any("filtering metadata" in warning for warning in contract.validation_warnings)
    assert any("edge-effect metadata" in warning for warning in contract.validation_warnings)
    assert all(record.filtering_status == "not_declared" for record in contract.records)
