"""Optional-dependency discovery: must work when every optional package is
absent, and must never import a heavy package just to check for it."""
from __future__ import annotations

import importlib.util

from tools.integration_bridge import capabilities


def test_detect_capabilities_never_raises_when_all_optional_absent(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    result = capabilities.detect_capabilities()
    assert result == {name: False for name in capabilities.OPTIONAL_PACKAGES}


def test_adapters_available_all_false_when_all_capabilities_absent():
    all_absent = {name: False for name in capabilities.OPTIONAL_PACKAGES}
    adapters = capabilities.adapters_available(all_absent)
    assert all(value is False for value in adapters.values())
    assert set(adapters) == set(capabilities.ADAPTER_REQUIREMENTS)


def test_find_spec_exception_is_treated_as_unavailable(monkeypatch):
    def _raise(name):
        raise ValueError("simulated malformed package metadata")

    monkeypatch.setattr(importlib.util, "find_spec", _raise)
    result = capabilities.detect_capabilities()
    assert result == {name: False for name in capabilities.OPTIONAL_PACKAGES}


def test_collect_environment_info_reflects_real_environment():
    info = capabilities.collect_environment_info()
    assert info.python_version
    assert info.platform
    assert set(info.capabilities) == set(capabilities.OPTIONAL_PACKAGES)
    as_dict = info.to_dict()
    assert as_dict["capabilities"] == dict(sorted(info.capabilities.items()))


def test_numpy_capability_gates_spatial_topology_adapter():
    caps = {"numpy": False}
    adapters = capabilities.adapters_available(caps)
    assert adapters["spatial_topology"] is False


def test_graph_beta1_requires_both_numpy_and_ripser():
    assert capabilities.adapters_available({"numpy": True, "ripser": False})["graph_beta1"] is False
    assert capabilities.adapters_available({"numpy": True, "ripser": True})["graph_beta1"] is True
