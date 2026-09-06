"""Release smoke tests for ``scripts/validate_pr_retirement_matrix.py``.

CLI wrapper only. Does not rewrite QA rules. Offline. No GitHub close/merge.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "validate_pr_retirement_matrix.py"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "pr_retirement"
MALFORMED = FIXTURE_DIR / "invented_pass.yaml"

_AST_DENIED_MODULES = frozenset(
    {
        "urllib.request",
        "urllib.client",
        "requests",
        "http.client",
        "httpx",
        "aiohttp",
        "socket",
        "ftplib",
        "smtplib",
        "subprocess",
        "github",
        "ghapi",
    }
)


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "validate_pr_retirement_matrix_cli", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_script_exists():
    assert SCRIPT.is_file()


def test_cli_live_matrix_exits_0(capsys):
    cli = _load_cli()
    assert cli.main([]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""


def test_cli_script_live_matrix_exits_0():
    proc = _run_script()
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_cli_malformed_fixture_exits_1(capsys):
    cli = _load_cli()
    code = cli.main(["--matrix", str(MALFORMED)])
    captured = capsys.readouterr()
    assert code == 1
    assert "invented_pass" in captured.out
    assert captured.out.strip() != ""
    for line in captured.out.strip().splitlines():
        assert line.strip()


def test_cli_script_malformed_fixture_exits_1():
    proc = _run_script("--matrix", str(MALFORMED))
    assert proc.returncode == 1
    assert "invented_pass" in proc.stdout


def test_cli_json_dump_errors_and_warnings(capsys):
    cli = _load_cli()
    code = cli.main(["--matrix", str(MALFORMED), "--json"])
    captured = capsys.readouterr()
    assert code == 1
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["errors"]
    assert any("invented_pass" in err for err in payload["errors"])
    assert payload["warnings"] == []
    assert "matrix" in payload


def test_cli_json_success_has_empty_lists(capsys):
    cli = _load_cli()
    code = cli.main(["--json"])
    captured = capsys.readouterr()
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["errors"] == []
    assert payload["warnings"] == []


def test_cli_default_matrix_is_qa_default():
    cli = _load_cli()
    args = cli.build_parser().parse_args([])
    assert Path(args.matrix) == cli.DEFAULT_MATRIX_PATH
    assert Path(args.matrix).as_posix().endswith(
        "configs/release/pr_retirement_matrix.yaml"
    )


def test_cli_wraps_qa_helpers_without_rewrite():
    text = SCRIPT.read_text(encoding="utf-8")
    for name in (
        "validate_path",
        "validate_pr_retirement_matrix",
        "run_validation",
        "DEFAULT_MATRIX_PATH",
    ):
        assert name in text
    assert "from pr_retirement_validate import" in text
    assert "def _check_research_locks" not in text
    assert "RETIRE_OR_MERGE_HINTS" not in text
    assert "CANONICAL_STACK_CHAINS" not in text
    assert "ALLOWED_PROXY_IDENTIFIERS" not in text


def test_cli_offline_no_github_close_or_merge():
    text = SCRIPT.read_text(encoding="utf-8")
    for token in (
        "urllib.request",
        "urllib.client",
        "requests.get",
        "http.client",
        "github",
        "ghapi",
        "pulls.merge",
        "do_not_merge",
    ):
        assert token not in text
    lowered = text.lower()
    assert "never close" in lowered or "no close" in lowered or "no close / merge" in lowered
    assert "merge(" not in text
    assert "close(" not in text


def test_cli_ast_denylist():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    offenders = [
        name
        for name in imported
        if name in _AST_DENIED_MODULES
        or any(name == denied or name.startswith(denied + ".") for denied in _AST_DENIED_MODULES)
    ]
    assert not offenders, offenders
