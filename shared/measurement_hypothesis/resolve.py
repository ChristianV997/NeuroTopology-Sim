"""Static resolution of implementation references.

Files are read as bytes and parsed with ``ast``. Nothing is imported or executed, so no
scientific dependency loads and no feature is computed. A reference resolves only if the
file lies inside the repository root after symlinks are followed.
"""
from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Optional


def repo_file(repo_root: Path, relative: object) -> Optional[Path]:
    """Return the repository file named by a relative path, or None if it is absent or escapes the root."""
    if not isinstance(relative, str) or not relative or "\x00" in relative or relative.startswith(("/", "\\")):
        return None
    if ".." in Path(relative).parts:
        return None
    root = Path(repo_root).resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse(path: Path) -> ast.Module:
    """Parse a file without executing it. Raises SyntaxError for unparseable source."""
    return ast.parse(path.read_bytes(), filename=str(path))


def top_level_function(tree: ast.Module, name: object) -> Optional[ast.FunctionDef]:
    """A function defined at module level. Nested definitions do not count."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def string_literals(node: ast.AST) -> set[str]:
    return {item.value for item in ast.walk(node) if isinstance(item, ast.Constant) and isinstance(item.value, str)}


def returned_literals(function: ast.AST) -> set[str]:
    """String constants inside a return statement. Docstrings and bare expressions do not count."""
    found: set[str] = set()
    for node in ast.walk(function):
        if isinstance(node, ast.Return) and node.value is not None:
            found |= string_literals(node.value)
    return found
