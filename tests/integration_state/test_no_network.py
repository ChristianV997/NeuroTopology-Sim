"""Structural guarantee: no module in tools/integration_state imports
anything network-capable, and none depends on the forbidden sibling
packages this branch must not touch."""
from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE = _ROOT / "tools" / "integration_state"

FORBIDDEN_MODULE_IMPORTS: tuple[str, ...] = ("socket", "requests", "urllib", "http")
FORBIDDEN_PACKAGE_DEPENDENCIES: tuple[str, ...] = (
    "tools.integration_reconciliation",
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


def test_package_has_expected_modules():
    files = {p.name for p in _PACKAGE.glob("*.py")}
    assert {"git_source.py", "github_source.py", "commit_classifier.py", "ci_classifier.py",
            "merge_verification.py", "state.py", "reporting.py", "models.py"} <= files


def test_no_network_imports_anywhere_in_the_package():
    violations = []
    for path in _PACKAGE.glob("*.py"):
        for name in _imported_module_names(path):
            if name.split(".")[0] in FORBIDDEN_MODULE_IMPORTS:
                violations.append(f"{path.name} imports {name!r}")
    assert not violations, violations


def test_no_dependency_on_forbidden_sibling_packages():
    violations = []
    for path in list(_PACKAGE.glob("*.py")) + [_ROOT / "scripts" / "verify_integration_state.py"]:
        if not path.exists():
            continue
        for name in _imported_module_names(path):
            if any(name == prefix or name.startswith(prefix + ".") for prefix in FORBIDDEN_PACKAGE_DEPENDENCIES):
                violations.append(f"{path.name} imports {name!r}")
    assert not violations, violations


def test_git_source_only_uses_read_only_subcommands():
    """git_source.py must not contain a mutating git verb as a literal
    string -- a cheap but effective guard against an accidental push/
    merge/rebase/checkout -b creeping in later."""
    source = (_PACKAGE / "git_source.py").read_text(encoding="utf-8")
    forbidden_verbs = ["\"push\"", "\"merge\"", "\"rebase\"", "\"checkout\", \"-b\"", "\"branch\", \"-d\"", "\"branch\", \"-D\""]
    violations = [verb for verb in forbidden_verbs if verb in source]
    assert not violations, violations
