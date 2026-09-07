"""Safe optional dependency classification without auto-installing or downloading binaries.

Features:
- Non-invasive spec probing via importlib.util.find_spec.
- Version extraction without importing heavy package runtime engines.
- Structured status classification (available, missing, incompatible, import_error).
"""
from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
from typing import Sequence

from .types import DependencyClassification, DependencyStatus


DEFAULT_OPTIONAL_DEPENDENCIES: list[str] = [
    "ripser",
    "gudhi",
    "gtda",
    "ripserplusplus",
    "mne",
    "scipy",
    "numpy",
    "matplotlib",
    "pandas",
]


def classify_dependency(module_name: str) -> DependencyClassification:
    """Classify availability and version of an optional package safely."""
    norm_name = module_name.strip().lower().replace("-", "_")

    # Fast check via importlib spec without executing package body
    try:
        spec = importlib.util.find_spec(norm_name)
    except (ImportError, AttributeError, ValueError) as exc:
        return DependencyClassification(
            name=module_name,
            status=DependencyStatus.IMPORT_ERROR,
            details=f"Spec resolution failed: {exc}",
        )

    if spec is None:
        return DependencyClassification(
            name=module_name,
            status=DependencyStatus.MISSING,
            details="Module is not installed in the current environment.",
        )

    # Attempt to read version from package metadata
    version: str | None = None
    dist_name = module_name.replace("_", "-")
    try:
        version = importlib.metadata.version(dist_name)
    except Exception:
        try:
            version = importlib.metadata.version(norm_name)
        except Exception:
            pass

    import_path = str(spec.origin) if spec.origin else None

    # Safe lazy import test for critical binary integrity
    try:
        mod = importlib.import_module(norm_name)
        if version is None and hasattr(mod, "__version__"):
            version = str(getattr(mod, "__version__"))
        return DependencyClassification(
            name=module_name,
            status=DependencyStatus.AVAILABLE,
            version=version,
            import_path=import_path,
            details=f"Module '{norm_name}' loaded successfully.",
        )
    except ModuleNotFoundError:
        return DependencyClassification(
            name=module_name,
            status=DependencyStatus.MISSING,
            details="Submodule or dependency not found.",
        )
    except (ImportError, OSError) as exc:
        # Check for ABI or DLL load failure
        msg = str(exc).lower()
        if any(term in msg for term in ("dll", "abi", "architecture", "incompatible", "c-extension")):
            return DependencyClassification(
                name=module_name,
                status=DependencyStatus.INCOMPATIBLE,
                version=version,
                import_path=import_path,
                details=f"Binary incompatibility or missing system DLL: {exc}",
            )
        return DependencyClassification(
            name=module_name,
            status=DependencyStatus.IMPORT_ERROR,
            version=version,
            import_path=import_path,
            details=f"Import error: {exc}",
        )
    except Exception as exc:
        return DependencyClassification(
            name=module_name,
            status=DependencyStatus.IMPORT_ERROR,
            version=version,
            import_path=import_path,
            details=f"Unexpected error during import probe: {exc}",
        )


def classify_dependencies(
    module_names: Sequence[str] | None = None,
) -> dict[str, DependencyClassification]:
    """Classify a collection of dependencies and return a mapping of name -> DependencyClassification."""
    names = module_names if module_names is not None else DEFAULT_OPTIONAL_DEPENDENCIES
    return {name: classify_dependency(name) for name in names}
