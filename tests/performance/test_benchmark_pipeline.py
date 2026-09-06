"""Smoke + equivalence tests for scripts/benchmark_streaming_pipeline.py."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

_SPEC = importlib.util.spec_from_file_location(
    "benchmark_streaming_pipeline",
    Path(__file__).resolve().parents[2] / "scripts" / "benchmark_streaming_pipeline.py",
)
bench = importlib.util.module_from_spec(_SPEC)
# Register before exec so dataclasses can resolve the module namespace.
sys.modules[_SPEC.name] = bench
_SPEC.loader.exec_module(bench)


def test_fixture_is_deterministic():
    a = bench.make_fixture(2000, 5, seed=7)
    b = bench.make_fixture(2000, 5, seed=7)
    assert np.array_equal(a, b)
    assert a.shape == (2000, 5) and a.dtype == np.float64


def test_baseline_and_optimized_equivalent_within_tolerance():
    report = bench.run_benchmark(channels=8, samples=20000, chunk_size=4096,
                                 window=1024, repeats=1, seed=0, tolerance=1e-9)
    ck = report["checksums"]
    assert ck["equivalent_within_tolerance"] is True
    assert ck["sample_rel_err"] <= 1e-9
    assert ck["moments_rel_err"] <= 1e-9
    assert ck["topo_rel_err"] <= 1e-9


def test_optimized_uses_less_peak_memory():
    report = bench.run_benchmark(channels=16, samples=40000, chunk_size=4096,
                                 window=1024, repeats=1, seed=1, tolerance=1e-9)
    assert report["peak_memory_ratio"] < 1.0  # bounded streaming wins on memory


def test_effective_chunk_size_is_window_aligned():
    assert bench.effective_chunk_size(4096, 1024) == 4096
    assert bench.effective_chunk_size(4097, 1024) == 5120
    assert bench.effective_chunk_size(100, 1024) == 1024


def test_main_json_returns_zero(capsys):
    rc = bench.main(["--channels", "4", "--samples", "8000", "--chunk-size", "2048",
                     "--window", "512", "--repeats", "1", "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"equivalent_within_tolerance": true' in out
