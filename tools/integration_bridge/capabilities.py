"""Optional-dependency and adapter discovery for the ecosystem-assembly run.

Deliberately import-safe: this module must be importable and its functions
callable even when every optional package below is absent. It only ever
uses ``importlib.util.find_spec`` (a metadata lookup) to test availability
— it never imports a heavy optional package just to check for it, and it
never fails when one is missing.
"""
from __future__ import annotations

import importlib.util
import platform
import sys
from dataclasses import dataclass, field
from typing import Dict, Tuple

# Packages this integration's own code paths can optionally use. Each entry
# names the exact capability it unlocks so preflight can explain a skip
# instead of silently degrading.
OPTIONAL_PACKAGES: Tuple[str, ...] = (
    "numpy",
    "scipy",
    "pandas",
    "sklearn",
    "yaml",
    "mne",
    "ripser",
    "gudhi",
    "boto3",
    "statsmodels",
)

# Which OPTIONAL_PACKAGES entry each analysis adapter requires. Used by
# run_plan.py to skip a stage cleanly rather than raising ImportError deep
# inside a public adapter.
ADAPTER_REQUIREMENTS: Dict[str, Tuple[str, ...]] = {
    "spatial_topology": ("numpy",),          # core.topology
    "graph_beta1": ("numpy", "ripser"),       # analysis.connectivity_topology.compute_beta1
    "scalar_chirality": ("numpy",),           # sim.pitnn.topological_invariants
    "bayesian_falsification": ("numpy",),     # sim.pitnn.bayesian_falsification
    "empirical_ingestion": ("numpy", "scipy"),  # sim.pitnn.ingest_empirical
    "mne_local_ingestion": ("mne",),           # .fif/.edf path inside ingest_empirical
    "hypothesis_spec_yaml": ("yaml",),
}


def _is_importable(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        # find_spec can itself raise for a malformed/partial package;
        # treat that identically to "not available" rather than crashing
        # discovery.
        return False


def detect_capabilities() -> Dict[str, bool]:
    """Return {package_name: is_importable} for every optional package this
    integration's adapters can use. Never raises."""
    return {name: _is_importable(name) for name in OPTIONAL_PACKAGES}


def adapters_available(capabilities: Dict[str, bool]) -> Dict[str, bool]:
    """Return {adapter_name: bool} — whether every package an adapter needs
    is present, derived from ADAPTER_REQUIREMENTS + a capability map (as
    returned by detect_capabilities())."""
    return {
        adapter: all(capabilities.get(pkg, False) for pkg in required)
        for adapter, required in ADAPTER_REQUIREMENTS.items()
    }


@dataclass(frozen=True)
class EnvironmentInfo:
    """Environment metadata recorded verbatim into the packaged artifacts —
    never used to gate behavior, only to make a run's context reproducible."""

    python_version: str
    platform: str
    capabilities: Dict[str, bool] = field(default_factory=dict)
    adapters: Dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "python_version": self.python_version,
            "platform": self.platform,
            "capabilities": dict(sorted(self.capabilities.items())),
            "adapters": dict(sorted(self.adapters.items())),
        }


def collect_environment_info() -> EnvironmentInfo:
    capabilities = detect_capabilities()
    return EnvironmentInfo(
        python_version=sys.version.split()[0],
        platform=platform.platform(),
        capabilities=capabilities,
        adapters=adapters_available(capabilities),
    )
