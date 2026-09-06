"""Offline tests for the optional-backend capability registry."""
from __future__ import annotations

import importlib
import json
import socket
import sys
import types
from pathlib import Path

import pytest
import yaml

from shared.tooling import capability_registry as registry

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


def test_committed_registry_loads_and_lists_expected_ids():
    document = registry.load_registry(REPO_YAML)
    assert document.registry_id == registry.REGISTRY_SCHEMA
    ids = {spec.id for spec in registry.list_tools(REPO_YAML)}
    assert ids == {
        "mne", "scipy_signal", "eeglab", "fieldtrip", "pylsl", "brainflow",
        "psychopy", "spikeinterface", "pynwb", "braindecode", "snntorch",
        "neurodata_tooling", "notebooklm_mcp", "semantica", "scrapling",
    }


def test_malformed_registry_missing_tools(tmp_path):
    path = _write_registry(tmp_path, {"schema_version": "1.0", "registry_id": registry.REGISTRY_SCHEMA})
    with pytest.raises(registry.CapabilityRegistryError, match="tools"):
        registry.load_registry(path)


def test_malformed_registry_bad_classification(tmp_path):
    document = _minimal_document([_minimal_tool(classification="magic")])
    path = _write_registry(tmp_path, document)
    with pytest.raises(registry.CapabilityRegistryError, match="classification"):
        registry.load_registry(path)


def test_malformed_registry_duplicate_ids(tmp_path):
    document = _minimal_document([_minimal_tool(), _minimal_tool()])
    path = _write_registry(tmp_path, document)
    with pytest.raises(registry.CapabilityRegistryError, match="duplicate"):
        registry.load_registry(path)


def test_malformed_registry_allow_install_forbidden(tmp_path):
    document = _minimal_document()
    document["defaults"]["allow_install"] = True
    path = _write_registry(tmp_path, document)
    with pytest.raises(registry.CapabilityRegistryError, match="allow_install"):
        registry.load_registry(path)


def test_absent_dependency_is_missing(tmp_path):
    path = _write_registry(tmp_path, _minimal_document([_minimal_tool(id="ghost", import_name="ntsim_ghost_backend")]))
    result = registry.probe_tool("ghost", registry_path=path, find_spec=lambda name: False)
    assert result.availability == "missing"
    assert result.selected is False


def test_fake_installed_dependency_is_available(tmp_path):
    module = types.ModuleType("ntsim_fake_backend")
    module.__version__ = "2.0.0"
    path = _write_registry(
        tmp_path,
        _minimal_document([
            _minimal_tool(
                id="fake",
                package_name="ntsim_fake_backend",
                import_name="ntsim_fake_backend",
                minimum_version="1.0.0",
            )
        ]),
    )
    result = registry.probe_tool(
        "fake",
        registry_path=path,
        find_spec=lambda name: True,
        import_module=lambda name: module,
        distribution_version=lambda name: "2.0.0",
    )
    assert result.availability == "available"
    assert result.installed_version == "2.0.0"


def test_version_incompatibility(tmp_path):
    module = types.ModuleType("ntsim_old_backend")
    module.__version__ = "0.2.0"
    path = _write_registry(
        tmp_path,
        _minimal_document([
            _minimal_tool(
                id="old",
                package_name="ntsim_old_backend",
                import_name="ntsim_old_backend",
                minimum_version="1.5.0",
            )
        ]),
    )
    result = registry.probe_tool(
        "old",
        registry_path=path,
        find_spec=lambda name: True,
        import_module=lambda name: module,
        distribution_version=lambda name: "0.2.0",
    )
    assert result.availability == "incompatible_version"


def test_offline_mode_blocks_network_required_local_tool(tmp_path):
    path = _write_registry(
        tmp_path,
        _minimal_document([
            _minimal_tool(
                id="netful",
                import_name="ntsim_netful",
                network_requirement="required",
                deterministic_offline=False,
            )
        ]),
    )
    result = registry.probe_tool(
        "netful",
        offline=True,
        allow_remote=False,
        registry_path=path,
        find_spec=lambda name: True,
        import_module=lambda name: types.ModuleType("ntsim_netful"),
    )
    assert result.availability == "offline_blocked"


