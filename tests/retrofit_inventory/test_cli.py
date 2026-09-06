"""Phase 5 Integration CLI smoke tests (offline only).

Does not edit QA validators.py or Release reporting.py.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from .conftest import REPO_ROOT

CLI_PATH = REPO_ROOT / "scripts" / "build_retrofit_inventory.py"
FROZEN_ISO = "2026-09-06T02:30:00+00:00"
EXPECTED_REPORTS = (
    "repository_inventory.json",
    "artifact_inventory.json",
    "tool_admission_inventory.json",
    "ownership_collision_report.json",
    "retrofit_priority_report.json",
    "scientific_claim_risk_report.json",
)


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "build_retrofit_inventory_cli",
        CLI_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _seed_tool_sources(tiny_repo: Path) -> None:
    dest = tiny_repo / "configs" / "retrofit_inventory"
    dest.mkdir(parents=True, exist_ok=True)
    src = REPO_ROOT / "configs" / "retrofit_inventory" / "tool_sources.yaml"
    (dest / "tool_sources.yaml").write_bytes(src.read_bytes())


def test_cli_rejects_missing_repo_root_and_traversal(tmp_path: Path, capsys):
    cli = _load_cli()
    missing = tmp_path / "does-not-exist"
    code = cli.main(["--repo-root", str(missing)])
    captured = capsys.readouterr()
    assert code == cli.EXIT_ERROR
    assert "does not exist" in captured.err

    code = cli.main(["--repo-root", "../outside"])
    captured = capsys.readouterr()
    assert code == cli.EXIT_ERROR
    assert "traversal" in captured.err

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    code = cli.main(
        [
            "--repo-root",
            str(repo),
            "--output-dir",
            "../escaped",
        ]
    )
    captured = capsys.readouterr()
    assert code == cli.EXIT_ERROR
    assert "traversal" in captured.err


def test_cli_rejects_output_outside_repo(tmp_path: Path, capsys):
    cli = _load_cli()
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside_bundle"
    code = cli.main(
        [
            "--repo-root",
            str(repo),
            "--output-dir",
            str(outside),
        ]
    )
    captured = capsys.readouterr()
    assert code == cli.EXIT_ERROR
    assert "must resolve under repo-root" in captured.err
    assert not outside.exists()


def test_cli_writes_offline_bundle_on_tiny_repo(tiny_repo: Path, capsys):
    cli = _load_cli()
    _seed_tool_sources(tiny_repo)
    out_rel = "artifacts/retrofit_inventory"
    code = cli.main(
        [
            "--repo-root",
            str(tiny_repo),
            "--output-dir",
            out_rel,
            "--offline",
            "--online",
            "--generated-at",
            FROZEN_ISO,
        ]
    )
    captured = capsys.readouterr()
    assert code == cli.EXIT_OK
    assert "status: ok" in captured.out
    assert "commit:" in captured.out
    for name in EXPECTED_REPORTS:
        assert name in captured.out
        path = tiny_repo / out_rel / name
        assert path.is_file(), name
    assert "--online is ignored" in captured.err
    assert "offline-only" in captured.err
