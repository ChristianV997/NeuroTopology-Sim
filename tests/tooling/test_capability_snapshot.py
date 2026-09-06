"""Offline tests for the additive capability snapshot layer."""
from __future__ import annotations

import importlib
import json
import math
import sys
import types
from pathlib import Path

import pytest
import yaml

from shared.tooling import capability_registry as registry
from shared.tooling import capability_snapshot as snapshot

REPO_YAML = Path(__file__).resolve().parents[2] / "configs" / "tools" / "optional_backends.yaml"


@pytest.fixture(autouse=True)
def _reset_registry():
    registry.reset_registry_cache()
    yield
    registry.reset_registry_cache()


def _write_registry(tmp_path: Path, document: dict) -> Path:
    path = tmp_path / "optional_backends.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


def _minimal_tool(**overrides):
    tool = {
        "id": "scipy_signal",
        "display_name": "SciPy signal",
        "package_name": "scipy",
        "import_name": "scipy.signal",
        "minimum_version": "1.10.0",
        "classification": "local_optional_dependency",
        "capability_category": "signal_filtering",
        "also_categories": [],
        "purposes": ["signal_filtering"],
        "input_contract": "arrays",
        "output_contract": "arrays",
        "units": {"time": "s"},
        "shapes": {"data": ["n_samples", "n_channels"]},
        "license": "BSD-3-Clause",
        "provenance": "SciPy",
        "network_requirement": "none",
        "deterministic_offline": True,
        "memory_risk": "medium",
        "scientific_support": "not_claimed",
        "notes": "test",
    }
    tool.update(overrides)
    return tool


def _minimal_document(tools=None):
    return {
        "schema_version": "1.0",
        "registry_id": registry.REGISTRY_SCHEMA,
        "description": "test",
        "defaults": {
            "offline": True,
            "allow_remote": False,
            "allow_install": False,
            "silent_fallback": False,
        },
        "tools": tools or [_minimal_tool()],
    }


def test_snapshot_is_deterministic(tmp_path):
    module = types.ModuleType("scipy.signal")
    module.__version__ = "1.14.0"
    path = _write_registry(tmp_path, _minimal_document())
    hooks = dict(
        registry_path=path,
        find_spec=lambda name: True,
        import_module=lambda name: module,
        distribution_version=lambda name: "1.14.0",
    )
    first = snapshot.capture_snapshot(**hooks)
    second = snapshot.capture_snapshot(**hooks)
    assert first == second
    assert snapshot.serialize_snapshot(first) == snapshot.serialize_snapshot(second)


def test_absent_optional_package(tmp_path):
    path = _write_registry(
        tmp_path,
        _minimal_document([_minimal_tool(id="mne", import_name="mne", capability_category="eeg_ingestion")]),
    )
    payload = snapshot.capture_snapshot(registry_path=path, find_spec=lambda name: False)
    record = payload["tools"]["mne"]
    assert record["availability"] == "missing"
    assert record["version"] is None
    assert record["unavailability_reason"]
    assert record["scientific_support"] == "not_claimed"


def test_fake_package_version(tmp_path):
    module = types.ModuleType("ntsim_fake")
    module.__version__ = "3.2.1"
    path = _write_registry(
        tmp_path,
        _minimal_document([
            _minimal_tool(
                id="fake",
                package_name="ntsim_fake",
                import_name="ntsim_fake",
                minimum_version="1.0.0",
            )
        ]),
    )
    payload = snapshot.capture_snapshot(
        registry_path=path,
        find_spec=lambda name: True,
        import_module=lambda name: module,
        distribution_version=lambda name: "3.2.1",
    )
    assert payload["tools"]["fake"]["availability"] == "available"
    assert payload["tools"]["fake"]["version"] == "3.2.1"
    assert payload["tools"]["fake"]["scientific_support"] == "not_claimed"


def test_remote_only_tool_is_not_local_support():
    payload = snapshot.capture_snapshot(offline=True, allow_remote=False, registry_path=REPO_YAML)
    record = payload["tools"]["notebooklm_mcp"]
    assert record["classification"] == "remote_service_mcp"
    assert record["availability"] == "opt_in_required"
    assert record["network_requirement"] == "required"
    assert record["version"] is None
    assert "notebooklm_mcp" in snapshot.remote_capabilities(payload)
    assert "notebooklm_mcp" not in snapshot.local_capabilities(payload)


