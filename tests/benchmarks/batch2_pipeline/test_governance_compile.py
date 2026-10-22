"""Governance phrase scan, compilation, and owned-path hygiene."""
from __future__ import annotations

import ast
import json
from pathlib import Path

from tools.benchmarks.batch2_pipeline.harness import run_all
from tools.benchmarks.batch2_pipeline.schema import (
    FORBIDDEN_PHRASES,
    OWNED_PATH_PREFIXES,
    PROTECTED_PATH_PREFIXES,
)
from tools.benchmarks.batch2_pipeline.budgets import ResourceBudgets

REPO_ROOT = Path(__file__).resolve().parents[3]
OWNED = [
    REPO_ROOT / "tools" / "benchmarks" / "batch2_pipeline",
    REPO_ROOT / "scripts" / "benchmark_batch2_pipeline.py",
    REPO_ROOT / "tests" / "benchmarks" / "batch2_pipeline",
    REPO_ROOT / "docs" / "performance" / "batch2_pipeline_benchmarks.md",
]


def test_owned_paths_declared():
    assert "tools/benchmarks/batch2_pipeline/" in OWNED_PATH_PREFIXES
    assert "tools/streaming/" in PROTECTED_PATH_PREFIXES
    assert "apps/awareness_studio/" in PROTECTED_PATH_PREFIXES


def test_no_forbidden_phrases_in_owned_sources():
    # schema.py defines the denylist itself; skip that file.
    skip_names = {"schema.py"}
    for root in OWNED:
        paths = [root] if root.is_file() else list(root.rglob("*"))
        for path in paths:
            if path.is_file() and path.suffix in {".py", ".md"} and path.name not in skip_names:
                text = path.read_text(encoding="utf-8").lower()
                for phrase in FORBIDDEN_PHRASES:
                    assert phrase not in text, f"{path}: {phrase}"


def test_report_governance_clean():
    report = run_all(ResourceBudgets(max_workers=1), seed=0, size=8, repetitions=1)
    blob = json.dumps(report).lower()
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in blob
    assert report["evidence_class"] == "performance_only"
    assert report["synthetic"] is True


def test_owned_python_compiles():
    py_files = list((REPO_ROOT / "tools" / "benchmarks" / "batch2_pipeline").glob("*.py"))
    py_files.append(REPO_ROOT / "scripts" / "benchmark_batch2_pipeline.py")
    for path in py_files:
        ast.parse(path.read_text(encoding="utf-8"))


def test_no_production_imports_in_workloads():
    src = (REPO_ROOT / "tools" / "benchmarks" / "batch2_pipeline" / "workloads.py").read_text(
        encoding="utf-8"
    )
    forbidden = (
        "tools.streaming",
        "tools.data_access",
        "apps.awareness_studio",
        "core.topology",
        "sim.",
    )
    for token in forbidden:
        assert token not in src
