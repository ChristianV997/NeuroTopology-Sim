"""Release-owned smoke tests for scripts/compile_repository_evidence.py.

QA owns tests/release/test_evidence_compiler.py. This file only checks that
the Release compiler consumes that contract. Inventory is not evidence.
Synthetic fixtures cannot establish scientific PASS.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from .evidence_validate import (
    MATRIX_PATH,
    SCHEMA_PATH,
    clone_doc,
    load_inventory,
    validate_compiled_report,
    validate_inventory,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPILER_PATH = REPO_ROOT / "scripts" / "compile_repository_evidence.py"


def _load_compiler():
    spec = importlib.util.spec_from_file_location(
        "compile_repository_evidence",
        COMPILER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


COMPILER = _load_compiler()


def test_compiler_script_exists_and_is_offline_source():
    text = COMPILER_PATH.read_text(encoding="utf-8")
    assert COMPILER_PATH.is_file()
    assert re.search(
        r"^\s*(import|from)\s+(requests|urllib|http\.client|httpx|aiohttp|github|ghapi|marketos)\b",
        text,
        re.M,
    ) is None
    assert "MarketOS" not in text
    assert "offline" in text.lower()


def test_live_matrix_compiles_and_validates():
    report = COMPILER.compile_report(
        repo_root=REPO_ROOT,
        generated_at="2026-09-06T00:00:00Z",
    )
    errors = validate_compiled_report(report)
    assert errors == [], errors
    assert report["kind"] == "compiled_report"
    assert report["schema_version"] == "1.0.0"
    assert report["inventory_is_not_evidence"] is True
    assert report["empirical_pass_from_this_pack"] is False
    assert report["release_recommendation"] == "BLOCKED_BY_SCIENTIFIC_VALIDATION"
    assert report["merger_instruction"] == "do_not_merge"
    assert len(report["contributions"]) == len(load_inventory()["contributions"])


def test_required_warnings_and_markdown_statements():
    report = COMPILER.compile_report(
        repo_root=REPO_ROOT,
        generated_at="2026-09-06T00:00:00Z",
    )
    blob = "\n".join(report["required_warnings"]).lower()
    for prn in ("210", "211", "212"):
        assert prn in blob
    assert "not merged" in blob
    assert "synthetic" in blob
    assert "pass" in blob
    assert "formal likelihood" in blob
    assert "falsification" in blob
    assert "antigravity" in blob
    assert "grok" in blob
    markdown = COMPILER.render_markdown(report)
    for phrase in (
        "Inventory is not evidence",
        "Synthetic data cannot establish a scientific PASS",
        "#210",
        "#211",
        "#212",
        "NOT merged",
        "formal likelihood",
        "no PR unless one is found",
        "Antigravity/Grok reports are unverified",
    ):
        assert phrase in markdown, phrase


def test_never_promotes_unverified_author_tests_to_pass():
    report = COMPILER.compile_report(
        repo_root=REPO_ROOT,
        generated_at="2026-09-06T00:00:00Z",
    )
    for row in report["contributions"]:
        status = row["verification_status"]
        assert status["scientific_pass"] not in {"pass", "claimed"}
        assert status["author_test_results"] == "unverified"
        assert row["test_results"] != "PASS"
        assert row["test_results"] != "pass"
        assert row["compiled_from_author_test_results"] is False
        assert row["tests_used_as_compiled_evidence"] is False
        for item in row["scientific_assertions"]:
            if isinstance(item, str):
                assert item.strip().lower() not in {"pass", "scientific_pass"}


def test_aliases_are_filled():
    report = COMPILER.compile_report(
        repo_root=REPO_ROOT,
        generated_at="2026-09-06T00:00:00Z",
    )
    for row in report["contributions"]:
        assert "pr" in row
        assert "changed_files" in row
        assert "test_results" in row
        assert "tests" in row
        assert "artifacts" in row
        assert "open_questions" in row
        assert "next_action" in row


def test_deterministic_with_frozen_generated_at():
    first = COMPILER.dumps_json(
        COMPILER.compile_report(
            repo_root=REPO_ROOT,
            generated_at="2026-09-06T00:00:00Z",
        )
    )
    second = COMPILER.dumps_json(
        COMPILER.compile_report(
            repo_root=REPO_ROOT,
            generated_at="2026-09-06T00:00:00Z",
        )
    )
    assert first == second
    payload = json.loads(first)
    assert payload["compiler"]["generated_at"] == "2026-09-06T00:00:00Z"


def test_invalid_inventory_fails_closed(tmp_path):
    broken = clone_doc(load_inventory())
    broken["inventory_is_not_evidence"] = False
    path = tmp_path / "broken_inventory.yaml"
    path.write_text(yaml.safe_dump(broken), encoding="utf-8")
    with pytest.raises(COMPILER.CompilerError) as caught:
        COMPILER.compile_report(repo_root=REPO_ROOT, matrix_path=path)
    assert caught.value.errors
    assert any("inventory_is_not_evidence" in item for item in caught.value.errors)


def test_cli_stdout_json_does_not_write_files(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(COMPILER_PATH),
            "--repo-root",
            str(REPO_ROOT),
            "--format",
            "json",
            "--generated-at",
            "2026-09-06T00:00:00Z",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert validate_compiled_report(report) == []
    assert report["release_recommendation"] == "BLOCKED_BY_SCIENTIFIC_VALIDATION"
    leftover = list(tmp_path.rglob("*"))
    assert leftover == [], leftover


def test_cli_write_requires_output(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(COMPILER_PATH),
            "--repo-root",
            str(REPO_ROOT),
            "--write",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "output" in result.stderr.lower()


def test_cli_output_dir_writes_when_requested(tmp_path):
    out = tmp_path / "compiled"
    result = subprocess.run(
        [
            sys.executable,
            str(COMPILER_PATH),
            "--repo-root",
            str(REPO_ROOT),
            "--format",
            "both",
            "--output-dir",
            str(out),
            "--generated-at",
            "2026-09-06T00:00:00Z",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    json_path = out / "compiled_repository_evidence.json"
    md_path = out / "compiled_repository_evidence.md"
    assert json_path.is_file()
    assert md_path.is_file()
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert validate_compiled_report(report) == []
    text = md_path.read_text(encoding="utf-8")
    assert "Inventory is not evidence" in text


def test_live_github_flag_is_refused():
    result = subprocess.run(
        [sys.executable, str(COMPILER_PATH), "--live"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "refused" in result.stderr.lower()


def test_inventory_still_passes_qa_validator():
    assert MATRIX_PATH.is_file()
    assert SCHEMA_PATH.is_file()
    assert validate_inventory(load_inventory()) == []
