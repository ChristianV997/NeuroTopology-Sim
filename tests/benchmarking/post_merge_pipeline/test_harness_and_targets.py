"""Deterministic fixtures, target equivalence, and finite reports."""
from __future__ import annotations

import json
import math

import pytest

from tools.benchmarking.post_merge_pipeline.adapters import probe_all
from tools.benchmarking.pipeline_efficiency.budgets import ResourceBudgets
from tools.benchmarking.post_merge_pipeline.fixtures import make_fixture
from tools.benchmarking.post_merge_pipeline.harness import SCHEMA_VERSION, run_all, run_target
from tools.benchmarking.post_merge_pipeline.schema import EVIDENCE_CLASS, TARGET_NAMES
from tools.benchmarking.pipeline_efficiency.telemetry import dumps, json_safe
from tools.benchmarking.post_merge_pipeline.workloads import TARGETS


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
    a = make_fixture(target, seed=7, size=8)
    b = make_fixture(target, seed=7, size=8)
    assert json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


@pytest.mark.parametrize("target", sorted(TARGETS.keys()))
def test_baseline_candidate_equivalent(target):
    rec = run_target(TARGETS[target], ResourceBudgets(), seed=0, size=8, repetitions=1)
    assert rec["status"] in {"ok", "budget_overrun"}, rec
    assert rec["deterministic"]["checksum_match"] is True, rec
    assert rec["evidence_class"] == EVIDENCE_CLASS
    assert rec["synthetic"] is True
    assert rec["telemetry"]["worker_count"] == 1


def test_run_all_eight_targets():
    report = run_all(seed=0, size=8, repetitions=1)
    assert report["schema"] == SCHEMA_VERSION
    assert report["num_targets"] == len(TARGET_NAMES)
    assert report["all_equivalent"] is True
    assert report["config"]["max_workers"] == 1
    assert report["evidence_class"] == EVIDENCE_CLASS
    assert report["synthetic"] is True
    names = {row["target"] for row in report["results"]}
    assert names == set(TARGET_NAMES)
    _assert_finite(json.loads(dumps(report)))
    blob = json_safe(report)
    assert blob["production_probe"]["network_used"] is False
    assert blob["streaming_baseline_comparison"]["synthetic"] is True


def test_probe_does_not_import_awareness():
    probe = probe_all()
    assert probe["blocked_imports"] == 0
    assert probe["remote_data_accessed"] is False
