"""Guardrail: no dashboard-side solver execution.

Static import-scan over apps/awareness_studio's source tree: no file there
may import a solver/falsification/simulation module directly, and nothing
under tools/integration_bridge or scripts/assemble_ecosystem_run.py may be
imported from the dashboard app either (the dashboard consumes exported
Markdown/JSON artifacts, per CLAUDE.md's documented RAG pipeline flow --
`inputs/` -> loader -> chunking -> index -> retrieval -> llm_client -- it
never imports a solver to compute a result live). This is a static check
(source text, not a running interpreter), so it holds even for files this
suite cannot execute (e.g. anything requiring FastAPI/uvicorn).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_DASHBOARD_SRC = _ROOT / "apps" / "awareness_studio" / "src"

# Modules that perform live scientific computation / solver execution.
# Importing any of these directly from dashboard code would mean the
# dashboard could trigger a live solver run from an API route, which the
# guardrail forbids outright.
FORBIDDEN_IMPORT_PREFIXES = (
    "sim.pitnn",
    "physics.exact_dynamics",
    "core.topology",
    "analysis.connectivity_topology",
    "tools.integration_bridge",
    "scripts.assemble_ecosystem_run",
    "governance",
)


def _iter_dashboard_python_files():
    if not _DASHBOARD_SRC.exists():
        pytest.skip(f"{_DASHBOARD_SRC} not present in this checkout")
    yield from _DASHBOARD_SRC.rglob("*.py")


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


def test_dashboard_source_exists_and_is_scanned():
    files = list(_iter_dashboard_python_files())
    assert files, "expected at least one .py file under apps/awareness_studio/src"


def test_no_dashboard_file_imports_a_solver_or_integration_bridge_module():
    violations: list[str] = []
    for path in _iter_dashboard_python_files():
        for module_name in _imported_module_names(path):
            if any(
                module_name == prefix or module_name.startswith(prefix + ".")
                for prefix in FORBIDDEN_IMPORT_PREFIXES
            ):
                violations.append(f"{path.relative_to(_ROOT)} imports forbidden module {module_name!r}")
    assert not violations, "\n".join(violations)


def test_integration_bridge_does_not_import_the_dashboard_app():
    """The dependency direction is one-way: the integration bridge and its
    tests may read exported artifacts the dashboard also reads, but must
    never import awareness_studio's own web/app code (which would be a
    hidden coupling in the wrong direction and a route to accidental
    network/FastAPI side effects during a plain analysis run)."""
    bridge_root = _ROOT / "tools" / "integration_bridge"
    assembler = _ROOT / "scripts" / "assemble_ecosystem_run.py"
    violations: list[str] = []
    for path in list(bridge_root.rglob("*.py")) + [assembler]:
        if not path.exists():
            continue
        for module_name in _imported_module_names(path):
            if module_name.startswith("awareness_studio") or module_name.startswith("apps.awareness_studio"):
                violations.append(f"{path.relative_to(_ROOT)} imports dashboard module {module_name!r}")
    assert not violations, "\n".join(violations)
