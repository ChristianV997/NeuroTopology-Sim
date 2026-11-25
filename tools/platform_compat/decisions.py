"""Capability-aware test execution decisions and explicit skip helpers.

Guarantees:
- Never silently skips tests.
- Clearly reports structured status: available, unavailable, unsupported, permission_denied, failed.
- Distinguishes platform capability absence from functional failures.
- Suggests concrete mitigation paths (e.g. Developer Mode on Windows).
"""
from __future__ import annotations

from typing import Optional

from .dependencies import classify_dependency
from .filesystem import detect_hardlink_capability, detect_symlink_capability
from .types import CapabilityResult, CapabilityStatus, DependencyStatus, PlatformTestDecision


def evaluate_test_prerequisite(
    prerequisite_name: str,
    required_status: CapabilityStatus = CapabilityStatus.AVAILABLE,
) -> PlatformTestDecision:
    """Evaluate whether a platform feature or dependency prerequisite is satisfied."""
    norm = prerequisite_name.strip().lower()

    if norm in ("symlink", "symlinks"):
        res = detect_symlink_capability()
        can_run = (res.status == required_status)
        mitigation = (
            "Enable Windows Developer Mode (Settings -> System -> For developers -> Developer Mode) "
            "or run with Administrator privileges." if res.status == CapabilityStatus.PERMISSION_DENIED else ""
        )
        return PlatformTestDecision(
            can_run=can_run,
            status=res.status,
            reason=res.details or f"Symlink capability status: {res.status.value}",
            mitigation=mitigation,
        )

    elif norm in ("hardlink", "hardlinks"):
        res = detect_hardlink_capability()
        can_run = (res.status == required_status)
        return PlatformTestDecision(
            can_run=can_run,
            status=res.status,
            reason=res.details or f"Hardlink capability status: {res.status.value}",
            mitigation="Ensure tests execute on a filesystem volume supporting hardlinks (e.g. NTFS/ext4).",
        )

    # Assume prerequisite refers to an optional module
    dep = classify_dependency(norm)
    if dep.status == DependencyStatus.AVAILABLE:
        return PlatformTestDecision(
            can_run=True,
            status=CapabilityStatus.AVAILABLE,
            reason=f"Optional dependency '{norm}' is available (version {dep.version or 'unknown'}).",
        )
    elif dep.status == DependencyStatus.MISSING:
        return PlatformTestDecision(
            can_run=False,
            status=CapabilityStatus.UNAVAILABLE,
            reason=f"Optional dependency '{norm}' is not installed.",
            mitigation=f"Install optional dependency '{norm}' if full accelerated functionality is required.",
        )
    elif dep.status == DependencyStatus.INCOMPATIBLE:
        return PlatformTestDecision(
            can_run=False,
            status=CapabilityStatus.UNSUPPORTED,
            reason=f"Dependency '{norm}' is installed but incompatible: {dep.details}",
            mitigation=f"Verify platform architecture and Python version compatibility for '{norm}'.",
        )
    else:
        return PlatformTestDecision(
            can_run=False,
            status=CapabilityStatus.FAILED,
            reason=f"Dependency '{norm}' failed to import: {dep.details}",
            mitigation=f"Inspect package installation integrity for '{norm}'.",
        )


def require_platform_capability(
    prerequisite_name: str,
    required_status: CapabilityStatus = CapabilityStatus.AVAILABLE,
) -> None:
    """Pytest helper: explicitly skip a test with structured diagnostic status and mitigation."""
    decision = evaluate_test_prerequisite(prerequisite_name, required_status)
    if not decision.can_run:
        try:
            import pytest
            msg = f"[{decision.status.value.upper()}] {decision.reason}"
            if decision.mitigation:
                msg += f" (Mitigation: {decision.mitigation})"
            pytest.skip(msg)
        except ImportError:
            pass
