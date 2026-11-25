"""CLI and Makefile-facing entry points. Offline only."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


validate_main = _load_script("validate_evidence_promotion.py").main
generate_main = _load_script("generate_evidence_promotion_report.py").main

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_validate_cli_writes_strict_json(tmp_path: Path):
    out = tmp_path / "epg-out.json"
    code = validate_main(["--input", str(FIXTURES), "--output", str(out)])
    assert code in {0, 1}
    payload = json.loads(out.read_text(encoding="utf-8"), parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))
    assert payload["scientific_pass"] is False
    assert payload["schema_version"] == "EvidencePromotionGate.v1"
    assert payload["case_count"] >= 15
    assert "NaN" not in out.read_text(encoding="utf-8")


def test_validate_cli_blocks_when_promotion_is_unsafe(tmp_path: Path):
    out = tmp_path / "blocked.json"
    code = validate_main(["--input", str(FIXTURES / "airtable_empirical_pass"), "--output", str(out)])
    assert code == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["results"][0]["promotion_decision"] == "BLOCK_PROMOTION"


def test_generate_cli_writes_report_command_center_and_rag(tmp_path: Path):
    out = tmp_path / "generated"
    code = generate_main(["--input", str(FIXTURES), "--output", str(out)])
    assert code == 0
    assert (out / "report.json").exists()
    assert (out / "report.md").exists()
    assert (out / "command_center" / "evidence_promotion_status.json").exists()
    assert (out / "rag_pack" / "rag_pack.json").exists()
    rag = json.loads((out / "rag_pack" / "rag_pack.json").read_text(encoding="utf-8"))
    assert rag["scientific_pass"] is False
    assert "empirical confirmation" in rag["public_answer_guidelines"].lower() or "empirical" in rag["forbidden_answer_patterns"][3]
