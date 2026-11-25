from __future__ import annotations

import json
import math
import socket
import sys

import numpy as np
import pytest

from topo_monitor.higher_order.spectra import (
    amplitude_shuffle_surrogate,
    block_shuffle_surrogate,
    compute_bispectrum,
    compute_higher_order_spectra,
    compute_modulogram,
    phase_randomized_surrogate,
    report_to_json,
)
from topo_monitor.higher_order.spectral_types import SegmentConfiguration


def _config(**overrides):
    values = dict(
        segment_length=256,
        n_fft=256,
        overlap=0.5,
        frequency_bins=24,
        trispectrum_slices=3,
        max_channels=4,
        memory_budget_bytes=16 * 1024 * 1024,
        max_surrogates=4,
    )
    values.update(overrides)
    return SegmentConfiguration(**values)


def _am_signal(seed: int = 3, sampling_rate_hz: float = 256.0, seconds: float = 8.0):
    rng = np.random.default_rng(seed)
    time = np.arange(int(sampling_rate_hz * seconds)) / sampling_rate_hz
    carrier = 40.0
    modulation = 5.0
    signal = (1.0 + 0.7 * np.sin(2 * np.pi * modulation * time)) * np.sin(2 * np.pi * carrier * time)
    return signal + 0.01 * rng.normal(size=time.size), sampling_rate_hz, carrier, modulation


def _assert_finite_json(value):
    if isinstance(value, dict):
        for item in value.values():
            _assert_finite_json(item)
    elif isinstance(value, list):
        for item in value:
            _assert_finite_json(item)
    elif isinstance(value, float):
        assert math.isfinite(value)


def test_known_amplitude_modulated_signal_has_bounded_modulogram_feature():
    signal, rate, carrier, modulation = _am_signal()
    config = _config(n_fft=512, segment_length=512, frequency_bins=96)
    result = compute_modulogram(signal, rate, config=config)
    carrier_index = min(range(len(result.carrier_axis.frequencies_hz)), key=lambda i: abs(result.carrier_axis.frequencies_hz[i] - carrier))
    modulation_index = min(range(len(result.modulation_axis.frequencies_hz)), key=lambda i: abs(result.modulation_axis.frequencies_hz[i] - modulation))
    value = result.magnitude[carrier_index][modulation_index]
    assert value is not None and value > 0.05
    assert result.representation == "reduced_carrier_modulation_map"


def test_independent_gaussian_noise_is_finite_and_not_a_topology_claim():
    rng = np.random.default_rng(11)
    result = compute_higher_order_spectra(
        rng.normal(size=(2, 2048)), 256.0, config=_config(), synthetic=True
    )
    payload = result.to_dict()
    _assert_finite_json(payload)
    assert all("topological" not in key.lower() for key in payload)
    assert result.provenance.synthetic is True


def test_frequency_axis_and_sampling_provenance_are_correct():
    signal = np.sin(2 * np.pi * 8 * np.arange(1024) / 256.0)
    result = compute_bispectrum(signal, 256.0, config=_config(n_fft=128, segment_length=128))
    axis = result.frequency_axis
    assert axis.resolution_hz == pytest.approx(2.0)
    assert axis.frequencies_hz[:3] == pytest.approx((0.0, 2.0, 4.0))
    report = compute_higher_order_spectra(signal, 256.0, config=_config(n_fft=128, segment_length=128), synthetic=True)
    assert report.provenance.sampling_rate_hz == 256.0
    assert len(report.provenance.checksum_sha256) == 64


def test_repeatability_includes_surrogate_seed_and_checksum():
    signal, rate, _, _ = _am_signal()
    kwargs = dict(
        config=_config(), synthetic=True, surrogate_methods=("amplitude_shuffle", "phase_randomized", "block_shuffle"),
        surrogate_count=2, seed=19,
    )
    assert report_to_json(compute_higher_order_spectra(signal, rate, **kwargs)) == report_to_json(
        compute_higher_order_spectra(signal, rate, **kwargs)
    )
    assert np.array_equal(amplitude_shuffle_surrogate(signal, seed=19), amplitude_shuffle_surrogate(signal, seed=19))
    assert np.array_equal(phase_randomized_surrogate(signal, seed=19), phase_randomized_surrogate(signal, seed=19))
    assert np.array_equal(block_shuffle_surrogate(signal, block_length=64, seed=19), block_shuffle_surrogate(signal, block_length=64, seed=19))


def test_segment_and_taper_changes_are_explicit():
    signal = np.random.default_rng(2).normal(size=1024)
    short = compute_modulogram(signal, 256.0, config=_config(segment_length=128, n_fft=128, taper="boxcar"))
    long = compute_modulogram(signal, 256.0, config=_config(segment_length=256, n_fft=256, taper="hann"))
    assert short.segment_count != long.segment_count
    assert short.carrier_axis.resolution_hz != long.carrier_axis.resolution_hz


def test_malformed_sampling_rate_is_rejected():
    with pytest.raises(ValueError):
        compute_bispectrum(np.ones(512), 0.0, config=_config())
    with pytest.raises(ValueError):
        compute_bispectrum(np.ones(512), float("nan"), config=_config())


def test_memory_budget_is_hard_and_does_not_allocate_unbounded_arrays():
    with pytest.raises(MemoryError):
        compute_bispectrum(
            np.ones((2, 4096)), 256.0,
            config=_config(memory_budget_bytes=4096, segment_length=256, n_fft=512),
        )


def test_optional_scipy_absence_does_not_break_numpy_estimator(monkeypatch):
    monkeypatch.setitem(sys.modules, "scipy", None)
    signal = np.random.default_rng(8).normal(size=1024)
    result = compute_modulogram(signal, 256.0, config=_config())
    assert result.segment_count > 0


def test_no_network_operation(monkeypatch):
    def fail_socket(*args, **kwargs):
        raise AssertionError("higher-order estimator must not use a network")

    monkeypatch.setattr(socket, "socket", fail_socket)
    result = compute_higher_order_spectra(
        np.random.default_rng(5).normal(size=1024), 256.0, config=_config(), synthetic=True
    )
    assert result.errors == ()


def test_report_json_is_strict_and_contains_schema_version():
    report = compute_higher_order_spectra(
        np.random.default_rng(7).normal(size=(2, 1024)), 256.0, config=_config(), synthetic=True
    )
    encoded = report_to_json(report)
    parsed = json.loads(encoded)
    _assert_finite_json(parsed)
    assert parsed["schema_version"] == "NeuroTopologySim.HigherOrderSpectra.v1"
    assert parsed["provenance"]["frequency_units"] == "Hz"
