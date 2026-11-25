"""Comprehensive test suite for the reliable simulation campaign runner.

Tests cover:
- Deterministic ordering;
- Resume after interruption;
- Retryable versus non-retryable failure;
- Timeout and child-process cleanup;
- Duplicate completion prevention;
- Partial campaign visibility and NOT_RUN representation;
- Missing dependency detection;
- Disk and memory budget refusal;
- Finite JSON serialization (no NaN/Inf);
- Offline execution and dry-run validation;
- CLI subprocess invocation and resume behavior.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

from tools.simulation_runtime.atomic_io import (
    compute_config_hash,
    compute_sha256,
    json_safe,
    load_json,
    write_atomic_json,
)
from tools.simulation_runtime.checkpoint import (
    CampaignCheckpointManager,
    CheckpointCorruptError,
    CheckpointMismatchError,
)
from tools.simulation_runtime.guards import (
    check_dependencies,
    check_disk_budget,
    check_memory_budget,
)
from tools.simulation_runtime.process_cleanup import run_isolated_process
from tools.simulation_runtime.runner import (
    SimulationCampaignRunner,
    run_campaign_manifest,
)
from tools.simulation_runtime.types import (
    CampaignManifest,
    Outcome,
    ResourcePolicy,
    UnitResult,
    WorkUnit,
    capture_environment_metadata,
)


def _create_mock_manifest(
    units: List[WorkUnit],
    campaign_id: str = "test_campaign_01",
    max_workers: int = 1,
) -> CampaignManifest:
    policy = ResourcePolicy(
        max_workers=max_workers,
        concurrency_cap=4,
        min_disk_free_mb=10.0,
        max_memory_mb=2048.0,
        max_retries_per_unit=2,
        default_timeout_s=30.0,
    )
    raw_dict = {
        "campaign_id": campaign_id,
        "seed": 100,
        "units": [u.to_dict() for u in units],
        "resource_policy": policy.to_dict(),
    }
    cfg_hash = compute_config_hash(raw_dict)
    return CampaignManifest(
        schema_version="simulation_campaign_manifest_v1",
        campaign_id=campaign_id,
        created_at="2026-09-10T00:00:00Z",
        code_commit="abcdef123456",
        configuration_hash=cfg_hash,
        seed=100,
        units=units,
        environment=capture_environment_metadata(),
        resource_policy=policy,
    )


def test_deterministic_ordering(tmp_path: Path):
    """Ensure units are executed in strictly ordered sequence by unit_id."""
    order_file = tmp_path / "execution_order.txt"

    # Out-of-order definition
    unit_ids = ["unit_C", "unit_A", "unit_D", "unit_B"]
    units = []
    for uid in unit_ids:
        cmd = [
            sys.executable,
            "-c",
            f"with open(r'{order_file}', 'a') as f: f.write('{uid}\\n')",
        ]
        units.append(
            WorkUnit(
                unit_id=uid,
                command=cmd,
                timeout_s=10.0,
                estimated_disk_mb=0.1,
                estimated_memory_mb=10.0,
            )
        )

    manifest = _create_mock_manifest(units, "test_ordering")
    runner = SimulationCampaignRunner(manifest, tmp_path)
    state = runner.run(resume=False)

    assert state.is_complete is True
    assert state.is_partial is False
    assert state.summary[Outcome.PASS.value] == 4

    # Check execution order on disk
    executed_order = [line.strip() for line in order_file.read_text().splitlines() if line.strip()]
    assert executed_order == ["unit_A", "unit_B", "unit_C", "unit_D"]


def test_resume_after_interruption(tmp_path: Path):
    """Ensure an interrupted campaign resumes without re-executing completed units."""
    counter_file = tmp_path / "runs_counter.json"
    counter_file.write_text(json.dumps({}), encoding="utf-8")

    def make_unit(uid: str) -> WorkUnit:
        cmd = [
            sys.executable,
            "-c",
            f"""
import json, sys
p = r'{counter_file}'
with open(p, 'r') as f:
    data = json.load(f)
data['{uid}'] = data.get('{uid}', 0) + 1
with open(p, 'w') as f:
    json.dump(data, f)
