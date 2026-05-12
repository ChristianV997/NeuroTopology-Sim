"""Tests for tools/build_awareness_rag_manifest.py and
sciencer_d/btc_icft/rag/artifact_manifest.py (P20.0).

32 tests — stdlib only, no network access required.
"""

from __future__ import annotations

import csv
import datetime
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Module loaders
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent.parent

CLI_PATH = REPO_ROOT / "tools" / "build_awareness_rag_manifest.py"
MOD_PATH = REPO_ROOT / "sciencer_d" / "btc_icft" / "rag" / "artifact_manifest.py"

REQUIRED_OUTPUTS = [
    "rag_artifact_manifest.jsonl",
    "rag_artifact_manifest.json",
    "rag_index_priority.csv",
    "rag_ingestion_plan.md",
    "quarantined_artifacts.json",
    "omega_event.json",
    "report.md",
]


def _load_mod():
    module_name = "sciencer_d.btc_icft.rag.artifact_manifest"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI_PATH)] + args,
        capture_output=True,
        text=True,
    )


def _run_mock(out_dir: Path) -> subprocess.CompletedProcess:
    return _run_cli(["--mock-fixture", "--out", str(out_dir)])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_01_help_exits_zero():
    result = _run_cli(["--help"])
    assert result.returncode == 0


def test_02_mock_fixture_exits_zero(tmp_path):
    out = tmp_path / "out"
    result = _run_mock(out)
    assert result.returncode == 0


def test_03_mock_fixture_writes_all_seven_outputs(tmp_path):
    out = tmp_path / "out"
    _run_mock(out)
    for name in REQUIRED_OUTPUTS:
        assert (out / name).exists(), f"missing: {name}"


def test_04_manifest_jsonl_one_row_per_artifact(tmp_path):
    out = tmp_path / "out"
    _run_mock(out)
    jsonl_path = out / "rag_artifact_manifest.jsonl"
    rows = [json.loads(line) for line in jsonl_path.read_text().splitlines() if line.strip()]
    manifest = json.loads((out / "rag_artifact_manifest.json").read_text())
    assert len(rows) == manifest["counts"]["total"]


def test_05_manifest_json_parses(tmp_path):
    out = tmp_path / "out"
    _run_mock(out)
    data = json.loads((out / "rag_artifact_manifest.json").read_text())
    assert "artifacts" in data
    assert "counts" in data


def test_06_priority_csv_has_required_columns(tmp_path):
    out = tmp_path / "out"
    _run_mock(out)
    with (out / "rag_index_priority.csv").open(newline="") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
    required_cols = [
        "artifact_id", "relative_path", "stage", "dataset_id",
        "evidence_state", "claim_safety_status", "index_priority",
        "recommended_rag_mode", "next_action",
    ]
    for col in required_cols:
        assert col in header, f"missing column: {col}"


def test_07_report_md_contains_cautious_terms(tmp_path):
    out = tmp_path / "out"
    _run_mock(out)
    text = (out / "report.md").read_text().lower()
    assert "candidate" in text or "proxy" in text


def test_08_report_md_no_banned_phrases(tmp_path):
    mod = _load_mod()
    out = tmp_path / "out"
    _run_mock(out)
    text = (out / "report.md").read_text().lower()
    for phrase in mod.BANNED_PHRASES:
        assert phrase not in text, f"banned phrase found in report.md: {phrase!r}"


def test_09_omega_event_no_external_api(tmp_path):
    out = tmp_path / "out"
    _run_mock(out)
    data = json.loads((out / "omega_event.json").read_text())
    assert data["no_external_api_called"] is True


def test_10_omega_event_no_embeddings(tmp_path):
    out = tmp_path / "out"
    _run_mock(out)
    data = json.loads((out / "omega_event.json").read_text())
    assert data["no_embeddings_created"] is True


