"""Structural guarantee: no module in tools/release_scientific_audit
imports anything network/filesystem-execution-capable, and none of them
imports the forbidden sibling packages this branch must not depend on
(sim/pitnn, tools/integration_reconciliation, governance/merge_gate)."""
from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE = _ROOT / "tools" / "release_scientific_audit"

FORBIDDEN_MODULE_IMPORTS: tuple[str, ...] = ("socket", "requests", "urllib", "http", "subprocess")
FORBIDDEN_PACKAGE_DEPENDENCIES: tuple[str, ...] = (
    "sim.pitnn",
    "tools.integration_reconciliation",
    "tools.integration_bridge",
    "governance.merge_gate",
)


def _imported_module_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_package_files_exist():
    files = list(_PACKAGE.glob("*.py"))
    assert len(files) >= 8


def test_no_network_or_subprocess_imports_anywhere_in_the_package():
    violations: list[str] = []
    for path in _PACKAGE.glob("*.py"):
        imported = _imported_module_names(path)
        for name in imported:
            top_level = name.split(".")[0]
            if top_level in FORBIDDEN_MODULE_IMPORTS:
                violations.append(f"{path.name} imports {name!r}")
    assert not violations, violations


def test_no_dependency_on_forbidden_sibling_packages():
    violations: list[str] = []
    for path in _PACKAGE.glob("*.py"):
        imported = _imported_module_names(path)
        for name in imported:
            if any(name == prefix or name.startswith(prefix + ".") for prefix in FORBIDDEN_PACKAGE_DEPENDENCIES):
                violations.append(f"{path.name} imports {name!r}")
    assert not violations, violations


def test_cli_script_also_has_no_forbidden_dependency():
    script = _ROOT / "scripts" / "audit_integrated_release.py"
    imported = _imported_module_names(script)
    violations = [
        name for name in imported
        if any(name == prefix or name.startswith(prefix + ".") for prefix in FORBIDDEN_PACKAGE_DEPENDENCIES)
    ]
    assert not violations, violations
