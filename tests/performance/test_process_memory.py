"""Tests for process-memory telemetry and the RSS benchmark runner.

These assert *reliable* properties only: types, finiteness, JSON-safety,
deterministic checksums, and the one memory relationship that is trustworthy in
a shared CI process (the ``tracemalloc`` peak, which reflects Python-level
allocation). They deliberately avoid gating on absolute wall-clock values or on
noisy process-RSS deltas, so correctness failures are separated from
performance regressions. Synthetic fixtures are performance scaffolding only.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from tools.streaming.memory_telemetry import (
    TelemetryRecord,
    dumps,
    get_peak_rss_bytes,
    get_rss_bytes,
    json_safe,
    measure_workload,
    provider_availability,
)

# Load the benchmark script by path (scripts/ is not a package).
_SPEC = importlib.util.spec_from_file_location(
    "benchmark_process_memory",
    Path(__file__).resolve().parents[2] / "scripts" / "benchmark_process_memory.py",
)
bench = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = bench
_SPEC.loader.exec_module(bench)


# --------------------------------------------------------------------------- #
# json_safe / dumps
# --------------------------------------------------------------------------- #
def test_json_safe_replaces_non_finite():
    assert json_safe(float("nan")) is None
    assert json_safe(float("inf")) is None
    assert json_safe(float("-inf")) is None
    assert json_safe(1.5) == 1.5
    nested = {"a": [float("nan"), 2.0], "b": {"c": float("inf")}}
    safe = json_safe(nested)
    assert safe["a"][0] is None and safe["a"][1] == 2.0
    assert safe["b"]["c"] is None


def test_dumps_emits_valid_finite_json():
    payload = {"x": float("nan"), "y": [1.0, float("inf")], "z": None, "n": 3}
    text = dumps(payload)
    assert "NaN" not in text and "Infinity" not in text
    parsed = json.loads(text)  # would raise on invalid JSON

    def _all_finite(obj):
        if isinstance(obj, float):
            assert math.isfinite(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                _all_finite(v)
        elif isinstance(obj, list):
            for v in obj:
                _all_finite(v)

    _all_finite(parsed)


# --------------------------------------------------------------------------- #
# RSS providers -- must never fabricate
# --------------------------------------------------------------------------- #
def test_rss_providers_return_int_or_none():
    rss = get_rss_bytes()
    peak = get_peak_rss_bytes()
    assert rss is None or (isinstance(rss, int) and rss > 0)
    assert peak is None or (isinstance(peak, int) and peak > 0)


def test_provider_availability_shape():
    prov = provider_availability()
    assert isinstance(prov.psutil, bool)
    assert isinstance(prov.resource, bool)
    assert isinstance(prov.proc_statm, bool)
    assert isinstance(prov.platform, str)


# --------------------------------------------------------------------------- #
# measure_workload
# --------------------------------------------------------------------------- #
def _work():
    a = np.ones((20000, 4), dtype=np.float64)
    return float(a.sum())


def test_measure_workload_record_shape_and_finiteness():
    rec = measure_workload(_work, label="unit", repetitions=2, backend="numpy",
                           input_dims={"samples": 20000, "channels": 4}, chunk_size=128)
    assert isinstance(rec, TelemetryRecord)
    assert rec.wall_best_s >= 0 and math.isfinite(rec.wall_best_s)
    assert rec.wall_mean_s >= 0 and math.isfinite(rec.wall_mean_s)
    assert rec.tracemalloc_peak_bytes is not None and rec.tracemalloc_peak_bytes >= 0
    assert math.isfinite(rec.checksum) and rec.checksum == 80000.0
    # Memory fields are int-or-None (never fabricated).
    for value in (rec.rss_before_bytes, rec.rss_after_bytes,
                  rec.rss_delta_bytes, rec.peak_rss_bytes):
        assert value is None or isinstance(value, int)
    assert rec.cpu_time_s is None or math.isfinite(rec.cpu_time_s)


def test_measure_workload_deterministic_checksum():
    a = measure_workload(_work, label="a", repetitions=1)
    b = measure_workload(_work, label="b", repetitions=1)
    assert a.checksum == b.checksum


def test_measure_workload_to_dict_is_json_safe():
    rec = measure_workload(_work, label="unit", repetitions=1)
    text = dumps(rec.to_dict())
    assert "NaN" not in text and "Infinity" not in text
    json.loads(text)


def test_measure_workload_rejects_bad_repetitions():
    with pytest.raises(ValueError):
        measure_workload(_work, label="x", repetitions=0)


# --------------------------------------------------------------------------- #
# Benchmark runner
# --------------------------------------------------------------------------- #
def test_make_signal_deterministic():
    a = bench.make_signal(1000, 4, seed=1)
    b = bench.make_signal(1000, 4, seed=1)
    assert np.array_equal(a, b) and a.shape == (1000, 4)


def test_streaming_bounded_matches_full_checksum_within_tolerance():
    sig = bench.make_signal(20000, 8, seed=0)
    full = bench.full_materialization_checksum(sig)
    for chunk in (256, 4096, 20000):
        bnd = bench.bounded_checksum(sig, chunk)
        assert bench._rel_err(full, bnd) <= 1e-9


def test_run_streaming_configs_equivalent_and_tracemalloc_bounded():
    out = bench.run_streaming_configs(
        samples_list=[20000], channels_list=[8], chunk_sizes=[1024, 8192],
        repeats=1, seed=0, tolerance=1e-9,
    )
    assert out["comparisons"], "expected comparisons"
    for comp in out["comparisons"]:
        assert comp["equivalent_within_tolerance"] is True
        # tracemalloc peak is the reliable memory signal in-process.
        assert comp["tracemalloc_bounded_lower"] is True
    # every record must be JSON-safe
    text = dumps(out)
    assert "NaN" not in text and "Infinity" not in text


def test_kernel_backend_determinism_within_backend():
    out = bench.run_kernel_configs(n_spins=32, n_steps=50, repeats=1, seed=0, tolerance=1e-9)
    assert "numpy" in out["backends_measured"]
    # Deterministic within a backend: rerun numpy path and compare.
    c1 = bench.kernel_checksum(32, 50, seed=0)
    c2 = bench.kernel_checksum(32, 50, seed=0)
    assert c1 == c2
    for rec in out["records"]:
        assert math.isfinite(rec["checksum"])


def test_kernel_numpy_fallback_available(monkeypatch):
    import sim.pitnn.kernels_fast as kf
    monkeypatch.setattr(kf, "NUMBA_AVAILABLE", False)
    out = bench.run_kernel_configs(n_spins=16, n_steps=20, repeats=1, seed=0, tolerance=1e-9)
    assert out["backends_measured"] == ["numpy"]
    assert math.isfinite(out["per_backend_checksums"]["numpy"])


def test_main_json_smoke(capsys):
    rc = bench.main([
        "--samples-list", "8000", "--channels-list", "4",
        "--chunk-sizes", "512", "4096", "--repeats", "1",
        "--kernel-spins", "16", "--kernel-steps", "20", "--json",
    ])
    assert rc == 0
    text = capsys.readouterr().out
    assert "NaN" not in text and "Infinity" not in text
    report = json.loads(text)
    assert report["streaming_all_equivalent"] is True
    assert "records" in report["streaming"] and "records" in report["kernel"]
