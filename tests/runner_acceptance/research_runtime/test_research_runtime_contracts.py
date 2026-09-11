"""Tests for research runtime contracts, finite JSON serialization, and fixtures."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from tools.runner_acceptance.research_runtime.contracts import (
    AcceptanceReport,
    AcceptanceScenarioResult,
    AtomicWriteSpec,
    BoundedChunkCachePlan,
    CacheEvictionPlan,
    FailureClassification,
    PlatformStatus,
    ResumableTransferMetadata,
    ScenarioOutcome,
    SimulationCheckpointSpec,
    dumps_finite_json,
    json_safe,
)
from tools.runner_acceptance.research_runtime.fixtures import (
    build_chunk_cache_plan_fixture,
    build_simulation_checkpoint_fixture,
    execute_atomic_write_fixture,
    probe_production_chunk_cache,
    probe_production_simulation_runner,
    simulate_cache_eviction_fixture,
    simulate_resumable_transfer_fixture,
)


def test_json_safe_and_finite_dumps() -> None:
    """Verifies that non-finite floats are converted to null and JSON is valid."""
    data = {
        "val": 10.5,
        "nan": float("nan"),
        "pos_inf": float("inf"),
        "neg_inf": float("-inf"),
        "nested": [1, float("nan"), {"sub": float("inf")}],
        "enum": ScenarioOutcome.PASS,
    }
    dumped = dumps_finite_json(data)
    loaded = json.loads(dumped)

    assert loaded["val"] == 10.5
    assert loaded["nan"] is None
    assert loaded["pos_inf"] is None
    assert loaded["neg_inf"] is None
    assert loaded["nested"][1] is None
    assert loaded["nested"][2]["sub"] is None
    assert loaded["enum"] == "PASS"


def test_chunk_cache_plan_contract() -> None:
    """Verifies BoundedChunkCachePlan contract generation and calculation."""
    plan = build_chunk_cache_plan_fixture(
        total_bytes=10 * 1024 * 1024,
        chunk_size_bytes=2 * 1024 * 1024,
        budget_bytes=6 * 1024 * 1024,
    )
    d = plan.to_dict()
    assert d["schema_version"] == "ResearchRuntime.ChunkCachePlan.v1"
    assert d["chunk_count"] == 5
    assert len(d["planned_chunks"]) == 5
    assert d["planned_chunks"][0]["byte_length"] == 2 * 1024 * 1024


def test_resumable_transfer_fixture(tmp_path: Path) -> None:
    """Verifies multi-chunk resumable transfer simulation and SHA-256 integrity."""
    meta = simulate_resumable_transfer_fixture(tmp_path, num_chunks=4, chunk_size=1024)
    d = meta.to_dict()
    assert d["schema_version"] == "ResearchRuntime.ResumableTransfer.v1"
    assert d["is_complete"] is True
    assert d["transferred_bytes"] == 4096
    assert len(d["completed_chunks"]) == 4
    assert len(d["checksum_sha256"]) == 64


def test_cache_eviction_fixture(tmp_path: Path) -> None:
    """Verifies LRU eviction planning when cache exceeds budget."""
    evict_plan = simulate_cache_eviction_fixture(
        cache_dir=tmp_path / "cache",
        file_sizes_bytes=[1000, 2000, 3000],
        budget_limit_bytes=3500,
    )
    d = evict_plan.to_dict()
    assert d["schema_version"] == "ResearchRuntime.CacheEviction.v1"
    assert d["current_size_bytes"] == 6000
    assert d["target_freed_bytes"] == 2500
    assert len(d["evicted_keys"]) >= 2
    assert d["resulting_size_bytes"] <= 3500


def test_atomic_write_fixture(tmp_path: Path) -> None:
    """Verifies atomic write staging and replacement."""
    target = tmp_path / "atomic.bin"
    payload = b"TEST_ATOMIC_PAYLOAD_12345"
    spec = execute_atomic_write_fixture(target, payload)

    d = spec.to_dict()
    assert d["schema_version"] == "ResearchRuntime.AtomicWrite.v1"
    assert d["replace_success"] is True
    assert target.exists()
    assert target.read_bytes() == payload
    assert len(d["checksum_sha256"]) == 64


def test_simulation_checkpoint_fixture(tmp_path: Path) -> None:
    """Verifies simulation checkpoint serialization and recovery hash."""
    ckpt = build_simulation_checkpoint_fixture(tmp_path, step_index=25, total_steps=100)
    d = ckpt.to_dict()
    assert d["schema_version"] == "ResearchRuntime.SimulationCheckpoint.v1"
    assert d["step_index"] == 25
    assert d["is_recoverable"] is True
    assert Path(d["checkpoint_file"]).exists()


def test_production_probes() -> None:
    """Verifies that production probes return boolean and informative string."""
    has_cache, msg_cache = probe_production_chunk_cache()
    assert isinstance(has_cache, bool)
    assert isinstance(msg_cache, str)

    has_sim, msg_sim = probe_production_simulation_runner()
    assert isinstance(has_sim, bool)
    assert isinstance(msg_sim, str)
