"""Cross-platform compatibility utilities and audit harness for NeuroTopology-Sim.

Provides unified, robust, and platform-neutral helpers for:
- Path normalization, comparison, and extended-length/Unicode handling.
- Temporary directory creation with retry-on-lock cleanup.
- Atomic JSON writes via temp sibling files.
- Non-destructive symlink, hardlink, and permission detection.
- Subprocess command construction and process-tree termination.
- Non-invasive optional dependency classification.
- Null-safe finite JSON serialization.
- Capability-aware test decisions without silent skips.
"""
from __future__ import annotations

from .audit import audit_platform_capabilities
from .decisions import evaluate_test_prerequisite, require_platform_capability
from .dependencies import classify_dependencies, classify_dependency
from .filesystem import (
    atomic_write_json,
    detect_file_permissions,
    detect_hardlink_capability,
    detect_symlink_capability,
    safe_read_json,
    safe_temp_dir,
)
from .paths import (
    IS_WINDOWS,
    compare_paths,
    has_unicode_characters,
    is_safe_relative_path,
    normalize_path,
    strip_extended_prefix,
    to_extended_length_path,
    to_posix_path,
    to_windows_path,
)
from .serialization import dump_finite_json, dumps_finite_json, sanitize_val_for_json
from .subprocess_ops import build_subprocess_cmd, run_guarded_subprocess, terminate_process_tree
from .types import (
    CapabilityResult,
    CapabilityStatus,
    DependencyClassification,
    DependencyStatus,
    PlatformAuditReport,
    PlatformTestDecision,
    ProcessResult,
)

__all__ = [
    # Audit & Decisions
    "audit_platform_capabilities",
    "evaluate_test_prerequisite",
    "require_platform_capability",
    # Paths
    "IS_WINDOWS",
    "normalize_path",
    "compare_paths",
    "to_posix_path",
    "to_windows_path",
    "to_extended_length_path",
    "strip_extended_prefix",
    "has_unicode_characters",
    "is_safe_relative_path",
    # Filesystem
    "safe_temp_dir",
    "atomic_write_json",
    "safe_read_json",
    "detect_symlink_capability",
    "detect_hardlink_capability",
    "detect_file_permissions",
    # Subprocess
    "build_subprocess_cmd",
    "run_guarded_subprocess",
    "terminate_process_tree",
    # Dependencies
    "classify_dependency",
    "classify_dependencies",
    # Serialization
    "dumps_finite_json",
    "dump_finite_json",
    "sanitize_val_for_json",
    # Types
    "CapabilityStatus",
    "CapabilityResult",
    "DependencyStatus",
    "DependencyClassification",
    "ProcessResult",
    "PlatformTestDecision",
    "PlatformAuditReport",
]
