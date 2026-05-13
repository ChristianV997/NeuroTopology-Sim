"""Tests for science task registry (P18.2)."""
import pytest

from sciencer_d.btc_icft.runtime.task_inventory import (
    ScienceTaskRecord,
    ScienceTaskRegistry,
    build_default_science_task_registry,
)


def test_default_registry_has_known_tasks():
    reg = build_default_science_task_registry()
    task_ids = {t.task_id for t in reg.tasks}
    assert "p18_1_run_benchmark_mock_e2e" in task_ids
    assert "p12_align_eeg_labels" in task_ids
    assert "p13_inject_eeg_targets" in task_ids
    assert "p11_run_eeg_signal_mt" in task_ids


def test_registry_get_existing_task():
    reg = build_default_science_task_registry()
    task = reg.get("p18_1_run_benchmark_mock_e2e")
    assert task is not None
    assert task.module == "sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark"


def test_registry_get_missing_task_returns_none():
    reg = build_default_science_task_registry()
    assert reg.get("nonexistent_task_xyz") is None


def test_registry_to_dict_has_tasks_key():
    reg = build_default_science_task_registry()
    d = reg.to_dict()
    assert "tasks" in d
    assert len(d["tasks"]) == len(reg.tasks)
    assert len(reg.tasks) >= 17
