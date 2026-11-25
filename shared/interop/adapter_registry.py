"""Lazy capability discovery for native signal/topology adapters."""
from __future__ import annotations

import importlib.util
from dataclasses import asdict
from typing import Any

from .contracts import AdapterCapability, AdapterStatus


# These are declarations, not imports.  The registry must work in a minimal
# offline test environment and must not initialize native backends.
_ADAPTER_SPECS: tuple[dict[str, Any], ...] = (
    {"adapter_name": "numpy", "dependency": "numpy", "formats": ("array",), "status": AdapterStatus.INTEGRATED},
    {"adapter_name": "scipy", "dependency": "scipy", "formats": ("array", "mat",), "status": AdapterStatus.INTEGRATED},
    {"adapter_name": "mne", "dependency": "mne", "formats": ("fif", "edf", "bdf", "set", "vhdr"), "montage": True, "status": AdapterStatus.INTEGRATED},
    {"adapter_name": "mne_bids", "dependency": "mne_bids", "formats": ("bids",), "montage": True, "status": AdapterStatus.INTEGRATED},
    {"adapter_name": "pynwb", "dependency": "pynwb", "formats": ("nwb",), "montage": True, "write": True, "status": AdapterStatus.INTEGRATED},
    {"adapter_name": "pylsl", "dependency": "pylsl", "formats": ("lsl",), "streaming": True, "network": "optional", "status": AdapterStatus.EMULATE},
    {"adapter_name": "brainflow", "dependency": "brainflow", "formats": ("board-stream",), "streaming": True, "network": "optional", "status": AdapterStatus.EMULATE},
    {"adapter_name": "semantica", "dependency": "semantica", "formats": ("metadata",), "network": "none", "status": AdapterStatus.REFERENCE},
    {"adapter_name": "scrapling", "dependency": "scrapling", "formats": ("metadata",), "network": "optional", "status": AdapterStatus.REFERENCE},
    {"adapter_name": "torch", "dependency": "torch", "formats": ("tensor",), "status": AdapterStatus.INTEGRATED},
    {"adapter_name": "braindecode", "dependency": "braindecode", "formats": ("tensor",), "status": AdapterStatus.REFERENCE},
    {"adapter_name": "snntorch", "dependency": "snntorch", "formats": ("tensor",), "status": AdapterStatus.REFERENCE},
)


def _available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


class AdapterRegistry:
    """A deterministic registry whose discovery has no network side effects."""

    def __init__(self) -> None:
        self._capabilities: dict[str, AdapterCapability] = {}

    def discover(self) -> dict[str, AdapterCapability]:
        capabilities: dict[str, AdapterCapability] = {}
        for spec in _ADAPTER_SPECS:
            available = _available(spec["dependency"])
            capabilities[spec["adapter_name"]] = AdapterCapability(
                adapter_name=spec["adapter_name"],
                supported_formats=spec.get("formats", ()),
                dependency=spec["dependency"],
                availability=available,
                streaming_support=bool(spec.get("streaming", False)),
                montage_support=bool(spec.get("montage", False)),
                write_support=bool(spec.get("write", False)),
                network_requirement=spec.get("network", "none"),
                status=spec["status"] if available else AdapterStatus.UNAVAILABLE,
            )
        self._capabilities = capabilities
        return dict(capabilities)

    def get(self, adapter_name: str) -> AdapterCapability:
        if not self._capabilities:
            self.discover()
        return self._capabilities[adapter_name]

    def as_dict(self) -> dict[str, dict[str, Any]]:
        if not self._capabilities:
            self.discover()
        return {name: asdict(capability) | {"status": capability.status.value} for name, capability in self._capabilities.items()}


def discover_adapters() -> dict[str, AdapterCapability]:
    return AdapterRegistry().discover()


__all__ = ["AdapterRegistry", "discover_adapters"]
