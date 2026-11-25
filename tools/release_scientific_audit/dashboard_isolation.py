"""Audit check 9: dashboard/API solver isolation.

Independent, self-contained static AST scan -- this module does not
import tools/integration_reconciliation.dashboard_isolation (a different,
not-owned package on a sibling branch); it re-implements the same class
of check from scratch so this audit's verdict never depends on trusting
another tool's code, only on reading source text directly. A previously
supplied "claimed_ok" value (e.g. from docs/release/dashboard_isolation_report.md)
is cross-checked against this independent scan, not trusted on its own --
a mismatch is itself a blocking finding.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Optional

from .models import DashboardIsolationInput, Finding

FORBIDDEN_IMPORT_PREFIXES: tuple[str, ...] = (
    "sim.pitnn",
    "physics.exact_dynamics",
    "core.topology",
    "analysis.connectivity_topology",
    "analysis.permutation",
    "governance",
    "shared.interop",
    "tools.integration_bridge",
    "tools.integration_reconciliation",
    "tools.release_scientific_audit",
    "scripts.assemble_ecosystem_run",
    "scripts.verify_integration_reconciliation",
    "scripts.audit_integrated_release",
)


def _imported_module_names(source_path: Path) -> set[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def scan_dashboard_source(dashboard_src: Path) -> dict:
    if not dashboard_src.exists():
        return {"ok": None, "scanned_files": 0, "violations": [], "evidence": f"{dashboard_src} does not exist"}
    violations: List[str] = []
    scanned = 0
    for path in sorted(dashboard_src.rglob("*.py")):
        scanned += 1
        for module_name in _imported_module_names(path):
            if any(module_name == prefix or module_name.startswith(prefix + ".") for prefix in FORBIDDEN_IMPORT_PREFIXES):
                violations.append(f"{path.as_posix()} imports forbidden module {module_name!r}")
    return {
        "ok": not violations, "scanned_files": scanned, "violations": violations,
        "evidence": f"static AST import scan of {dashboard_src}",
    }


def check_dashboard_solver_isolation(
    dashboard_src_path: Optional[str], claim: Optional[DashboardIsolationInput]
) -> List[Finding]:
    findings: List[Finding] = []
    scan_result = None
    if dashboard_src_path is not None:
        scan_result = scan_dashboard_source(Path(dashboard_src_path))
        if scan_result["ok"] is None:
            findings.append(Finding(
                "dashboard_solver_isolation", "warning",
                f"dashboard source path {dashboard_src_path!r} does not exist -- could not independently scan",
                "dashboard_src_path",
            ))
        elif scan_result["ok"] is False:
            findings.append(Finding(
                "dashboard_solver_isolation", "blocking",
                f"independent scan found {len(scan_result['violations'])} forbidden import(s) in dashboard source",
                scan_result["evidence"], detail="; ".join(scan_result["violations"]),
            ))
        else:
            findings.append(Finding(
                "dashboard_solver_isolation", "info",
                f"independent scan of {scan_result['scanned_files']} file(s) found no forbidden imports",
                scan_result["evidence"],
            ))
    else:
        findings.append(Finding(
            "dashboard_solver_isolation", "warning",
            "no dashboard_src_path supplied -- this audit could not independently verify isolation",
            "dashboard_src_path (absent)",
        ))

    if claim is not None and claim.claimed_ok is not None and scan_result is not None and scan_result["ok"] is not None:
        if claim.claimed_ok != scan_result["ok"]:
            findings.append(Finding(
                "dashboard_solver_isolation", "blocking",
                f"external claim ({claim.claim_source!r}) says isolation ok={claim.claimed_ok}, but this "
                f"audit's own independent scan found ok={scan_result['ok']} -- the claim is not trusted "
                "on its own and this divergence is reported, not silently resolved in the claim's favor",
                claim.claim_source,
            ))
    return findings
