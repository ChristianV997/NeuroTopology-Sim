"""Backend registry and dynamic capability discovery for persistent homology adapters.

Features:
- Safe, non-invasive capability inspection.
- Priority-ordered fallback resolution.
- Clear error reporting for missing, incompatible, or offline-disabled backends.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Type

from .base import BaseTDABackend
from .backends import (
    GiottoTDABackend,
    GudhiBackend,
    RipserBackend,
    RipserPlusPlusBackend,
)
from .fallback import DeterministicFallbackBackend
from .types import (
    BackendCapability,
    BackendCapabilityStatus,
    BackendName,
)


_BACKEND_CLASSES: dict[str, Type[BaseTDABackend]] = {
    BackendName.RIPSER.value: RipserBackend,
    BackendName.GUDHI.value: GudhiBackend,
    BackendName.RIPSER_PLUS_PLUS.value: RipserPlusPlusBackend,
    BackendName.GIOTTO_TDA.value: GiottoTDABackend,
    BackendName.FALLBACK.value: DeterministicFallbackBackend,
}

_DEFAULT_PRIORITY: list[str] = [
    BackendName.RIPSER.value,
    BackendName.GUDHI.value,
    BackendName.FALLBACK.value,
]


def get_all_capabilities() -> dict[str, BackendCapability]:
    """Inspect and return capability status for all registered backends."""
    capabilities: dict[str, BackendCapability] = {}
    for name, cls in _BACKEND_CLASSES.items():
        try:
            backend_inst = cls()
            capabilities[name] = backend_inst.get_capability()
        except Exception as exc:
            capabilities[name] = BackendCapability(
                name=name,
                status=BackendCapabilityStatus.FAILED,
                description=f"Backend '{name}' failed during capability check.",
                details=str(exc),
            )
    return capabilities


def list_available_backends() -> list[str]:
    """Return names of all currently available persistent homology backends."""
    caps = get_all_capabilities()
    return [name for name, cap in caps.items() if cap.status == BackendCapabilityStatus.AVAILABLE]


def get_backend(name: str | None = None) -> BaseTDABackend:
    """Instantiate and return a persistent homology backend adapter.

    If name is None, automatically selects the highest-priority available backend.
    If name is specified, validates that the backend is registered and available.
    """
    if name is None:
        # Automatic selection based on priority
        for candidate_name in _DEFAULT_PRIORITY:
            cls = _BACKEND_CLASSES[candidate_name]
            backend_inst = cls()
            cap = backend_inst.get_capability()
            if cap.status == BackendCapabilityStatus.AVAILABLE:
                return backend_inst

        # Fallback is always available
        return DeterministicFallbackBackend()

    canonical_name = name.strip().lower().replace("_", "-")
    # Normalize aliases
    if canonical_name in ("ripser++", "ripserplusplus", "ripser-plusplus", "ripser-plus-plus"):
        canonical_name = BackendName.RIPSER_PLUS_PLUS.value
    elif canonical_name in ("fallback", "numpy", "scipy", "deterministic_fallback"):
        canonical_name = BackendName.FALLBACK.value
    elif canonical_name in ("giotto", "gtda", "giotto_tda"):
        canonical_name = BackendName.GIOTTO_TDA.value

    if canonical_name not in _BACKEND_CLASSES:
        valid_backends = list(_BACKEND_CLASSES.keys())
        raise KeyError(f"Unknown TDA backend '{name}'. Available backends: {valid_backends}")

    backend_inst = _BACKEND_CLASSES[canonical_name]()
    cap = backend_inst.get_capability()
    if cap.status != BackendCapabilityStatus.AVAILABLE:
        raise RuntimeError(
            f"Requested TDA backend '{canonical_name}' is not available (status='{cap.status.value}'). "
            f"Details: {cap.details or cap.description}"
        )

    return backend_inst
