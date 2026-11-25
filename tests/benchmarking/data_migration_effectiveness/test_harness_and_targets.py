"""Deterministic fixtures, target coverage, checksum equivalence, finite JSON."""
from __future__ import annotations

import json
import math

import pytest

from tools.benchmarking.data_migration_effectiveness.budgets import ResourceBudgets
from tools.benchmarking.data_migration_effectiveness.fixtures import make_fixture
from tools.benchmarking.data_migration_effectiveness.harness import run_all, run_target
from tools.benchmarking.data_migration_effectiveness.schema import (
    EVIDENCE_CLASS,
    SCHEMA_VERSION,
    TARGET_NAMES,
)
from tools.benchmarking.data_migration_effectiveness.telemetry import dumps, json_safe
from tools.benchmarking.data_migration_effectiveness.workloads import TARGETS


ENGINEERING_OK = {"ok", "timeout", "rejected", "budget_overrun"}


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
    a = make_fixture(seed=7, size=16)
    b = make_fixture(seed=7, size=16)
    skip = {"payload", "extra_payload"}
    da = {k: v for k, v in a.items() if k not in skip}
    db = {k: v for k, v in b.items() if k not in skip}
    assert json.dumps(da, sort_keys=True, default=str) == json.dumps(db, sort_keys=True, default=str)
    assert a["payload"] == b["payload"]
    assert a["payload_sha256"] == b["payload_sha256"]


@pytest.mark.parametrize("target", sorted(TARGETS.keys()))
def test_baseline_candidate_checksum_match(target):
    rec = run_target(target, ResourceBudgets(), seed=0, size=32, repetitions=1)
    assert rec["deterministic"]["checksum_match"] is True
    assert rec["status"] in ENGINEERING_OK
    assert rec["evidence_class"] == EVIDENCE_CLASS
    assert rec["synthetic"] is True
    assert rec["scientific_improvement_claimed"] is False


def test_target_set_matches_contract():
    assert set(TARGETS) == set(TARGET_NAMES)
    assert len(TARGETS) == 10


def test_deterministic_checksums_stable_across_runs():
    r1 = run_all(seed=0, size=32, repetitions=1)
    r2 = run_all(seed=0, size=32, repetitions=1)
    d1 = [
        (r["target"], r["deterministic"]["checksum_baseline"], r["deterministic"]["checksum_candidate"])
        for r in r1["results"]
    ]
    d2 = [
        (r["target"], r["deterministic"]["checksum_baseline"], r["deterministic"]["checksum_candidate"])
        for r in r2["results"]
    ]
    assert d1 == d2
    assert r1["all_checksums_match"] is True
    assert r2["all_checksums_match"] is True


def test_finite_json():
    report = run_all(seed=0, size=32, repetitions=1)
    text = json.dumps(report, allow_nan=False)
    assert "NaN" not in text and "Infinity" not in text
    _assert_finite(json.loads(text))
    assert json_safe(float("nan")) is None and json_safe(float("inf")) is None
    dumps(report)


def test_schema_and_worker_bound():
    report = run_all(seed=0, size=32, repetitions=1)
    assert report["schema"] == SCHEMA_VERSION == "data_migration_effectiveness/v1"
    assert report["evidence_class"] == EVIDENCE_CLASS
    assert report["config"]["max_workers"] == 1
    assert report["scientific_improvement_claimed"] is False
    assert report["network_accessed"] is False
    assert report["full_dataset_download"] is False
    assert set(r["target"] for r in report["results"]) == set(TARGET_NAMES)


def test_correctness_separated_from_telemetry():
    rec = run_target("planning_latency", ResourceBudgets(), seed=0, size=32, repetitions=1)
    assert "checksum_match" in rec["deterministic"]
    assert "runtime_best_s" in rec["telemetry"]["candidate"]
    assert rec["measurement_quality"]["correctness_separated_from_performance"] is True


def test_bounded_vs_rejected_records_policy_reject():
    rec = run_target("bounded_vs_rejected_full_object", ResourceBudgets(), seed=0, size=32, repetitions=1)
    assert rec["deterministic"]["checksum_match"] is True
    assert rec["deterministic"]["rejected_full_object"] is True
    assert rec["deterministic"]["correctness_baseline"]["rejected"] is True
    assert rec["deterministic"]["correctness_baseline"]["policy"] == "reject"
    occupancy = rec["telemetry"]["candidate"]["cache_occupancy_bytes"]
    assert occupancy is None or occupancy >= 0
    # Baseline reject is a no-op: occupancy/disk stay null, not fabricated zeros.
    assert rec["telemetry"]["baseline"]["cache_occupancy_bytes"] is None
    assert rec["telemetry"]["baseline"]["disk_bytes"] is None
    assert rec["telemetry"]["baseline"]["retry_attempts"] is None