def test_remote_service_stays_opt_in(tmp_path):
    path = _write_registry(
        tmp_path,
        _minimal_document([
            _minimal_tool(
                id="notebooklm_mcp",
                classification="remote_service_mcp",
                capability_category="notebook_document_research",
                purposes=["notebook_document_research"],
                import_name=None,
                network_requirement="required",
                deterministic_offline=False,
            )
        ]),
    )
    result = registry.probe_tool("notebooklm_mcp", offline=False, allow_remote=True, registry_path=path)
    assert result.availability == "opt_in_required"


def test_reference_only_is_not_selectable(tmp_path):
    path = _write_registry(
        tmp_path,
        _minimal_document([
            _minimal_tool(
                id="snntorch",
                classification="research_reference_only",
                capability_category="neural_decoding",
                purposes=[],
                import_name="snntorch",
            )
        ]),
    )
    result = registry.probe_tool("snntorch", registry_path=path)
    assert result.availability == "reference_only"
    with pytest.raises(registry.CapabilityAdmissionError):
        registry.select_backend("snntorch", purpose="neural_decoding", registry_path=path)


def test_select_backend_rejects_wrong_purpose(tmp_path):
    module = types.ModuleType("scipy.signal")
    module.__version__ = "1.11.0"
    path = _write_registry(tmp_path, _minimal_document())
    with pytest.raises(registry.CapabilityAdmissionError, match="silently fall back"):
        registry.select_backend(
            "scipy_signal",
            purpose="tda",
            registry_path=path,
            find_spec=lambda name: True,
            import_module=lambda name: module,
        )


def test_select_backend_does_not_fallback_when_missing(tmp_path):
    document = _minimal_document([
        _minimal_tool(id="mne", purposes=["eeg_ingestion"], capability_category="eeg_ingestion", import_name="mne"),
        _minimal_tool(),
    ])
    path = _write_registry(tmp_path, document)
    with pytest.raises(registry.CapabilityAdmissionError, match="missing"):
        registry.select_backend(
            "mne",
            purpose="eeg_ingestion",
            registry_path=path,
            find_spec=lambda name: False,
        )


def test_capability_metadata_is_deterministic(tmp_path):
    module = types.ModuleType("scipy.signal")
    module.__version__ = "1.14.0"
    path = _write_registry(tmp_path, _minimal_document())
    hooks = {
        "registry_path": path,
        "find_spec": lambda name: True,
        "import_module": lambda name: module,
        "distribution_version": lambda name: "1.14.0",
    }
    first = registry.capability_metadata(selected={"signal_filtering": "scipy_signal"}, **hooks)
    second = registry.capability_metadata(selected={"signal_filtering": "scipy_signal"}, **hooks)
    assert first == second
    encoded = registry.serialize_capability_state(first)
    assert encoded == registry.serialize_capability_state(second)
    json.loads(encoded)
    assert first["allow_install"] is False
    assert first["silent_fallback"] is False
    assert first["selected"]["signal_filtering"]["selected"] is True


def test_probe_makes_no_network_calls(monkeypatch):
    def _blocked(*args, **kwargs):
        raise AssertionError("network call is forbidden")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    registry.probe_all(offline=True, registry_path=REPO_YAML, find_spec=lambda name: False)


def test_import_time_has_no_backend_side_effects():
    names = ("mne", "brainflow", "pylsl", "spikeinterface", "braindecode", "snntorch", "psychopy")
    before = {name for name in names if name in sys.modules}
    importlib.reload(registry)
    after = {name for name in names if name in sys.modules}
    assert after == before


def test_committed_yaml_does_not_claim_scientific_support():
    for spec in registry.list_tools(REPO_YAML):
        assert spec.scientific_support == "not_claimed"


def test_purpose_catalog_has_no_tda_backend():
    assert registry.tools_for_purpose("tda", REPO_YAML) == ()


def test_external_toolchain_is_external_only():
    result = registry.probe_tool("eeglab", registry_path=REPO_YAML)
    assert result.availability == "external_only"
    with pytest.raises(registry.CapabilityAdmissionError):
        registry.select_backend("eeglab", purpose="eeg_ingestion", registry_path=REPO_YAML)