def test_offline_mode_blocks_live_optional_network():
    payload = snapshot.capture_snapshot(offline=True, allow_remote=False, registry_path=REPO_YAML)
    assert payload["offline"] is True
    assert payload["tools"]["pylsl"]["availability"] == "offline_blocked"
    assert payload["tools"]["brainflow"]["availability"] == "offline_blocked"


def test_unknown_tool_id_is_rejected(tmp_path):
    path = _write_registry(tmp_path, _minimal_document())
    with pytest.raises(snapshot.CapabilitySnapshotError, match="unknown registry tool"):
        snapshot.capture_snapshot(tool_ids=["not_a_real_backend"], registry_path=path)


def test_malformed_metadata_is_rejected():
    with pytest.raises(snapshot.CapabilitySnapshotError, match="missing"):
        snapshot.validate_snapshot({"schema": snapshot.SNAPSHOT_SCHEMA})
    with pytest.raises(snapshot.CapabilitySnapshotError, match="not_claimed"):
        snapshot.validate_snapshot({
            "schema": snapshot.SNAPSHOT_SCHEMA,
            "registry_id": registry.REGISTRY_SCHEMA,
            "offline": True,
            "allow_remote": False,
            "allow_install": False,
            "scientific_support": "supported",
            "tools": {
                "scipy_signal": {
                    "tool_name": "scipy_signal",
                    "availability": "available",
                    "version": "1.0.0",
                    "capability_category": "signal_filtering",
                    "provenance": "SciPy",
                    "network_requirement": "none",
                    "determinism_state": "deterministic_offline",
                    "shapes": {},
                    "units": {},
                    "memory_risk": "medium",
                    "unavailability_reason": None,
                    "classification": "local_optional_dependency",
                    "scientific_support": "supported",
                }
            },
        })


def test_json_finite_null_compliance(tmp_path):
    module = types.ModuleType("scipy.signal")
    module.__version__ = "1.14.0"
    path = _write_registry(tmp_path, _minimal_document())
    payload = snapshot.capture_snapshot(
        registry_path=path,
        find_spec=lambda name: True,
        import_module=lambda name: module,
    )
    encoded = snapshot.serialize_snapshot(payload)
    loaded = json.loads(encoded)
    assert loaded["tools"]["scipy_signal"]["unavailability_reason"] is None
    with pytest.raises(snapshot.CapabilitySnapshotError, match="finite"):
        snapshot.json_safe({"bad": math.inf})
    with pytest.raises(snapshot.CapabilitySnapshotError, match="finite"):
        snapshot.json_safe({"bad": math.nan})


def test_import_time_has_no_backend_side_effects():
    names = ("mne", "brainflow", "pylsl", "spikeinterface", "braindecode", "snntorch", "psychopy")
    before = {name for name in names if name in sys.modules}
    importlib.reload(snapshot)
    after = {name for name in names if name in sys.modules}
    assert after == before


def test_attachment_refuses_run_record_shape(tmp_path):
    path = _write_registry(tmp_path, _minimal_document())
    payload = snapshot.capture_snapshot(registry_path=path, find_spec=lambda name: False)
    with pytest.raises(snapshot.CapabilitySnapshotError, match="RunRecordV1"):
        snapshot.attach_capability_snapshot(
            {"schema_version": "0.1", "run_kind": "hypothesis"},
            snapshot=payload,
        )
    sidecar = snapshot.attach_capability_snapshot({"runner": "offline"}, snapshot=payload)
    assert sidecar["runner"] == "offline"
    assert sidecar[snapshot.ATTACHMENT_KEY]["schema"] == snapshot.SNAPSHOT_SCHEMA


def test_committed_registry_snapshot_classifies_families():
    payload = snapshot.capture_snapshot(offline=True, registry_path=REPO_YAML, find_spec=lambda name: False)
    assert payload["schema"] == snapshot.SNAPSHOT_SCHEMA
    optional = snapshot.optional_capabilities(payload)
    remote = snapshot.remote_capabilities(payload)
    assert "scipy_signal" in optional
    assert "mne" in optional
    assert "notebooklm_mcp" in remote
    assert payload["tools"]["eeglab"]["availability"] == "external_only"
    assert payload["tools"]["snntorch"]["availability"] == "reference_only"
    for record in payload["tools"].values():
        assert record["scientific_support"] == "not_claimed"