def test_11_markdown_artifact_summarized(tmp_path):
    mod = _load_mod()
    md_file = tmp_path / "signal_report.md"
    md_file.write_text("# Signal Report\n\ncandidate proxy metric output.\n", encoding="utf-8")
    records = mod.scan_artifacts(tmp_path)
    found = [r for r in records if r.relative_path.endswith(".md")]
    assert found, "no .md artifact found"
    assert found[0].summary != ""


def test_12_json_artifact_summarized(tmp_path):
    mod = _load_mod()
    json_file = tmp_path / "omega_event.json"
    json_file.write_text(
        json.dumps({"safe_claim": "test", "extraction_ready": True}), encoding="utf-8"
    )
    records = mod.scan_artifacts(tmp_path)
    found = [r for r in records if r.relative_path.endswith(".json")]
    assert found, "no .json artifact found"
    assert found[0].summary != ""


def test_13_csv_artifact_summarized(tmp_path):
    mod = _load_mod()
    csv_file = tmp_path / "metrics.csv"
    csv_file.write_text("col_a,col_b,col_c\n1,2,3\n4,5,6\n", encoding="utf-8")
    records = mod.scan_artifacts(tmp_path)
    found = [r for r in records if r.relative_path.endswith(".csv")]
    assert found, "no .csv artifact found"
    assert "columns" in found[0].summary


def test_14_yaml_artifact_summarized(tmp_path):
    mod = _load_mod()
    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("dataset_scope: test\npipeline_id: p20_test\n", encoding="utf-8")
    records = mod.scan_artifacts(tmp_path)
    found = [r for r in records if r.relative_path.endswith(".yaml")]
    assert found, "no .yaml artifact found"
    assert found[0].summary != ""


def test_15_stage_inference_target_aware_activation():
    mod = _load_mod()
    path = Path("outputs/btc_icft/target_aware_activation/activation_smoke_summary.json")
    assert mod.infer_stage(path) == "target_aware_activation"


def test_16_stage_inference_eeg_signal_mt():
    mod = _load_mod()
    path = Path("outputs/btc_icft/eeg_signal_mt/metrics_signal_mt.json")
    assert mod.infer_stage(path) == "eeg_signal_mt"


def test_17_stage_inference_ds005620_contract_activation():
    mod = _load_mod()
    path = Path("outputs/btc_icft/ds005620_contract_activation/report.md")
    assert mod.infer_stage(path) == "ds005620_contract_activation"


def test_18_dataset_inference_DS005620():
    mod = _load_mod()
    path = Path("outputs/btc_icft/eeg_labels/DS005620/label_alignment_report.json")
    assert mod.infer_dataset_id(path) == "DS005620"


def test_19_evidence_state_mock_fixture():
    mod = _load_mod()
    path = Path("mock_fixtures/report.md")
    # We need a real path for stat(); use a temp approach via content snippet
    state = mod.infer_evidence_state(path, "mock fixture only content")
    assert state == "mock_fixture"


def test_20_banned_phrase_artifact_quarantined(tmp_path):
    mod = _load_mod()
    bad_file = tmp_path / "bad_report.md"
    # Contains a banned phrase (in test content only, not prose)
    bad_file.write_text(
        "# Report\n\nThis is a test file. eeg proves consciousness statement.\n",
        encoding="utf-8",
    )
    records = mod.scan_artifacts(tmp_path)
    found = [r for r in records if "bad_report" in r.relative_path]
    assert found, "bad_report.md not found in scan"
    assert found[0].claim_safety_status == "quarantined_banned_phrase"


def test_21_quarantined_in_quarantined_json(tmp_path):
    out = tmp_path / "out"
    mod = _load_mod()
    bad_file = tmp_path / "source" / "bad.md"
    bad_file.parent.mkdir(parents=True)
    bad_file.write_text(
        "# Test\neeg proves consciousness claim here.\n", encoding="utf-8"
    )
    records = mod.scan_artifacts(bad_file.parent)
    mod.write_outputs(records, out, bad_file.parent, datetime.datetime.now(datetime.timezone.utc).isoformat())
    data = json.loads((out / "quarantined_artifacts.json").read_text())
    quarantined_paths = [a["relative_path"] for a in data["quarantined_artifacts"]]
    assert any("bad.md" in p for p in quarantined_paths)


