"""Static (no-execution) check that dashboard routes never import or
execute a scientific solver.

Independent, self-contained implementation -- this module does not import
anything from tools/integration_bridge (PR #210's package): that package
belongs to a different, not-yet-merged branch this reconciliation must not
take a hard dependency on, and this check needs to work standalone against
whatever `apps/awareness_studio/src` looks like on the target ref, which
may or may not have PR #210 merged into it yet.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional

# Modules a dashboard route must never import directly, because doing so
# would let an HTTP request trigger a live scientific computation instead
# of reading an already-exported artifact.
FORBIDDEN_IMPORT_PREFIXES: tuple[str, ...] = (
    "sim.pitnn",
    "physics.exact_dynamics",
    "core.topology",
    "analysis.connectivity_topology",
    "governance",
    "shared.interop",
    "tools.integration_bridge",
    "tools.integration_reconciliation",
    "scripts.assemble_ecosystem_run",
    "scripts.verify_integration_reconciliation",
)


def _imported_module_names(source_path: Path) -> set[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def check_dashboard_isolation(
    dashboard_src: Path,
    forbidden_prefixes: tuple[str, ...] = FORBIDDEN_IMPORT_PREFIXES,
) -> dict:
    """Scan every .py file under ``dashboard_src`` for a forbidden import.
    Returns a strict-JSON-ready dict; ``ok`` is None (not False) when the
    directory does not exist, since "no dashboard source found" is not the
    same claim as "dashboard source was checked and is clean"."""
    if not dashboard_src.exists():
        return {
            "ok": None,
            "scanned_files": 0,
            "violations": [],
            "evidence": f"{dashboard_src} does not exist on this ref",
        }

    violations: list[str] = []
    scanned = 0
    for path in sorted(dashboard_src.rglob("*.py")):
        scanned += 1
        for module_name in _imported_module_names(path):
            if any(
                module_name == prefix or module_name.startswith(prefix + ".")
                for prefix in forbidden_prefixes
            ):
                violations.append(f"{path.as_posix()} imports forbidden module {module_name!r}")

    return {
        "ok": not violations,
        "scanned_files": scanned,
        "violations": violations,
        "evidence": f"static AST import scan of {dashboard_src}",
    }