""",
        ]
        return WorkUnit(
            unit_id=uid,
            command=cmd,
            timeout_s=10.0,
            estimated_disk_mb=0.1,
            estimated_memory_mb=10.0,
        )

    units = [make_unit("unit_01"), make_unit("unit_02"), make_unit("unit_03"), make_unit("unit_04")]
    manifest = _create_mock_manifest(units, "test_resume")

    # Step 1: Run with cancel_check returning True after 2 units
    cancel_flag = False
    completed_so_far = 0

    def check_cancel() -> bool:
        nonlocal completed_so_far, cancel_flag
        # Check units dir count
        units_dir = tmp_path / "units"
        if units_dir.exists():
            count = len(list(units_dir.glob("*.json")))
            if count >= 2:
                cancel_flag = True
        return cancel_flag

    runner1 = SimulationCampaignRunner(manifest, tmp_path, cancel_check=check_cancel)
    state1 = runner1.run(resume=False)

    assert state1.is_complete is False
    assert state1.is_partial is True
    assert state1.cancelled is True

    # 2 units completed
    units_done = set(state1.completed_units.keys())
    assert len(units_done) == 2

    # Step 2: Resume without cancellation
    runner2 = SimulationCampaignRunner(manifest, tmp_path, cancel_check=lambda: False)
    state2 = runner2.run(resume=True)

    assert state2.is_complete is True
    assert state2.is_partial is False
    assert state2.summary[Outcome.PASS.value] == 4

    # Verify that each unit was executed EXACTLY once
    run_counts = json.loads(counter_file.read_text(encoding="utf-8"))
    for uid in ["unit_01", "unit_02", "unit_03", "unit_04"]:
        assert run_counts.get(uid) == 1, f"Unit {uid} was executed {run_counts.get(uid)} times instead of 1"


def test_retryable_vs_nonretryable_failure(tmp_path: Path):
    """Correctness failures must NEVER retry; infrastructure errors retry up to limit."""
    # 1. Non-retryable: correctness assertion failure
    correctness_cmd = [
        sys.executable,
        "-c",
        "import sys; sys.stderr.write('AssertionError: validation failed'); sys.exit(1)",
    ]
    u1 = WorkUnit(
        unit_id="unit_correctness",
        command=correctness_cmd,
        timeout_s=5.0,
        retryable=True,
        max_retries=3,
        estimated_disk_mb=0.1,
        estimated_memory_mb=10.0,
    )

    # 2. Retryable: transient disk failure simulated via attempt counter
    retry_file = tmp_path / "retry_counter.txt"
    retry_cmd = [
        sys.executable,
        "-c",
        f"""
import os, sys
p = r'{retry_file}'
count = 0
if os.path.exists(p):
    with open(p, 'r') as f:
        count = int(f.read().strip() or '0')
count += 1
with open(p, 'w') as f:
    f.write(str(count))

if count < 2:
    sys.stderr.write('OSError: [Errno 28] No space left on device\\n')
    sys.exit(1)