def test_22_safe_artifact_has_status_safe(tmp_path):
    mod = _load_mod()
    safe_file = tmp_path / "safe_report.md"
    safe_file.write_text(
        "# Safe Report\n\nAll metrics are candidate proxies only.\n", encoding="utf-8"
    )
    records = mod.scan_artifacts(tmp_path)
    found = [r for r in records if "safe_report" in r.relative_path]
    assert found, "safe_report.md not found"
    assert found[0].claim_safety_status == "safe"


def test_23_missing_root_exits_zero(tmp_path):
    out = tmp_path / "out"
    nonexistent = tmp_path / "does_not_exist"
    result = _run_cli(["--root", str(nonexistent), "--out", str(out)])
    assert result.returncode == 0
    assert (out / "omega_event.json").exists()


def test_24_max_artifacts_limits(tmp_path):
    mod = _load_mod()
    src = tmp_path / "src"
    src.mkdir()
    for i in range(5):
        (src / f"file_{i}.md").write_text(f"# File {i}\ncontent {i}\n", encoding="utf-8")
    records = mod.scan_artifacts(src, max_artifacts=2)
    assert len(records) == 2


def test_25_binary_files_skipped(tmp_path):
    mod = _load_mod()
    bin_file = tmp_path / "model.pkl"
    bin_file.write_bytes(bytes(range(256)))
    records = mod.scan_artifacts(tmp_path)
    assert not any("model.pkl" in r.relative_path for r in records)


def test_26_no_openai_notion_imports():
    cli_src = CLI_PATH.read_text()
    mod_src = MOD_PATH.read_text()
    for src, label in [(cli_src, "CLI"), (mod_src, "module")]:
        assert "import openai" not in src, f"{label} imports openai"
        assert "import notion" not in src, f"{label} imports notion"
        assert "from openai" not in src, f"{label} from-imports openai"
        assert "from notion" not in src, f"{label} from-imports notion"


def test_27_p16_files_not_imported():
    cli_src = CLI_PATH.read_text()
    mod_src = MOD_PATH.read_text()
    for src in (cli_src, mod_src):
        assert "from sciencer_d.btc_icft.pipelines" not in src
        assert "import ds005620_contract_activation" not in src


def test_28_p19_files_not_imported():
    cli_src = CLI_PATH.read_text()
    mod_src = MOD_PATH.read_text()
    for src in (cli_src, mod_src):
        assert "import eeg_reader_preflight" not in src
        assert "from sciencer_d.btc_icft.pipelines" not in src


def test_29_p11_p12_p13_not_imported():
    cli_src = CLI_PATH.read_text()
    mod_src = MOD_PATH.read_text()
    forbidden = [
        "from sciencer_d.btc_icft.pipelines.run_eeg_level",
        "import run_eeg_level",
        "from pipelines.run_eeg",
        "import p11",
        "import p12",
        "import p13",
    ]
    for src in (cli_src, mod_src):
        for frag in forbidden:
            assert frag not in src, f"forbidden import fragment found: {frag!r}"


def test_30_legacy_mt_real_not_imported():
    cli_src = CLI_PATH.read_text()
    mod_src = MOD_PATH.read_text()
    for src in (cli_src, mod_src):
        assert "mt_real" not in src, "legacy mt_real reference found in source"


def test_31_recommended_first_batch_present(tmp_path):
    out = tmp_path / "out"
    _run_mock(out)
    plan = (out / "rag_ingestion_plan.md").read_text()
    assert "Highest Priority" in plan


def test_32_no_claim_promotion(tmp_path):
    out = tmp_path / "out"
    _run_mock(out)
    data = json.loads((out / "omega_event.json").read_text())
    assert data["no_claim_promotion"] is True
