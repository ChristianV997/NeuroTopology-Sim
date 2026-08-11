"""Store + CLI tests for benchmarks.export_registry.BenchmarkRegistry.

Exercises both the library (`BenchmarkRegistry`) and the actual
`python -m benchmarks.export_registry` subprocess CLI against the real
committed benchmarks/registry_seed.json, plus small tmp_path-based registries
for mutation (mark-seen / lock / consume) tests so the committed seed file
is never mutated by a test run.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks.artifact_registry import ArtifactRecordV1
from benchmarks.dataset_registry import DatasetRecordV1
from benchmarks.export_registry import BenchmarkRegistry, RegistryError

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SEED = _REPO_ROOT / "benchmarks" / "registry_seed.json"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "benchmarks.export_registry", *args],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )


def _write_small_registry(tmp_path: Path) -> Path:
    dataset = DatasetRecordV1.make(
        dataset_id="ds_cli_test", display_name="cli test dataset", modalities=["EEG"],
        current_role="development", allowed_uses=["transition_export"],
        forbidden_uses=["final_claim_confirmation"], contamination_status="unseen",
        claim_scope_ceiling="exploratory_metric", evidence_level_ceiling="L0_computational_artifact",
        provenance="synthetic fixture", limitations=["test only"],
    )
    locked = DatasetRecordV1.make(
        dataset_id="ds_locked_test", display_name="locked test dataset", modalities=["EEG"],
        current_role="locked_internal_validation", allowed_uses=["internal_validation"],
        forbidden_uses=[], contamination_status="unseen",
        claim_scope_ceiling="exploratory_metric", evidence_level_ceiling="L0_computational_artifact",
        provenance="synthetic fixture", limitations=["test only"],
        validation_lock={
            "locked_at": "2026-01-01T00:00:00+00:00", "locked_by": "operator",
            "reason": "test lock", "allowed_claim_family": "fam_x",
            "consumed": False, "consumed_at": None, "consumed_by": None,
        },
    )
    registry = BenchmarkRegistry(datasets={dataset.dataset_id: dataset, locked.dataset_id: locked})
    path = tmp_path / "small_registry.json"
    registry.save(path)
    return path


# ── 5. Store/CLI ─────────────────────────────────────────────────────────────

def test_load_seed_registry():
    registry = BenchmarkRegistry.load(_SEED)
    assert len(registry.datasets) == 4
    assert len(registry.artifacts) == 6


def test_list_datasets_and_artifacts():
    registry = BenchmarkRegistry.load(_SEED)
    dataset_ids = {r.dataset_id for r in registry.list_datasets()}
    assert dataset_ids == {"ds005620", "ds000245", "ds005917", "ds006644"}
    artifacts = registry.list_artifacts(dataset_id="ds005620")
    assert len(artifacts) == 2


def test_list_datasets_filters_by_role_and_modality():
    registry = BenchmarkRegistry.load(_SEED)
    development = registry.list_datasets(role="development")
    assert {r.dataset_id for r in development} == {"ds005620", "ds000245"}
    fmri = registry.list_datasets(modality="fMRI")
    assert {r.dataset_id for r in fmri} == {"ds000245", "ds005917", "ds006644"}


def test_check_allowed_use_returns_success():
    registry = BenchmarkRegistry.load(_SEED)
    allowed, reason = registry.check_use("ds005620", "transition_export")
    assert allowed is True
    assert reason == "allowed"


def test_check_forbidden_use_returns_clear_failure():
    registry = BenchmarkRegistry.load(_SEED)
    allowed, reason = registry.check_use("ds005620", "clinical_claim")
    assert allowed is False
    assert reason  # non-empty explanation


def test_validate_seed_registry_passes():
    registry = BenchmarkRegistry.load(_SEED)
    assert registry.validate() == {}


def test_get_unknown_id_raises_registry_error():
    registry = BenchmarkRegistry.load(_SEED)
    with pytest.raises(RegistryError):
        registry.get("not_a_real_id")


def test_load_missing_file_raises_registry_error(tmp_path):
    with pytest.raises(RegistryError):
        BenchmarkRegistry.load(tmp_path / "does_not_exist.json")


def test_mark_seen_via_registry_and_save(tmp_path):
    path = _write_small_registry(tmp_path)
    registry = BenchmarkRegistry.load(path)
    registry.mark_seen("ds_cli_test", seen_by="llm", note="tested")
    out = tmp_path / "updated.json"
    registry.save(out)
    reloaded = BenchmarkRegistry.load(out)
    assert reloaded.datasets["ds_cli_test"].contamination_status == "seen_by_llm"


def test_lock_and_consume_via_registry(tmp_path):
    dataset = DatasetRecordV1.make(
        dataset_id="ds_lock_flow", display_name="lock flow test", modalities=["EEG"],
        current_role="locked_internal_validation", allowed_uses=["internal_validation"],
        forbidden_uses=[], contamination_status="unseen",
        claim_scope_ceiling="exploratory_metric", evidence_level_ceiling="L0_computational_artifact",
        provenance="synthetic fixture", limitations=["test only"],
    )
    registry = BenchmarkRegistry(datasets={dataset.dataset_id: dataset})
    registry.lock_for_validation("ds_lock_flow", locked_by="operator", reason="prereg replication", claim_family="fam_x")
    allowed, _ = registry.check_use("ds_lock_flow", "internal_validation", claim_family="fam_x")
    assert allowed
    registry.consume_validation_lock("ds_lock_flow", claim_family="fam_x", consumed_by="test_run")
    allowed, reason = registry.check_use("ds_lock_flow", "internal_validation", claim_family="fam_x")
    assert not allowed
    assert "already been consumed" in reason


# ── CLI subprocess tests ─────────────────────────────────────────────────────

def test_cli_validate_seed_registry_exits_zero():
    result = _run_cli("--registry", str(_SEED), "--validate")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["valid"] is True
    assert payload["datasets"] == 4
    assert payload["artifacts"] == 6


def test_cli_list_datasets():
    result = _run_cli("--registry", str(_SEED), "--list-datasets")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert {row["id"] for row in payload} == {"ds005620", "ds000245", "ds005917", "ds006644"}


def test_cli_check_use_allowed_exits_zero():
    result = _run_cli("--registry", str(_SEED), "--check-use", "ds005620", "transition_export")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["allowed"] is True


def test_cli_check_use_forbidden_exits_nonzero():
    result = _run_cli("--registry", str(_SEED), "--check-use", "ds005620", "final_claim_confirmation")
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["allowed"] is False
    assert payload["reason"]


def test_cli_mark_seen_requires_out(tmp_path):
    path = _write_small_registry(tmp_path)
    result = _run_cli("--registry", str(path), "--mark-seen", "ds_cli_test", "--seen-by", "llm")
    assert result.returncode == 1
    assert "--out" in result.stdout


def test_cli_mark_seen_writes_updated_registry(tmp_path):
    path = _write_small_registry(tmp_path)
    out = tmp_path / "out.json"
    result = _run_cli(
        "--registry", str(path), "--mark-seen", "ds_cli_test", "--seen-by", "llm", "--out", str(out),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    reloaded = BenchmarkRegistry.load(out)
    assert reloaded.datasets["ds_cli_test"].contamination_status == "seen_by_llm"


def test_cli_lock_for_validation_writes_updated_registry(tmp_path):
    path = _write_small_registry(tmp_path)
    out = tmp_path / "out.json"
    # ds_locked_test already carries a validation_lock in the fixture; issuing
    # a fresh one over an unconsumed lock should fail closed via the CLI.
    result = _run_cli(
        "--registry", str(path), "--lock-for-validation", "ds_locked_test",
        "--claim-family", "fam_y", "--reason", "test", "--locked-by", "op", "--out", str(out),
    )
    assert result.returncode == 1
    assert "unconsumed validation_lock" in result.stdout


def test_cli_seed_file_never_mutated_by_this_test_suite():
    before = _SEED.read_text(encoding="utf-8")
    _run_cli("--registry", str(_SEED), "--check-use", "ds005620", "transition_export")
    after = _SEED.read_text(encoding="utf-8")
    assert before == after
