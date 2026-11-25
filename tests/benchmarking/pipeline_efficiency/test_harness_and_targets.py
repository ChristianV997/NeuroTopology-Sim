"""Deterministic fixtures, target equivalence, and finite reports."""
from __future__ import annotations

import json
import math

import pytest

from tools.benchmarking.pipeline_efficiency.adapters import probe_all
from tools.benchmarking.pipeline_efficiency.budgets import ResourceBudgets
from tools.benchmarking.pipeline_efficiency.fixtures import make_fixture
from tools.benchmarking.pipeline_efficiency.harness import SCHEMA_VERSION, run_all, run_target
from tools.benchmarking.pipeline_efficiency.schema import EVIDENCE_CLASS, TARGET_NAMES
from tools.benchmarking.pipeline_efficiency.telemetry import dumps, json_safe
from tools.benchmarking.pipeline_efficiency.workloads import TARGETS


def _assert_finite(obj):
    if isinstance(obj, float):
        assert math.isfinite(obj)
    elif isinstance(obj, dict):
        for value in obj.values():
            _assert_finite(value)
    elif isinstance(obj, list):
        for value in obj:
            _assert_finite(value)


@pytest.mark.parametrize("target", sorted(TARGETS.keys()))
def test_deterministic_fixture(target):
    a = make_fixture(target, seed=7, size=16)
    b = make_fixture(target, seed=7, size=16)
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


@pytest.mark.parametrize("target", sorted(TARGETS.keys()))
def test_baseline_candidate_equivalent(target):
    rec = run_target(TARGETS[target], ResourceBudgets(), seed=0, size=12, repetitions=1)
    assert rec["status"] in {"ok", "budget_overrun"}
    assert rec["deterministic"]["checksum_match"] is True
    assert rec["evidence_class"] == EVIDENCE_CLASS
    assert rec["synthetic"] is True


def test_target_set_matches_contract():
    assert set(TARGETS) == set(TARGET_NAMES)
    assert len(TARGETS) == 8


def test_deterministic_checksums_stable_across_runs():
    r1 = run_all(seed=0, size=12, repetitions=1)
    r2 = run_all(seed=0, size=12, repetitions=1)
    d1 = [
        (r["target"], r["deterministic"]["checksum_baseline"], r["deterministic"]["checksum_candidate"])
        for r in r1["results"]
    ]
    d2 = [
        (r["target"], r["deterministic"]["checksum_baseline"], r["deterministic"]["checksum_candidate"])
        for r in r2["results"]
    ]
    assert d1 == d2
    assert r1["all_equivalent"] is True
    assert r2["all_equivalent"] is True


def test_finite_json():
    report = run_all(seed=0, size=10, repetitions=1)
    text = json.dumps(report, allow_nan=False)
    assert "NaN" not in text and "Infinity" not in text
    _assert_finite(json.loads(text))
    assert json_safe(float("nan")) is None and json_safe(float("inf")) is None
    dumps(report)  # allow_nan=False


def test_schema_and_worker_bound():
    report = run_all(seed=0, size=8, repetitions=1)
    assert report["schema"] == SCHEMA_VERSION == "pipeline_efficiency/v1"
    assert report["evidence_class"] == EVIDENCE_CLASS
    assert report["config"]["max_workers"] == 1
    assert report["num_targets"] == 8
    assert "bottleneck_ranking" in report


def test_production_probe_is_local():
    probe = probe_all()
    assert probe["network_used"] is False
    assert probe["remote_data_accessed"] is False
    assert probe["blocked_imports"] == 0
    blob = json.dumps(probe).lower()
    assert "openneuro.org" not in blob
    assert "amazonaws.com" not in blob


def test_input_size_and_null_metrics_shape():
    rec = run_target(TARGETS["checkpoint_recovery_planning"], ResourceBudgets(), seed=0, size=10, repetitions=1)
    assert rec["deterministic"]["input_size"]["n_items"] == 10
    assert rec["telemetry"]["candidate"]["disk_bytes"] is None
    assert rec["telemetry"]["worker_count"] == 1
    rss = rec["telemetry"]["candidate"]["rss_after_bytes"]
    assert rss is None or rss > 0
