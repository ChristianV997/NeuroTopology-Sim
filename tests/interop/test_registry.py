from __future__ import annotations

import importlib.util
import socket

from shared.interop.adapter_registry import AdapterRegistry, discover_adapters
from shared.interop.contracts import AdapterStatus


EXPECTED = {
    "numpy", "scipy", "mne", "mne_bids", "pynwb", "pylsl", "brainflow",
    "semantica", "scrapling", "torch", "braindecode", "snntorch",
}


def test_registry_has_all_declared_optional_dependencies_without_importing_them():
    before = {name: name in __import__("sys").modules for name in EXPECTED}
    registry = AdapterRegistry()
    result = registry.discover()
    assert set(result) == EXPECTED
    assert all(cap.status in set(AdapterStatus) for cap in result.values())
    assert all(name not in __import__("sys").modules for name, loaded in before.items() if not loaded)


def test_missing_optional_packages_are_explicitly_unavailable(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    result = discover_adapters()
    assert all(not capability.availability for capability in result.values())
    assert all(capability.status is AdapterStatus.UNAVAILABLE for capability in result.values())


def test_registry_does_not_open_network_sockets(monkeypatch):
    def fail_socket(*args, **kwargs):
        raise AssertionError("adapter discovery must not use the network")

    monkeypatch.setattr(socket, "socket", fail_socket)
    result = discover_adapters()
    assert result["pylsl"].network_requirement == "optional"
    assert result["semantica"].network_requirement == "none"
