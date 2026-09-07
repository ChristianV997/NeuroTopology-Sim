#!/usr/bin/env python3
"""CLI utility to audit cross-platform compatibility capabilities for NeuroTopology-Sim.

Usage:
    python scripts/run_platform_compat_audit.py --output audit.json
    python scripts/run_platform_compat_audit.py --verbose
    python scripts/run_platform_compat_audit.py --check-prereq symlinks
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.platform_compat import (
    CapabilityStatus,
    DependencyStatus,
    audit_platform_capabilities,
    evaluate_test_prerequisite,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_platform_compat_audit",
        description="Audit host platform capabilities and dependency status for NeuroTopology-Sim.",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Path to write structured JSON audit report.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Display detailed diagnostic output for each capability probe.",
    )
    parser.add_argument(
        "--check-prereq",
        type=str,
        default=None,
        help="Check a specific capability or dependency prerequisite and exit 0 if available.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.check_prereq:
        decision = evaluate_test_prerequisite(args.check_prereq)
        print(f"Prerequisite: {args.check_prereq}")
        print(f"Status:       {decision.status.value.upper()}")
        print(f"Can run:      {decision.can_run}")
        print(f"Reason:       {decision.reason}")
        if decision.mitigation:
            print(f"Mitigation:   {decision.mitigation}")
        return 0 if decision.can_run else 1

    print("=" * 72)
    print(" NeuroTopology-Sim: Platform Compatibility Audit")
    print("=" * 72)

    report = audit_platform_capabilities(output_path=args.output)

    print(f"Host OS:          {report.os_name} {report.os_release} ({report.platform})")
    print(f"Python Version:   {report.python_version}")
    print(f"Windows Host:     {report.is_windows}")
    print(f"Audit Timestamp:  {report.timestamp}")
    print(f"Audit Checksum:   {report.deterministic_checksum[:16]}...")
    print("-" * 72)
    print("Capabilities:")
    for name, cap in sorted(report.capabilities.items()):
        status_tag = f"[{cap.status.value.upper():17s}]"
        print(f"  {status_tag} {name:22s}: {cap.details}")
        if args.verbose and cap.error_type:
            print(f"      Error: {cap.error_type}")
        if args.verbose and cap.metadata:
            print(f"      Metadata: {cap.metadata}")

    print("-" * 72)
    print("Optional Dependencies:")
    for name, dep in sorted(report.dependencies.items()):
        status_tag = f"[{dep.status.value.upper():17s}]"
        ver_info = f"(v{dep.version})" if dep.version else ""
        print(f"  {status_tag} {name:22s} {ver_info:12s}: {dep.details}")

    print("=" * 72)
    if args.output:
        print(f"Structured audit written to: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
