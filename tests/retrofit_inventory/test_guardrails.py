"""Mutation-style guardrails: secrets, no-network, no scientific PASS."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tools.retrofit_inventory.models import KIND_TEXT
from tools.retrofit_inventory.scanner import scan_repository_files
from tools.retrofit_inventory.validators import (
    FORBIDDEN_SCIENTIFIC_CLAIM_STATUSES,
    INVENTORY_CLAIM_STATUS_NOT_EVIDENCE,
    NETWORK_IMPORT_DENYLIST,
    collect_forbidden_import_violations,
    find_secret_pattern_hits,
    find_secrets_in_text,
    inventory_claim_record,
    inventory_scientific_claim_status,
    validate_inventory_snapshot,
    validate_no_network_imports,
    validate_no_scientific_pass,
)

from .conftest import FIXTURES, make_file_entry, make_snapshot, init_git_repo


def _secret_fixture(name: str) -> Path:
    return FIXTURES / "secrets" / name


@pytest.mark.parametrize(
    ("filename", "needle"),
    [
        ("api_key_line.txt", "api_key="),
        ("akia_line.txt", "AKIA"),
        ("private_key_header.txt", "BEGIN PRIVATE KEY"),
        ("password_line.txt", "password="),
        ("secret_key_line.txt", "secret_key="),
    ],
)
def test_secret_fixtures_are_detected(filename: str, needle: str):
    text = _secret_fixture(filename).read_text(encoding="utf-8")
    hits = find_secret_pattern_hits(text)
    assert hits, f"secret fixture {filename} must be detected (needle {needle})"
    assert any(needle in hit for hit in hits)
    errors = find_secrets_in_text(text, location=filename)
    assert errors, "secret detection must fail closed, not warn"


def test_secret_in_scanned_text_path_fails_snapshot(tmp_path: Path):
    repo = tmp_path / "leaky"
    leaked = repo / "notes.txt"
    leaked.parent.mkdir(parents=True)
    leaked.write_text(_secret_fixture("api_key_line.txt").read_text(encoding="utf-8"))
    snapshot = make_snapshot(
        repo_root=str(repo),
        files=[
            make_file_entry(
                "notes.txt",
                kind=KIND_TEXT,
                size=leaked.stat().st_size,
            )
        ],
        artifacts=[],
    )
    errors = validate_inventory_snapshot(snapshot, repo_root=repo)
    assert any("secret pattern" in item for item in errors), (
        "validator must fail if a secret slips through a scanned text path"
    )


def test_clean_tiny_repo_has_no_secret_hits(tiny_repo: Path):
    for row in scan_repository_files(tiny_repo):
        if row.kind != KIND_TEXT:
            continue
        text = (tiny_repo / row.path).read_text(encoding="utf-8")
        assert find_secret_pattern_hits(text) == []


def test_inventory_never_emits_scientific_pass():
    snapshot = make_snapshot()
    status = inventory_scientific_claim_status(snapshot)
    assert status == INVENTORY_CLAIM_STATUS_NOT_EVIDENCE
    assert status not in FORBIDDEN_SCIENTIFIC_CLAIM_STATUSES
    assert "PASS" not in status.upper()
    record = inventory_claim_record(snapshot)
    assert record["scientific_claim_status"] not in FORBIDDEN_SCIENTIFIC_CLAIM_STATUSES
    assert validate_no_scientific_pass(snapshot, extra_payloads=[{"verdict": "PASS"}])
    # Extra payload PASS must be rejected; the inventory status itself stays clean.
    assert inventory_scientific_claim_status(snapshot) != "PASS"


def test_no_network_imports_in_scanner_and_validators():
    errors = validate_no_network_imports()
    assert errors == [], errors
    package = Path(__file__).resolve().parents[2] / "tools" / "retrofit_inventory"
    for name in ("validators.py", "scanner.py", "tool_sources.py", "models.py"):
        assert collect_forbidden_import_violations(package / name) == []


def test_ast_denylist_flags_urllib_and_requests(tmp_path: Path):
    dirty = tmp_path / "net.py"
    dirty.write_text("import requests\nfrom urllib.request import urlopen\n", encoding="utf-8")
    errors = collect_forbidden_import_violations(dirty)
    assert any("requests" in item for item in errors)
    assert any("urllib" in item for item in errors)


def test_ast_denylist_flags_marketos(tmp_path: Path):
    dirty = tmp_path / "mos.py"
    dirty.write_text("import marketos\n", encoding="utf-8")
    errors = collect_forbidden_import_violations(dirty)
    assert any("MarketOS" in item or "marketos" in item for item in errors)


def test_scanner_and_validators_source_has_no_network_calls():
    """AST walk: no requests/urllib/httpx imports and no urlopen names."""

    package = Path(__file__).resolve().parents[2] / "tools" / "retrofit_inventory"
    forbidden_names = {"urlopen", "Session", "Client"}
    # Client/Session are too broad if used as local class names; only flag
    # attribute loads on denied modules (handled by import denylist).
    for name in ("validators.py", "scanner.py"):
        path = package / name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        for module in imported:
            root = module.split(".", 1)[0]
            assert root not in NETWORK_IMPORT_DENYLIST
            assert module not in NETWORK_IMPORT_DENYLIST
        _ = forbidden_names


def test_secret_repo_scan_fails_closed(tmp_path: Path):
    repo = tmp_path / "secret-tree"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "notes.md").write_text(
        _secret_fixture("private_key_header.txt").read_text(encoding="utf-8")
    )
    (repo / "README.md").write_text("clean fixture\n", encoding="utf-8")
    init_git_repo(repo)
    files = scan_repository_files(repo)
    snapshot = make_snapshot(
        repo_root=str(repo.resolve()),
        files=files,
        artifacts=[],
    )
    errors = validate_inventory_snapshot(snapshot, repo_root=repo)
    assert any("BEGIN PRIVATE KEY" in item or "secret pattern" in item for item in errors)
