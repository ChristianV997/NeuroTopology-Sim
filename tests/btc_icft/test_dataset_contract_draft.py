from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from sciencer_d.btc_icft.labels.dataset_contract_draft import (
    _validate_safe_text,
    build_contract_draft_review_checklist,
    discover_adapter_plan_files,
    draft_contract_from_adapter_plan,
    draft_contracts_from_readiness_dir,
    load_adapter_readiness_summary,
    load_dataset_adapter_plan,
    write_contract_draft_outputs,
)


def _mk_readiness(tmp_path: Path) -> Path:
    rd = tmp_path / "readiness"; rd.mkdir()
    per = {
        "DS005620": {"dataset_id": "DS005620", "readiness_status": "ready_to_activate", "best_probe": {"candidate_label_columns": ["trial_type", "condition"], "unique_values": {"trial_type": ["x", "y"]}}},
        "DS002094": {"dataset_id": "DS002094", "readiness_status": "metadata_file_not_found", "best_probe": {}},
    }
    (rd / "adapter_readiness_summary.json").write_text(json.dumps({"per_dataset": per}), encoding="utf-8")
    (rd / "plan_ds.json").write_text(json.dumps({"dataset_id": "ds003816", "readiness_status": "insufficient_label_values", "best_probe": {"candidate_label_columns": ["label"], "unique_values": {"label": ["u"]}}}), encoding="utf-8")
    return rd


def test_loaders_and_discovery(tmp_path: Path):
    rd = _mk_readiness(tmp_path)
    assert "per_dataset" in load_adapter_readiness_summary(str(rd / "adapter_readiness_summary.json"))
    assert load_dataset_adapter_plan(str(rd / "plan_ds.json"))["dataset_id"] == "ds003816"
    assert len(discover_adapter_plan_files(str(rd))) == 1


def test_draft_rules():
    draft = draft_contract_from_adapter_plan("A", {"readiness_status": "ready_to_activate", "best_probe": {"candidate_label_columns": ["c1", "c2"], "unique_values": {"c1": ["p", "n"]}}})
    assert draft.status != "active"
    assert draft.positive_values == [] and draft.negative_values == []
    assert draft.unresolved_values == ["p", "n"]
    assert "human_must_choose_explicit_label_column" in draft.activation_blockers
    assert "human_must_declare_positive_and_negative_values" in draft.activation_blockers
    assert draft.join_keys == ["dataset_id", "row_id", "source_file", "window_id", "window_start_s", "window_end_s", "sample_start", "sample_end"]
    assert "declare positive_values" in draft.required_human_decisions


def test_blockers_and_checklist():
    d1 = draft_contract_from_adapter_plan("B", {"readiness_status": "metadata_file_not_found"})
    d2 = draft_contract_from_adapter_plan("C", {"readiness_status": "no_candidate_label_column"})
    assert "metadata_required" in d1.activation_blockers
    assert "explicit_label_column_required" in d2.activation_blockers
    ck = build_contract_draft_review_checklist(d1)
    assert ck["activation_allowed"] is False


def test_outputs_and_safety(tmp_path: Path):
    rd = _mk_readiness(tmp_path)
    result = draft_contracts_from_readiness_dir(str(rd))
    out = write_contract_draft_outputs(result, str(tmp_path / "out"))
    assert set(out) == {"contract_draft_summary.json", "contract_drafts.json", "human_review_checklists.json", "activation_blockers.json", "omega_event.json", "report.md"}
    summary = json.loads((tmp_path / "out" / "contract_draft_summary.json").read_text())
    assert "statuses" in summary
    drafts = json.loads((tmp_path / "out" / "contract_drafts.json").read_text())["drafts"]
    assert all(d["status"] != "active" for d in drafts)
    assert all(d["positive_values"] == [] and d["negative_values"] == [] for d in drafts)
    text = (tmp_path / "out" / "report.md").read_text().lower()
    assert "inactive p12 contract drafts" in text and "human review" in text and "without inferring labels or targets" in text
    for phrase in ["proves consciousness", "consciousness proven", "soul proven", "afterlife proven", "liberation detected", "ontology solved", "ultimate reality", "q equals self", "q equals soul", "q_abs equals suffering", "f_dress equals karma", "sedated implies no_experience", "unresponsive implies unconscious"]:
        assert phrase not in text
    _validate_safe_text(result.omega_event["safe_claim"])


def test_cli_missing_readiness(tmp_path: Path):
    proc = subprocess.run([sys.executable, "-m", "sciencer_d.btc_icft.pipelines.draft_dataset_label_contracts", "--readiness-dir", str(tmp_path / "none"), "--out", str(tmp_path / "o")], capture_output=True, text=True)
    assert proc.returncode != 0


def test_cli_mock_fixture(tmp_path: Path):
    out = tmp_path / "drafts"
    proc = subprocess.run([sys.executable, "-m", "sciencer_d.btc_icft.pipelines.draft_dataset_label_contracts", "--mock-fixture", "--out", str(out)], capture_output=True, text=True)
    assert proc.returncode == 0
    for n in ["contract_draft_summary.json", "contract_drafts.json", "human_review_checklists.json", "activation_blockers.json", "omega_event.json", "report.md"]:
        assert (out / n).exists()
    drafts = json.loads((out / "contract_drafts.json").read_text())["drafts"]
    assert {d["dataset_id"] for d in drafts} == {"DS005620", "DS002094", "ds001787", "ds003969", "ds003816", "PhysioNet_GABA"}


def test_no_forbidden_import_paths():
    src = Path("sciencer_d/btc_icft/labels/dataset_contract_draft.py").read_text() + Path("sciencer_d/btc_icft/pipelines/draft_dataset_label_contracts.py").read_text()
    assert "target_aware_activation" not in src
    assert "eeg_target_injection" not in src
    assert "mt_real" not in src
    assert " y " not in src


def test_config_contents():
    cfg = Path("configs/btc_icft/dataset_contract_drafts.yaml").read_text()
    assert "required_outputs" in cfg and "draft_statuses" in cfg and "guardrails" in cfg