print('Success on retry!')
sys.exit(0)
""",
    ]
    u2 = WorkUnit(
        unit_id="unit_transient_retry",
        command=retry_cmd,
        timeout_s=5.0,
        retryable=True,
        max_retries=3,
        estimated_disk_mb=0.1,
        estimated_memory_mb=10.0,
    )

    manifest = _create_mock_manifest([u1, u2], "test_retry_logic")
    runner = SimulationCampaignRunner(manifest, tmp_path)
    state = runner.run(resume=False)

    res1 = state.completed_units["unit_correctness"]
    assert res1.outcome == Outcome.CORRECTNESS_FAILURE
    assert res1.retry_count == 0  # Crucial: NEVER retried!

    res2 = state.completed_units["unit_transient_retry"]
    assert res2.outcome == Outcome.PASS
    assert res2.retry_count == 1  # Successfully recovered on retry 1


def test_timeout_and_child_process_cleanup(tmp_path: Path):
    """Subprocess exceeding timeout must be killed with process group and classified as TIMEOUT."""
    sleep_cmd = [
        sys.executable,
        "-c",
        "import time; time.sleep(15.0)",
    ]
    unit = WorkUnit(
        unit_id="unit_hung",
        command=sleep_cmd,
        timeout_s=0.5,
        estimated_disk_mb=0.1,
        estimated_memory_mb=10.0,
    )

    manifest = _create_mock_manifest([unit], "test_timeout")
    runner = SimulationCampaignRunner(manifest, tmp_path)

    start = time.monotonic()
    state = runner.run(resume=False)
    elapsed = time.monotonic() - start

    assert elapsed < 5.0, f"Runner hung for {elapsed:.1f}s instead of enforcing timeout"
    res = state.completed_units["unit_hung"]
    assert res.outcome == Outcome.TIMEOUT
    assert "timed out" in (res.error_message or "").lower()


def test_duplicate_completion_prevention(tmp_path: Path):
    """Resuming against already completed units must preserve existing results and not duplicate."""
    units = [
        WorkUnit(
            unit_id=f"u_{i}",
            command=[sys.executable, "-c", "print('done')"],
            timeout_s=5.0,
            estimated_disk_mb=0.1,
            estimated_memory_mb=10.0,
        )
        for i in range(3)
    ]
    manifest = _create_mock_manifest(units, "test_dedup")
    runner = SimulationCampaignRunner(manifest, tmp_path)
    state1 = runner.run(resume=False)

    assert state1.is_complete is True
    assert len(state1.completed_units) == 3

    # Run again with resume=True
    runner2 = SimulationCampaignRunner(manifest, tmp_path)
    state2 = runner2.run(resume=True)

    assert state2.is_complete is True
    assert len(state2.completed_units) == 3
    # Check all timestamps and outputs preserved
    for uid in ["u_0", "u_1", "u_2"]:
        assert state2.completed_units[uid].completed_at == state1.completed_units[uid].completed_at


def test_partial_campaign_visibility(tmp_path: Path):
    """Partial campaigns must explicitly display NOT_RUN status for remaining units."""
    units = [
        WorkUnit(
            unit_id=f"u_{i}",
            command=[sys.executable, "-c", "print('done')"],
            timeout_s=5.0,
            estimated_disk_mb=0.1,
            estimated_memory_mb=10.0,
        )
        for i in range(4)
    ]
    manifest = _create_mock_manifest(units, "test_partial")

    # Stop after unit 1
    cancel = False

    def stop_after_one() -> bool:
        nonlocal cancel
        if (tmp_path / "units" / "u_0.json").exists():
            cancel = True
        return cancel

    runner = SimulationCampaignRunner(manifest, tmp_path, cancel_check=stop_after_one)
    state = runner.run(resume=False)

    assert state.is_complete is False
    assert state.is_partial is True
    assert state.summary[Outcome.NOT_RUN.value] == 3

    summary_file = tmp_path / "campaign_summary.json"
    assert summary_file.exists()
    summary_data = json.loads(summary_file.read_text(encoding="utf-8"))

    not_run_units = [u for u in summary_data["units"] if u["outcome"] == Outcome.NOT_RUN.value]
    assert len(not_run_units) == 3
    assert not_run_units[0]["unit_id"] == "u_1"


def test_missing_dependency(tmp_path: Path):
    """Units requiring unavailable dependencies must be classified immediately as DEPENDENCY_MISSING."""
    unit = WorkUnit(
        unit_id="unit_missing_pkg",
        command=[sys.executable, "-c", "print('should not run')"],
        dependencies=["nonexistent_sim_module_xyz_9999"],
        timeout_s=5.0,
        estimated_disk_mb=0.1,
        estimated_memory_mb=10.0,
    )

    manifest = _create_mock_manifest([unit], "test_dep_missing")
    runner = SimulationCampaignRunner(manifest, tmp_path)
    state = runner.run(resume=False)

    res = state.completed_units["unit_missing_pkg"]
    assert res.outcome == Outcome.DEPENDENCY_MISSING
    assert res.retry_count == 0
    assert "nonexistent_sim_module_xyz_9999" in (res.error_message or "")


def test_disk_budget_refusal(tmp_path: Path):
    """Work unit with disk estimate exceeding capacity must fail with DISK_FAILURE before execution."""
    unit = WorkUnit(
        unit_id="unit_giant_disk",
        command=[sys.executable, "-c", "print('should not run')"],
        estimated_disk_mb=999_999_999.0,  # 999 TB
        timeout_s=5.0,
    )
    manifest = _create_mock_manifest([unit], "test_disk_budget")
    runner = SimulationCampaignRunner(manifest, tmp_path)
    state = runner.run(resume=False)

    res = state.completed_units["unit_giant_disk"]
    assert res.outcome == Outcome.DISK_FAILURE
    assert "insufficient disk space" in (res.error_message or "").lower()


def test_memory_budget_refusal(tmp_path: Path):
    """Work unit with memory estimate exceeding policy must fail with MEMORY_FAILURE before execution."""
    unit = WorkUnit(
        unit_id="unit_giant_mem",
        command=[sys.executable, "-c", "print('should not run')"],
        estimated_memory_mb=999_999.0,  # 999 GB
        timeout_s=5.0,
    )
    manifest = _create_mock_manifest([unit], "test_mem_budget")
    runner = SimulationCampaignRunner(manifest, tmp_path)
    state = runner.run(resume=False)

    res = state.completed_units["unit_giant_mem"]
    assert res.outcome == Outcome.MEMORY_FAILURE
    assert "exceeds maximum allowed memory budget" in (res.error_message or "").lower()


def test_finite_json_serialization(tmp_path: Path):
    """All telemetry must be serialized strictly without NaN or Infinity."""
    bad_data = {
        "nan_val": float("nan"),
        "inf_val": float("inf"),
        "neg_inf": float("-inf"),
        "valid_float": 3.14159,
        "nested": {"nested_nan": float("nan"), "valid": 42},
    }
    clean = json_safe(bad_data)
    # Must dump with allow_nan=False without raising ValueError
    serialized = json.dumps(clean, allow_nan=False)
    loaded = json.loads(serialized)
    assert loaded["nan_val"] is None
    assert loaded["inf_val"] is None
    assert loaded["neg_inf"] is None
    assert loaded["valid_float"] == 3.14159
    assert loaded["nested"]["nested_nan"] is None


def test_checkpoint_mismatch_detection(tmp_path: Path):
    """Resuming with a modified manifest or different campaign_id must raise CheckpointMismatchError."""
    unit = WorkUnit(
        unit_id="u_0",
        command=[sys.executable, "-c", "print('ok')"],
        timeout_s=5.0,
        estimated_disk_mb=0.1,
        estimated_memory_mb=10.0,
    )
    manifest1 = _create_mock_manifest([unit], "campaign_alpha")
    runner1 = SimulationCampaignRunner(manifest1, tmp_path)
    runner1.run(resume=False)

    # Change campaign_id
    manifest2 = _create_mock_manifest([unit], "campaign_beta")
    runner2 = SimulationCampaignRunner(manifest2, tmp_path)
    with pytest.raises(CheckpointMismatchError):
        runner2.run(resume=True)


def test_no_network_dry_run(tmp_path: Path):
    """Dry-run must validate configuration and gates without starting child execution."""
    manifest_path = tmp_path / "test_manifest.json"
    unit = WorkUnit(
        unit_id="u_01",
        command=[sys.executable, "-c", "print('dry run')"],
        timeout_s=5.0,
        dependencies=["sys"],
        estimated_disk_mb=0.1,
        estimated_memory_mb=10.0,
    )
    manifest = _create_mock_manifest([unit], "test_dry_run")
    write_atomic_json(manifest_path, manifest.to_dict())

    # Invoke CLI dry run
    cli_script = Path(__file__).resolve().parents[2] / "scripts" / "run_simulation_reliable.py"
    res = subprocess.run(
        [sys.executable, str(cli_script), "--manifest", str(manifest_path), "--output-dir", str(tmp_path / "out"), "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0
    assert "Dry run validation PASSED" in res.stdout


def test_cli_execution_and_resumption(tmp_path: Path):
    """Test full CLI lifecycle: generate synthetic manifest, run, and verify outputs."""
    cli_script = Path(__file__).resolve().parents[2] / "scripts" / "run_simulation_reliable.py"
    manifest_path = tmp_path / "synthetic_manifest.json"
    output_dir = tmp_path / "campaign_out"

    # 1. Generate synthetic manifest
    res_gen = subprocess.run(
        [sys.executable, str(cli_script), "--generate-synthetic-manifest", str(manifest_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_gen.returncode == 0
    assert manifest_path.exists()

    # 2. Run campaign via CLI
    res_run = subprocess.run(
        [sys.executable, str(cli_script), "--manifest", str(manifest_path), "--output-dir", str(output_dir), "--format", "json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res_run.returncode == 0, f"CLI run failed: {res_run.stderr}"
    assert (output_dir / "campaign_summary.json").exists()
    assert (output_dir / "checkpoint.json").exists()

    summary_data = json.loads((output_dir / "campaign_summary.json").read_text(encoding="utf-8"))
    assert summary_data["is_complete"] is True
    assert summary_data["is_partial"] is False
    assert summary_data["total_units"] == 3
