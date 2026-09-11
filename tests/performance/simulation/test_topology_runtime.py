"""Independent correctness and operational tests for the topology reuse hook."""
from __future__ import annotations

import json
import subprocess
import sys
import tracemalloc
from pathlib import Path

import numpy as np
import pytest

from sim.pitnn.topological_invariants import TopologicalInvariantTracker
from sim.pitnn.vampire_os_llg import LLGConfig, simulate_os_llg
import sim.pitnn.vampire_os_llg as llg
from tools.simulation_runtime.topology_metrics import audit_snapshot_reuse
from tools.streaming.process_runner import Outcome, build_python_command, run_one


ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / "scripts" / "benchmark_simulation_runtime.py"


def _spins(n: int = 32, seed: int = 5) -> np.ndarray:
    rng = np.random.default_rng(seed)
    values = rng.standard_normal((n, 3))
    return values / np.linalg.norm(values, axis=1, keepdims=True)


def test_reused_snapshot_matches_existing_tracker_independently():
    tracker = TopologicalInvariantTracker(48)
    for threshold in (0.0, 0.3, 1.0):
        spins = _spins(48, seed=int(threshold * 10) + 5)
        expected = tracker.audit_snapshot(spins, threshold=threshold)
        actual = audit_snapshot_reuse(tracker, spins, threshold=threshold)
        assert actual == expected


def test_full_production_trace_matches_reference_callback(monkeypatch):
    config = LLGConfig(n_spins=24, steps=12, seed=11)
    optimized = simulate_os_llg(config, backend="fast")
    monkeypatch.setattr(llg, "audit_snapshot_reuse", lambda tracker, spins: tracker.audit_snapshot(spins))
    reference = simulate_os_llg(config, backend="fast")
    assert optimized == reference


def test_invalid_threshold_keeps_tracker_error_contract():
    tracker = TopologicalInvariantTracker(8)
    with pytest.raises(ValueError, match="threshold must be finite"):
        audit_snapshot_reuse(tracker, _spins(8), threshold=-1.0)
    with pytest.raises(ValueError, match="threshold must be finite"):
        audit_snapshot_reuse(tracker, _spins(8), threshold=float("nan"))


def test_single_snapshot_memory_is_bounded():
    tracker = TopologicalInvariantTracker(2048)
    spins = _spins(2048)
    tracemalloc.start()
    tracemalloc.reset_peak()
    for _ in range(20):
        result = audit_snapshot_reuse(tracker, spins)
        assert set(result) == {
            "winding_number", "topological_charge", "beta1_loops",
            "max_chirality", "mean_chirality",
        }
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    # One snapshot is O(N) working memory; no trajectory/history is retained.
    assert peak < 2_000_000


def test_fresh_process_benchmark_emits_finite_telemetry():
    result = run_one(
        build_python_command(
            str(BENCHMARK),
            [
                "child", "--mode", "optimized", "--n-spins", "8", "--steps", "3",
                "--seed", "3", "--backend", "numpy", "--repetitions", "1",
            ],
        ),
        {"mode": "optimized", "n_spins": 8, "steps": 3, "seed": 3},
        timeout_s=30,
        required_metrics=("checksum", "tracemalloc_peak_bytes"),
    )
    assert result.outcome == Outcome.PASS
    assert result.timed_out is False
    payload = result.telemetry
    assert payload is not None
    json.dumps(payload, allow_nan=False)
    assert payload["evidence_class"] == "performance_only"
    assert payload["provenance_label"] == "local_deterministic_simulation_performance_only"
    assert payload["correctness_ok"] is True


def test_simulation_timeout_is_never_pass():
    result = run_one(
        build_python_command(
            str(BENCHMARK),
            [
                "child", "--mode", "optimized", "--n-spins", "8", "--steps", "3",
                "--seed", "3", "--backend", "numpy", "--repetitions", "1",
                "--inject-sleep", "10",
            ],
        ),
        {"mode": "optimized", "n_spins": 8, "steps": 3, "seed": 3},
        timeout_s=0.2,
    )
    assert result.outcome == Outcome.TIMEOUT
    assert result.timed_out is True
    assert result.checksum is None
