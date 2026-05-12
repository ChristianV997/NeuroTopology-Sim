"""Tests for P20.1 ingestion pack builder CLI + module."""

from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
CLI_PATH = REPO_ROOT / "tools" / "build_awareness_rag_ingestion_pack.py"
MOD_PATH = REPO_ROOT / "sciencer_d" / "btc_icft" / "rag" / "ingestion_pack.py"

REQUIRED_OUTPUTS = [
    "rag_ingestion_chunks.jsonl",
    "rag_ingestion_pack.json",
    "rag_ingestion_index.csv",
    "withheld_or_quarantined_chunks.json",
    "omega_event.json",
    "report.md",
]


def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CLI_PATH)] + args, capture_output=True, text=True)


def _load_module():
    module_name = "sciencer_d.btc_icft.rag.ingestion_pack"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_help_exits_zero():
    result = _run_cli(["--help"])
    assert result.returncode == 0


def test_mock_fixture_writes_outputs(tmp_path):
    out = tmp_path / "out"
    result = _run_cli(["--mock-fixture", "--out", str(out)])
    assert result.returncode == 0
    for name in REQUIRED_OUTPUTS:
        assert (out / name).exists(), f"missing: {name}"


def test_mock_fixture_generates_chunks(tmp_path):
    out = tmp_path / "out"
    _run_cli(["--mock-fixture", "--out", str(out)])
    rows = [json.loads(line) for line in (out / "rag_ingestion_chunks.jsonl").read_text().splitlines() if line.strip()]
    assert len(rows) > 0


def test_chunk_has_required_fields(tmp_path):
    mod = _load_module()
    out = tmp_path / "out"
    _run_cli(["--mock-fixture", "--out", str(out)])
    first = json.loads((out / "rag_ingestion_chunks.jsonl").read_text().splitlines()[0])
    for field in mod.CHUNK_FIELDS:
        assert field in first


def test_missing_manifest_writes_empty_valid(tmp_path):
    out = tmp_path / "out"
    result = _run_cli([
        "--manifest", str(tmp_path / "does_not_exist.jsonl"),
        "--out", str(out),
    ])
    assert result.returncode == 0
    data = json.loads((out / "rag_ingestion_pack.json").read_text())
    assert "rag_manifest_missing" in data["blockers"]


def test_mock_has_quarantined_withheld_default(tmp_path):
    out = tmp_path / "out"
    _run_cli(["--mock-fixture", "--out", str(out)])
    withheld = json.loads((out / "withheld_or_quarantined_chunks.json").read_text())
    assert any(row["reason"] == "quarantined" for row in withheld["withheld_artifacts"])


def test_include_quarantined_sets_withhold_override(tmp_path):
    mod = _load_module()
    out = tmp_path / "out"
    _run_cli([
        "--mock-fixture",
        "--include-quarantined", "true",
        "--out", str(out),
    ])
    rows = [json.loads(line) for line in (out / "rag_ingestion_chunks.jsonl").read_text().splitlines() if line.strip()]
    quarantined = [r for r in rows if r["claim_safety_status"] != "safe"]
    assert quarantined
    assert all(not str(r["next_action"]).startswith(f"{mod.WITHHOLD_PREFIX}quarantined") for r in quarantined)


def test_priority_filter_withholds_high_priority_number(tmp_path):
    out = tmp_path / "out"
    _run_cli([
        "--mock-fixture",
        "--include-priority-max", "1",
        "--out", str(out),
    ])
    withheld = json.loads((out / "withheld_or_quarantined_chunks.json").read_text())
    assert any(row["reason"] == "priority_excluded" for row in withheld["withheld_artifacts"])


def test_chunk_role_detected_for_report_and_omega(tmp_path):
    out = tmp_path / "out"
    _run_cli(["--mock-fixture", "--out", str(out)])
    rows = [json.loads(line) for line in (out / "rag_ingestion_chunks.jsonl").read_text().splitlines() if line.strip()]
    by_path = {r["relative_path"]: r for r in rows}
    assert by_path["report.md"]["chunk_role"] == "report_summary"
    assert by_path["omega_event.json"]["chunk_role"] == "omega_event"


def test_retrieval_tags_include_dataset_prefix(tmp_path):
    out = tmp_path / "out"
    _run_cli(["--mock-fixture", "--out", str(out)])
    row = json.loads((out / "rag_ingestion_chunks.jsonl").read_text().splitlines()[0])
    assert any(tag.startswith("dataset:") for tag in row["retrieval_tags"])


def test_csv_has_expected_columns(tmp_path):
    out = tmp_path / "out"
    _run_cli(["--mock-fixture", "--out", str(out)])
    with (out / "rag_ingestion_index.csv").open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        cols = reader.fieldnames or []
    for required in ["chunk_id", "artifact_id", "relative_path", "chunk_role", "recommended_rag_mode"]:
        assert required in cols


def test_no_external_imports_present():
    cli_src = CLI_PATH.read_text(encoding="utf-8")
    mod_src = MOD_PATH.read_text(encoding="utf-8")
    banned_fragments = [
        "import openai",
        "from openai",
        "import notion",
        "langchain",
        "llamaindex",
        "faiss",
        "chroma",
        "pinecone",
    ]
    for src in (cli_src, mod_src):
        for fragment in banned_fragments:
            assert fragment not in src.lower()


def test_max_artifacts_limits_manifest_rows(tmp_path):
    out = tmp_path / "out"
    _run_cli(["--mock-fixture", "--max-artifacts", "2", "--out", str(out)])
    data = json.loads((out / "rag_ingestion_pack.json").read_text())
    assert data["counts"]["artifacts_seen"] == 2


@pytest.mark.parametrize(
    "flag,value",
    [
        ("--max-chars-per-chunk", "500"),
        ("--overlap-chars", "50"),
    ],
)
def test_chunking_flags_are_reflected(tmp_path, flag, value):
    out = tmp_path / "out"
    _run_cli(["--mock-fixture", flag, value, "--out", str(out)])
    data = json.loads((out / "rag_ingestion_pack.json").read_text())
    key = "max_chars_per_chunk" if flag == "--max-chars-per-chunk" else "overlap_chars"
    assert data["params"][key] == int(value)
