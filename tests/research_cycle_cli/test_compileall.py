"""compileall: every module in the package and the CLI script must byte-compile cleanly."""
from __future__ import annotations

import compileall
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_package_compiles_cleanly(tmp_path):
    package_dir = _REPO_ROOT / "tools" / "research_cycle_cli"
    assert compileall.compile_dir(str(package_dir), quiet=1, ddir=str(tmp_path))


def test_cli_script_compiles_cleanly(tmp_path):
    cli_path = _REPO_ROOT / "scripts" / "inspect_research_cycle.py"
    assert compileall.compile_file(str(cli_path), quiet=1, ddir=str(tmp_path))
