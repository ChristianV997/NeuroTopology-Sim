"""Comprehensive test fixtures for Simulation Release Bridge.

Provides pre-configured stage dictionaries and directory builders for:
- Complete PASS run (empirical)
- Partial run (PARTIAL, interrupted/resumable)
- Failed run (FAILED, solver divergence/error)
- Timeout run (TIMEOUT)
- Missing validation run (complete execution but no validation stage)
- Synthetic-only run (synthetic data mode)
- Proxy-only run (proxy data mode)
- Fabricated provenance run (placeholder run_id / unknown source / null seed)
- Incomplete manifest run (missing RunRecord.json or summary/metrics)
- Non-finite metrics run (contains NaN or Inf)
- Output-root escape run (contains path traversal or absolute path)
- Temporary-only artifacts run (contains only scratch tmp files)
- Blocked run (BLOCKED)
- Not implemented run (NOT_IMPLEMENTED)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import (
    ExecutionOutcomeState,
    canonical_hash,
    dumps_finite_json,
)


def create_complete_pass_stages() -> dict[str, Any]:
    """Return an 8-stage dictionary for a fully compliant PASS empirical run."""
    return {
        "input_provenance": {
            "run_id": "run_pass_001",
            "dataset_id": "ds005620",
            "source": "openneuro/ds005620",
            "data_mode": "empirical",
            "input_references": ["sub-01/eeg/sub-01_task-rest_eeg.set"],
            "description": "Empirical EEG recording from OpenNeuro ds005620",
        },
        "configuration": {
            "parameters": {"n_nodes": 64, "dt": 0.001, "filter_band": [8, 12]},
            "argv": ["python", "run_pipeline.py", "--dataset", "ds005620"],
            "spec_id": "SPEC-EMPIRICAL-001",
            "timeout_s": 300.0,
        },
        "code_revision": {
            "code_revision": "ed3a6f03806785ed724ef501a4aa0f41b932e805",
            "repo": "NeuroTopology-Sim",
            "clean_working_tree": True,
        },
        "seed": {
            "seed": 42,
            "deterministic_fixed": True,
        },
        "execution_outcome": {
            "state": ExecutionOutcomeState.PASS.value,
            "exit_code": 0,
            "elapsed_s": 12.45,
            "error_message": None,
            "runner_id": "bounded_runner",
        },
        "artifact_manifest": {
            "artifacts": [
                {
                    "relative_path": "RunRecord.json",
                    "sha256": "1111111111111111111111111111111111111111111111111111111111111111",
                    "size_bytes": 1024,
                    "role": "run_record",
                },
                {
                    "relative_path": "summary.json",
                    "sha256": "2222222222222222222222222222222222222222222222222222222222222222",
                    "size_bytes": 2048,
                    "role": "summary",
                },
                {
                    "relative_path": "metrics.json",
                    "sha256": "3333333333333333333333333333333333333333333333333333333333333333",
                    "size_bytes": 512,
                    "role": "metrics",
                },
            ],
            "run_directory": "/outputs/simulations/run_pass_001",
            "duplicate_content": [],
        },
        "validation": {
            "report_id": "val_empirical_001",
            "passed": True,
            "status": "PASS",
            "checks": {
                "finite_json": True,
                "network_accessed": False,
                "schema_valid": True,
            },
            "finite_json_verified": True,
            "zero_network_verified": True,
        },
        "evidence_review": {
            "review_id": "rev_empirical_001",
            "decision": "EVIDENCE_READY_FOR_REVIEW",
            "evidence_class": "empirical_dataset",
            "reason_codes": ["empirical_complete"],
            "operational_ready": True,
        },
    }


def create_partial_stages() -> dict[str, Any]:
    """Return stages for an interrupted/resumable run (PARTIAL)."""
    stages = create_complete_pass_stages()
    stages["execution_outcome"] = {
        "state": ExecutionOutcomeState.PARTIAL.value,
        "exit_code": None,
        "elapsed_s": 5.0,
        "error_message": "Run interrupted; checkpoint saved.",
        "runner_id": "bounded_runner",
    }
    stages["validation"]["passed"] = False
    stages["validation"]["status"] = "PARTIAL"
    stages["evidence_review"]["operational_ready"] = False
    stages["evidence_review"]["decision"] = "EVIDENCE_INCOMPLETE"
    return stages


def create_failed_stages() -> dict[str, Any]:
    """Return stages for a failed simulation (FAILED)."""
    stages = create_complete_pass_stages()
    stages["execution_outcome"] = {
        "state": ExecutionOutcomeState.FAILED.value,
        "exit_code": 1,
        "elapsed_s": 2.1,
        "error_message": "Integration diverged: NaN encountered in state vector",
        "runner_id": "bounded_runner",
    }
    stages["validation"]["passed"] = False
    stages["validation"]["status"] = "FAILED"
    stages["evidence_review"]["operational_ready"] = False
    stages["evidence_review"]["decision"] = "VALIDATION_FAILURE"
    return stages


def create_timeout_stages() -> dict[str, Any]:
    """Return stages for a timed-out run (TIMEOUT)."""
    stages = create_complete_pass_stages()
    stages["execution_outcome"] = {
        "state": ExecutionOutcomeState.TIMEOUT.value,
        "exit_code": -9,
        "elapsed_s": 300.1,
        "error_message": "Execution budget exceeded limit 300.0s",
        "runner_id": "bounded_runner",
    }
    stages["validation"]["passed"] = False
    stages["validation"]["status"] = "TIMEOUT"
    stages["evidence_review"]["operational_ready"] = False
    stages["evidence_review"]["decision"] = "RESOURCE_FAILURE"
    return stages


def create_missing_validation_stages() -> dict[str, Any]:
    """Return stages where execution completed PASS, but validation stage is missing."""
    stages = create_complete_pass_stages()
    del stages["validation"]
    return stages


def create_synthetic_only_stages() -> dict[str, Any]:
    """Return stages for a synthetic benchmark run."""
    stages = create_complete_pass_stages()
    stages["input_provenance"]["dataset_id"] = "synthetic_benchmark_lattice"
    stages["input_provenance"]["source"] = "generators.synthetic_lattice"
    stages["input_provenance"]["data_mode"] = "synthetic"
    stages["evidence_review"]["evidence_class"] = "synthetic_demo_only"
    stages["evidence_review"]["decision"] = "SYNTHETIC_ONLY"
    return stages


def create_proxy_only_stages() -> dict[str, Any]:
    """Return stages for a proxy surrogate run."""
    stages = create_complete_pass_stages()
    stages["input_provenance"]["dataset_id"] = "proxy_kuramoto_cohort"
    stages["input_provenance"]["source"] = "surrogates.kuramoto"
    stages["input_provenance"]["data_mode"] = "proxy"
    stages["evidence_review"]["evidence_class"] = "proxy_only"
    stages["evidence_review"]["decision"] = "PROXY_ONLY"
    return stages


def create_fabricated_provenance_stages() -> dict[str, Any]:
    """Return stages with placeholder/fabricated provenance values."""
    stages = create_complete_pass_stages()
    stages["input_provenance"]["dataset_id"] = "unknown"
    stages["input_provenance"]["source"] = "null"
    stages["code_revision"]["code_revision"] = "placeholder"
    stages["seed"]["seed"] = None
    return stages


def create_incomplete_manifest_stages() -> dict[str, Any]:
    """Return stages where manifest is missing RunRecord.json and summary/metrics."""
    stages = create_complete_pass_stages()
    stages["artifact_manifest"]["artifacts"] = [
        {
            "relative_path": "arbitrary_data.bin",
            "sha256": "4444444444444444444444444444444444444444444444444444444444444444",
            "size_bytes": 100,
            "role": "output",
        }
    ]
    return stages


def create_non_finite_metrics_stages() -> dict[str, Any]:
    """Return stages containing NaN / non-finite metrics."""
    stages = create_complete_pass_stages()
    stages["configuration"]["parameters"]["unstable_ratio"] = float("nan")
    return stages


def create_output_root_escape_stages() -> dict[str, Any]:
    """Return stages with output artifact path traversal."""
    stages = create_complete_pass_stages()
    stages["artifact_manifest"]["artifacts"].append({
        "relative_path": "../../secret_credentials.env",
        "sha256": "5555555555555555555555555555555555555555555555555555555555555555",
        "size_bytes": 64,
        "role": "leak",
    })
    return stages


def create_temporary_only_artifacts_stages() -> dict[str, Any]:
    """Return stages with exclusively temporary scratch files."""
    stages = create_complete_pass_stages()
    stages["artifact_manifest"]["artifacts"] = [
        {
            "relative_path": "tmp/scratch.tmp",
            "sha256": "6666666666666666666666666666666666666666666666666666666666666666",
            "size_bytes": 128,
            "role": "temp",
        },
        {
            "relative_path": "temp_run.tmp",
            "sha256": "7777777777777777777777777777777777777777777777777777777777777777",
            "size_bytes": 256,
            "role": "temp",
        },
    ]
    return stages


def create_blocked_stages() -> dict[str, Any]:
    """Return stages in BLOCKED execution state."""
    stages = create_complete_pass_stages()
    stages["execution_outcome"]["state"] = ExecutionOutcomeState.BLOCKED.value
    stages["execution_outcome"]["error_message"] = "Execution blocked by policy"
    stages["validation"]["passed"] = False
    return stages


def create_not_implemented_stages() -> dict[str, Any]:
    """Return stages in NOT_IMPLEMENTED execution state."""
    stages = create_complete_pass_stages()
    stages["execution_outcome"]["state"] = ExecutionOutcomeState.NOT_IMPLEMENTED.value
    stages["execution_outcome"]["error_message"] = "Requested solver feature not implemented"
    stages["validation"]["passed"] = False
    return stages


def populate_run_directory(
    target_dir: Path,
    stages: Mapping[str, Any],
) -> Path:
    """Populate a directory with valid JSON artifacts representing the given stages."""
    target_dir.mkdir(parents=True, exist_ok=True)

    prov = stages.get("input_provenance") or {}
    config = stages.get("configuration") or {}
    rev = stages.get("code_revision") or {}
    seed_spec = stages.get("seed") or {}
    outcome = stages.get("execution_outcome") or {}
    manifest = stages.get("artifact_manifest") or {}
    val = stages.get("validation") or {}
    review = stages.get("evidence_review") or {}

    # Write RunRecord.json
    run_record = {
        "schema_version": "0.1",
        "run_id": "run_fixture_001",
        "run_kind": "hypothesis",
        "created_at": "2026-09-11T00:00:00+00:00",
        "dataset_id": prov.get("dataset_id"),
        "source": prov.get("source"),
        "data_mode": prov.get("data_mode"),
        "git_commit": rev.get("code_revision"),
        "repo": rev.get("repo"),
        "input": config.get("parameters"),
        "argv": config.get("argv"),
        "verdict": outcome.get("state"),
        "elapsed_s": outcome.get("elapsed_s"),
        "metrics": {"q_proxy": 0.72},
        "artifacts": {"summary": "summary.json", "metrics": "metrics.json"},
    }
    (target_dir / "RunRecord.json").write_text(
        dumps_finite_json(run_record), encoding="utf-8"
    )

    # Write summary.json
    summary = {
        "status": outcome.get("state"),
        "dataset_id": prov.get("dataset_id"),
        "seed": seed_spec.get("seed"),
        "completed": outcome.get("state") == "PASS",
    }
    (target_dir / "summary.json").write_text(
        dumps_finite_json(summary), encoding="utf-8"
    )

    # Write metrics.json
    metrics = {"metric_a": 1.23, "metric_b": 4.56}
    (target_dir / "metrics.json").write_text(
        dumps_finite_json(metrics), encoding="utf-8"
    )

    # Write execution_manifest.json
    exec_manifest = {
        "schema_version": "NeuroTopologySim.BoundedExecution.v1",
        "state": outcome.get("state"),
        "exit_code": outcome.get("exit_code"),
        "elapsed_s": outcome.get("elapsed_s"),
        "error": outcome.get("error_message"),
        "runner_id": outcome.get("runner_id"),
        "code_revision": rev.get("code_revision"),
        "seed": seed_spec.get("seed"),
        "input_references": prov.get("input_references"),
    }
    (target_dir / "execution_manifest.json").write_text(
        dumps_finite_json(exec_manifest), encoding="utf-8"
    )

    # Write validation report if present
    if val:
        val_doc = {
            "schema_version": "NeuroTopologySim.ValidationReport.v1",
            "status": val.get("status"),
            "passed": val.get("passed", False),
            "payload": {
                "report_id": val.get("report_id"),
                "passed": val.get("passed", False),
                "validation_status": val.get("status"),
                "checks": val.get("checks", {"finite_json": True, "network_accessed": False}),
            },
        }
        (target_dir / "validation_report.json").write_text(
            dumps_finite_json(val_doc), encoding="utf-8"
        )

    # Write release evidence report if present
    if review:
        review_doc = {
            "schema_version": "1.0",
            "record_id": review.get("review_id"),
            "decision": review.get("decision"),
            "evidence_class": review.get("evidence_class"),
            "reason_codes": review.get("reason_codes", []),
        }
        (target_dir / "release_evidence_report.json").write_text(
            dumps_finite_json(review_doc), encoding="utf-8"
        )

    return target_dir
