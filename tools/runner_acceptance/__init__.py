"""Windows-focused acceptance harness for the isolated test runner.

Exercises ``scripts/run_tests_isolated.py`` through safe subprocesses to validate
its platform behavior. On non-Windows hosts the harness reports
``platform_status=unsupported`` and runs only portable contract tests -- it never
claims Windows behavior passed. The runner implementation is never modified.
"""
from __future__ import annotations

from .harness import (
    AcceptanceRecord,
    Capability,
    Outcome,
    PlatformStatus,
    build_powershell_command,
    detect_capability,
    json_safe,
    ps_single_quote,
    run_acceptance,
)

__all__ = [
    "AcceptanceRecord",
    "Capability",
    "Outcome",
    "PlatformStatus",
    "build_powershell_command",
    "detect_capability",
    "json_safe",
    "ps_single_quote",
    "run_acceptance",
]
