"""Tests for the research-cycle resource benchmark harness.

Cover deterministic fixtures, budget pass/overrun, timeout, missing metric,
checksum mismatch, malformed record, finite JSON, no-network, and bounded worker
count. Synthetic only; no datasets, no simulations, no network, no external APIs.
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
from pathlib import Path

import pytest

from tools.benchmarking.research_cycle_benchmarks.budgets import ResourceBudgets, compare_budget
from tools.benchmarking.research_cycle_benchmarks.fixtures import make_fixture
from tools.benchmarking.research_cycle_benchmarks.harness import (
    SCHEMA_VERSION,
    run_all,
    run_target,
)
from tools.benchmarking.research_cycle_benchmarks.telemetry import (
    dumps,
    execute_child,
    json_safe,
    measure,
)
from tools.benchmarking.research_cycle_benchmarks.workloads import TARGETS, TargetSpec

REPO_ROOT = Path(__file__).resolve().parents[3]

# Load the CLI script by path (scripts/ is not a package).
_SPEC = importlib.util.spec_from_file_location(
    "benchmark_research_cycle", REPO_ROOT / "scripts" / "benchmark_research_cycle.py")
cli = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = cli
_SPEC.loader.exec_module(cli)


def _assert_finite(obj):
    if isinstance(obj, float):
        assert math.isfinite(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _assert_finite(v)
    elif isinstance(obj, list):
        for v in obj:
            _assert_finite(v)


# --------------------------------------------------------------------------- #
# Deterministic fixtures + equivalence
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("target", sorted(TARGETS.keys()))
def test_deterministic_fixture(target):
    a = make_fixture(target, seed=7, size=64)
    b = make_fixture(target, seed=7, size=64)
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


@pytest.mark.parametrize("target", sorted(TARGETS.keys()))
def test_baseline_candidate_equivalent(target):
    rec = run_target(TARGETS[target], ResourceBudgets(), seed=0, size=128, repetitions=1)
    assert rec["status"] == "ok"
    assert rec["deterministic"]["checksum_match"] is True


def test_deterministic_checksums_stable_across_runs():
    r1 = run_all(seed=0, size=100, repetitions=1)
    r2 = run_all(seed=0, size=100, repetitions=1)
    d1 = [(r["target"], r["deterministic"]["checksum_baseline"],
           r["deterministic"]["checksum_candidate"]) for r in r1["results"]]
    d2 = [(r["target"], r["deterministic"]["checksum_baseline"],
           r["deterministic"]["checksum_candidate"]) for r in r2["results"]]
    assert d1 == d2


# --------------------------------------------------------------------------- #
# Budgets
# --------------------------------------------------------------------------- #
def test_budget_pass():
    huge = ResourceBudgets(memory_bytes=10**12, disk_bytes=10**12)
    rec = run_target(TARGETS["ledger_append_export"], huge, seed=0, size=100, repetitions=1)
    assert rec["deterministic"]["budget"]["within_budget"] is True


def test_budget_overrun():
    tiny = ResourceBudgets(memory_bytes=1, disk_bytes=1)
    rec = run_target(TARGETS["ledger_append_export"], tiny, seed=0, size=200, repetitions=1)
    assert rec["deterministic"]["budget"]["within_budget"] is False
    assert any("budget" in r for r in rec["recommendations"])


def test_missing_metric_is_null_not_zero():
    # No runtime budget configured -> runtime check is None (unknown), not a pass.
    result = compare_budget({"tracemalloc_peak_bytes": 100, "disk_bytes": None,
                             "runtime_best_s": 0.01, "rss_after_bytes": None},
                            ResourceBudgets(memory_bytes=1000))
    assert result["checks"]["disk_within_budget"] is None       # no budget
    assert result["checks"]["rss_within_budget"] is None
    # disk metric missing but budget set -> unknown (None), never a pass.
    result2 = compare_budget({"tracemalloc_peak_bytes": 100, "disk_bytes": None},
                             ResourceBudgets(disk_bytes=1000))
    assert result2["checks"]["disk_within_budget"] is None


def test_measure_reports_null_for_unavailable(monkeypatch):
    import tools.benchmarking.research_cycle_benchmarks.telemetry as T
    monkeypatch.setattr(T, "_PSUTIL", None)
    monkeypatch.setattr(sys, "platform", "darwin")  # no /proc fallback path
    out = T.measure(lambda: {"checksum": "abc"}, repetitions=1)
    assert out["rss_after_bytes"] is None            # null, never fabricated/zero


# --------------------------------------------------------------------------- #
# Checksum mismatch + malformed record
# --------------------------------------------------------------------------- #
def test_checksum_mismatch():
    base = TARGETS["research_plan_audit"]
    broken = TargetSpec(
        name="mismatch", make_fixture=base.make_fixture, baseline=base.baseline,
        candidate=lambda fx: {"checksum": "deadbeef", "feature_count": 0},
    )
    rec = run_target(broken, ResourceBudgets(), seed=0, size=50, repetitions=1)
    assert rec["status"] == "checksum_mismatch"
    assert rec["deterministic"]["checksum_match"] is False


def test_malformed_record():
    base = TARGETS["research_plan_audit"]
    malformed = TargetSpec(
        name="malformed", make_fixture=base.make_fixture, baseline=base.baseline,
        candidate=lambda fx: {"feature_count": 0},  # missing 'checksum'
    )
    rec = run_target(malformed, ResourceBudgets(), seed=0, size=50, repetitions=1)
    assert rec["status"] == "malformed_record"


def test_target_exception_is_error():
    base = TARGETS["research_plan_audit"]
    boom = TargetSpec(
        name="boom", make_fixture=base.make_fixture, baseline=base.baseline,
        candidate=lambda fx: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    rec = run_target(boom, ResourceBudgets(), seed=0, size=50, repetitions=1)
    assert rec["status"] == "error"


# --------------------------------------------------------------------------- #
# Timeout + child isolation + bounded workers
# --------------------------------------------------------------------------- #
def test_child_timeout():
    res = execute_child([sys.executable, "-c", "import time; time.sleep(60)"], timeout_s=1.0)
    assert res.timed_out is True
    assert res.exit_code != 0
    assert res.elapsed_s < 20


def test_child_success_and_isolated_cli(capsys):
    rc = cli.main(["--isolated", "--size", "60", "--repetitions", "1",
                   "--per-target-timeout-s", "30", "--json"])
    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["mode"] == "isolated"
    assert report["config"]["max_workers"] == 1          # bounded worker count
    assert report["num_targets"] == len(TARGETS)
    assert rc in (0, 1)


def test_bounded_worker_count_in_report():
    report = run_all(seed=0, size=50, repetitions=1)
    assert report["config"]["max_workers"] == 1


# --------------------------------------------------------------------------- #
# Finite JSON + schema + no-network
# --------------------------------------------------------------------------- #
def test_finite_json():
    report = run_all(seed=0, size=80, repetitions=1)
    text = json.dumps(report, allow_nan=False)           # raises on NaN/Inf
    assert "NaN" not in text and "Infinity" not in text
    _assert_finite(json.loads(text))
    assert json_safe(float("nan")) is None and json_safe(float("inf")) is None


def test_schema_versioned():
    report = run_all(seed=0, size=50, repetitions=1)
    assert report["schema"] == SCHEMA_VERSION == "research_cycle_benchmarks/v1"
    assert report["evidence_class"] == "performance_only"
    assert report["synthetic"] is True


def test_no_network_execution():
    # The repo conftest network guard is active in this process; a full run must
    # complete without any network access and reference no network dependency.
    report = run_all(seed=0, size=80, repetitions=1)
    assert report["num_targets"] == len(TARGETS)
    assert "network" not in json.dumps(report).lower()


def test_dumps_is_deterministic_for_deterministic_fields():
    a = run_all(seed=1, size=64, repetitions=1)
    b = run_all(seed=1, size=64, repetitions=1)
    # Deterministic sub-structures must match exactly across runs.
    da = [r["deterministic"] for r in a["results"]]
    db = [r["deterministic"] for r in b["results"]]
    assert da == db
