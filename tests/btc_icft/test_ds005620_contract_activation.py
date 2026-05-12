"""Tests for P16 — DS005620 human-reviewed label contract activation packet.

All tests use tmp_path only. No real dataset files required.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from sciencer_d.btc_icft.labels.ds005620_contract_activation import (
    DS005620ActivationProposal,
    DS005620ActivationResult,
    DS005620MetadataValueAuditRow,
    _BANNED_PHRASES,
    _SAFE_CLAIM,
    audit_metadata_values,
    build_activation_blockers,
    build_ds005620_activation_omega_event,
    build_human_review_packet,
    load_contract_drafts,
    load_metadata_rows,
    prepare_ds005620_activation_proposal,
    write_ds005620_activation_outputs,
)

DATASET_ID = "DS005620"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_tsv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


_STANDARD_ROWS = [
    {"trial_type": "focus", "condition": "A",
     "notes": "free text note", "filename": "/data/sub-01.set"},
    {"trial_type": "mind_wandering", "condition": "B",
     "notes": "another note", "filename": "/data/sub-01.set"},
    {"trial_type": "focus", "condition": "A",
     "notes": "n/a", "filename": "/data/sub-02.set"},
    {"trial_type": "mind_wandering", "condition": "B",
     "notes": "ok", "filename": "/data/sub-02.set"},
]

_SINGLE_VALUE_ROWS = [
    {"trial_type": "focus", "condition": "A"},
    {"trial_type": "focus", "condition": "A"},
]


def _make_result(rows=None, drafts=None) -> DS005620ActivationResult:
    if rows is None:
        rows = _STANDARD_ROWS
    return prepare_ds005620_activation_proposal(rows, drafts)


# ---------------------------------------------------------------------------
# Test 1–4: load_metadata_rows format support
# ---------------------------------------------------------------------------

class TestLoadMetadataRows:
    def test_reads_csv(self, tmp_path):
        p = tmp_path / "events.csv"
        _write_csv(p, _STANDARD_ROWS)
        rows = load_metadata_rows(str(p))
        assert len(rows) == 4

    def test_reads_tsv(self, tmp_path):
        p = tmp_path / "events.tsv"
        _write_tsv(p, _STANDARD_ROWS)
        rows = load_metadata_rows(str(p))
        assert len(rows) == 4

    def test_reads_json_list(self, tmp_path):
        p = tmp_path / "meta.json"
        p.write_text(json.dumps(_STANDARD_ROWS), encoding="utf-8")
        rows = load_metadata_rows(str(p))
        assert len(rows) == 4

    def test_reads_json_rows_dict(self, tmp_path):
        p = tmp_path / "meta.json"
        p.write_text(json.dumps({"rows": _STANDARD_ROWS}), encoding="utf-8")
        rows = load_metadata_rows(str(p))
        assert len(rows) == 4

    def test_unsupported_extension_raises_value_error(self, tmp_path):
        p = tmp_path / "meta.xlsx"
        p.write_bytes(b"not real xlsx")
        with pytest.raises(ValueError, match="Unsupported"):
            load_metadata_rows(str(p))

    def test_missing_file_raises_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_metadata_rows(str(tmp_path / "nonexistent.csv"))


# ---------------------------------------------------------------------------
# Tests 7–10: audit_metadata_values column classification
# ---------------------------------------------------------------------------

class TestAuditMetadataValues:
    def test_identifies_binary_candidate_column(self):
        rows = _STANDARD_ROWS
        audit = audit_metadata_values(rows)
        trial_type_row = next(r for r in audit if r.column == "trial_type")
        assert trial_type_row.binary_candidate is True

    def test_rejects_free_text_notes_column(self):
        rows = _STANDARD_ROWS
        audit = audit_metadata_values(rows)
        notes_row = next(r for r in audit if r.column == "notes")
        assert notes_row.binary_candidate is False
        assert notes_row.likely_label_candidate is False
        assert notes_row.rejected_reason is not None

    def test_rejects_file_path_column(self):
        rows = _STANDARD_ROWS
        audit = audit_metadata_values(rows)
        file_row = next(r for r in audit if r.column == "filename")
        assert file_row.binary_candidate is False
        assert file_row.rejected_reason is not None

    def test_rejects_single_value_column(self):
        rows = _SINGLE_VALUE_ROWS
        audit = audit_metadata_values(rows)
        trial_row = next(r for r in audit if r.column == "trial_type")
        assert trial_row.binary_candidate is False
        assert trial_row.rejected_reason == "single_value_only"

    def test_returns_list_of_audit_rows(self):
        audit = audit_metadata_values(_STANDARD_ROWS)
        assert isinstance(audit, list)
        assert all(isinstance(r, DS005620MetadataValueAuditRow) for r in audit)

    def test_empty_rows_returns_empty_audit(self):
        audit = audit_metadata_values([])
        assert audit == []


# ---------------------------------------------------------------------------
# Tests 11–16: proposal invariants
# ---------------------------------------------------------------------------

class TestProposalInvariants:
    def test_contract_activation_never_true(self):
        result = _make_result()
        assert result.activation_proposal["contract_activation_allowed"] is False

    def test_positive_values_always_empty(self):
        result = _make_result()
        assert result.activation_proposal["positive_values"] == []

    def test_negative_values_always_empty(self):
        result = _make_result()
        assert result.activation_proposal["negative_values"] == []

    def test_candidate_values_go_to_unresolved_only(self):
        result = _make_result()
        proposal = result.activation_proposal
        unresolved = proposal["unresolved_values"]
        # Values that appear in metadata should be in unresolved if binary_candidate
        assert isinstance(unresolved, list)
        # Never in pos/neg
        assert proposal["positive_values"] == []
        assert proposal["negative_values"] == []

    def test_activation_blockers_include_human_review_required(self):
        result = _make_result()
        blockers = result.activation_proposal["activation_blockers"]
        assert "human_review_required" in blockers

    def test_activation_blockers_include_separate_pr_required(self):
        result = _make_result()
        blockers = result.activation_proposal["activation_blockers"]
        assert "separate_contract_activation_pr_required" in blockers

    def test_human_review_packet_activation_allowed_false(self):
        result = _make_result()
        assert result.human_review_packet["activation_allowed"] is False

    def test_result_is_correct_type(self):
        result = _make_result()
        assert isinstance(result, DS005620ActivationResult)


# ---------------------------------------------------------------------------
# Tests 17–19: write outputs
# ---------------------------------------------------------------------------

class TestWriteOutputs:
    def _run(self, tmp_path):
        result = _make_result()
        paths = write_ds005620_activation_outputs(result, str(tmp_path / "out"))
        return result, paths, tmp_path / "out"

    def test_metadata_value_audit_csv_has_required_columns(self, tmp_path):
        _, _, out = self._run(tmp_path)
        csv_path = out / "metadata_value_audit.csv"
        assert csv_path.is_file()
        header = csv_path.read_text().splitlines()[0]
        for col in ["column", "n_rows", "n_nonempty", "n_unique",
                    "unique_values", "binary_candidate", "likely_label_candidate",
                    "rejected_reason", "warnings"]:
            assert col in header, f"Missing column in CSV: {col}"

    def test_writes_all_six_files(self, tmp_path):
        _, _, out = self._run(tmp_path)
        for name in [
            "activation_proposal.json",
            "human_review_packet.json",
            "metadata_value_audit.csv",
            "activation_blockers.json",
            "omega_event.json",
            "report.md",
        ]:
            assert (out / name).is_file(), f"Missing: {name}"

    def test_json_outputs_parse(self, tmp_path):
        _, _, out = self._run(tmp_path)
        for name in [
            "activation_proposal.json",
            "human_review_packet.json",
            "activation_blockers.json",
            "omega_event.json",
        ]:
            data = json.loads((out / name).read_text())
            assert isinstance(data, dict), f"{name} is not a dict"


# ---------------------------------------------------------------------------
# Test 20: omega_event safe claim
# ---------------------------------------------------------------------------

class TestOmegaEvent:
    def test_omega_event_safe_claim_no_banned_phrases(self):
        result = _make_result()
        omega = build_ds005620_activation_omega_event(result)
        claim = omega.get("safe_claim", "").lower()
        for phrase in _BANNED_PHRASES:
            assert phrase not in claim, f"Banned phrase in omega safe_claim: {phrase}"

    def test_omega_event_contract_activation_false(self):
        result = _make_result()
        omega = build_ds005620_activation_omega_event(result)
        assert omega["contract_activation_allowed"] is False

    def test_omega_event_human_review_required(self):
        result = _make_result()
        omega = build_ds005620_activation_omega_event(result)
        assert omega["human_review_required"] is True


# ---------------------------------------------------------------------------
# Test 21–22: report.md content
# ---------------------------------------------------------------------------

class TestReportMd:
    def _get_report(self, tmp_path) -> str:
        result = _make_result()
        write_ds005620_activation_outputs(result, str(tmp_path / "out"))
        return (tmp_path / "out" / "report.md").read_text()

    def test_report_contains_human_reviewed(self, tmp_path):
        text = self._get_report(tmp_path).lower()
        assert "human-reviewed" in text or "human reviewed" in text

    def test_report_contains_without_inferring_labels(self, tmp_path):
        text = self._get_report(tmp_path).lower()
        assert "without inferring labels" in text or "no labels inferred" in text

    def test_report_contains_separate_contract_activation_pr(self, tmp_path):
        text = self._get_report(tmp_path).lower()
        assert "separate contract-activation pr" in text or "separate" in text

    def test_report_no_banned_phrases(self, tmp_path):
        text = self._get_report(tmp_path).lower()
        for phrase in _BANNED_PHRASES:
            assert phrase not in text, f"Banned phrase in report.md: {phrase}"


# ---------------------------------------------------------------------------
# Tests 23–24: CLI
# ---------------------------------------------------------------------------

class TestCli:
    def test_mock_fixture_exits_zero_and_writes_outputs(self, tmp_path):
        cp = subprocess.run(
            [sys.executable, "-m",
             "sciencer_d.btc_icft.pipelines.prepare_ds005620_contract_activation",
             "--mock-fixture",
             "--out", str(tmp_path / "out")],
            capture_output=True, text=True,
        )
        assert cp.returncode == 0, f"stderr: {cp.stderr}"
        out = tmp_path / "out"
        for name in [
            "activation_proposal.json",
            "human_review_packet.json",
            "metadata_value_audit.csv",
            "activation_blockers.json",
            "omega_event.json",
            "report.md",
        ]:
            assert (out / name).is_file(), f"Missing: {name}"

    def test_missing_metadata_without_mock_fails_cleanly(self, tmp_path):
        cp = subprocess.run(
            [sys.executable, "-m",
             "sciencer_d.btc_icft.pipelines.prepare_ds005620_contract_activation",
             "--out", str(tmp_path / "out")],
            capture_output=True, text=True,
        )
        assert cp.returncode != 0
        assert "metadata" in cp.stderr.lower() or "mock-fixture" in cp.stderr.lower()

    def test_help_works(self):
        cp = subprocess.run(
            [sys.executable, "-m",
             "sciencer_d.btc_icft.pipelines.prepare_ds005620_contract_activation",
             "--help"],
            capture_output=True, text=True,
        )
        assert cp.returncode == 0
        assert "mock-fixture" in cp.stdout.lower() or "metadata" in cp.stdout.lower()


# ---------------------------------------------------------------------------
# Test 25: config
# ---------------------------------------------------------------------------

class TestConfig:
    def test_config_contains_required_outputs(self):
        cfg = Path("configs/btc_icft/ds005620_contract_activation.yaml").read_text()
        for item in [
            "activation_proposal.json",
            "human_review_packet.json",
            "metadata_value_audit.csv",
            "activation_blockers.json",
            "omega_event.json",
            "report.md",
        ]:
            assert item in cfg, f"Config missing required output: {item}"

    def test_config_contains_activation_gates(self):
        cfg = Path("configs/btc_icft/ds005620_contract_activation.yaml").read_text()
        for gate in [
            "metadata_file_exists",
            "explicit_label_column_declared",
            "positive_values_declared",
            "negative_values_declared",
            "label_scope_declared",
            "join_keys_declared",
            "both_classes_present",
            "ambiguous_values_rejected",
            "human_review_required",
            "contract_activation_allowed",
        ]:
            assert gate in cfg, f"Config missing gate: {gate}"

    def test_config_contract_activation_allowed_false(self):
        cfg = Path("configs/btc_icft/ds005620_contract_activation.yaml").read_text()
        assert "contract_activation_allowed: false" in cfg

    def test_config_contains_guardrails(self):
        cfg = Path("configs/btc_icft/ds005620_contract_activation.yaml").read_text()
        for gr in [
            "no_label_inference",
            "no_target_fabrication",
            "no_sedated_to_no_experience",
            "no_unresponsive_to_unconscious",
            "no_automatic_real_contract_activation",
        ]:
            assert gr in cfg, f"Config missing guardrail: {gr}"

    def test_config_no_banned_phrases(self):
        cfg = Path("configs/btc_icft/ds005620_contract_activation.yaml").read_text().lower()
        for phrase in _BANNED_PHRASES:
            assert phrase not in cfg, f"Banned phrase in config: {phrase}"


# ---------------------------------------------------------------------------
# Tests 26–27: no y target / no active contract status
# ---------------------------------------------------------------------------

class TestNoYTargetNoActiveContract:
    def test_no_y_target_in_any_output(self, tmp_path):
        result = _make_result()
        paths = write_ds005620_activation_outputs(result, str(tmp_path / "out"))
        out = tmp_path / "out"
        # Check all JSON outputs for y target fields
        for name in ["activation_proposal.json", "human_review_packet.json",
                     "activation_blockers.json", "omega_event.json"]:
            text = (out / name).read_text()
            data = json.loads(text)
            _check_no_y_target(data)

    def test_no_contract_status_set_to_active(self, tmp_path):
        result = _make_result()
        paths = write_ds005620_activation_outputs(result, str(tmp_path / "out"))
        data = json.loads((tmp_path / "out" / "activation_proposal.json").read_text())
        assert data["contract_activation_allowed"] is False
        assert data["positive_values"] == []
        assert data["negative_values"] == []

    def test_activation_blockers_json_always_false(self, tmp_path):
        result = _make_result()
        write_ds005620_activation_outputs(result, str(tmp_path / "out"))
        data = json.loads((tmp_path / "out" / "activation_blockers.json").read_text())
        assert data["contract_activation_allowed"] is False


def _check_no_y_target(data, path=""):
    if isinstance(data, dict):
        for k, v in data.items():
            if k in ("y", "y_target", "y_targets", "labels", "positive_label", "negative_label"):
                # Should be empty or not present with values
                if isinstance(v, list):
                    assert len(v) == 0, f"Non-empty {k} at {path}"
                elif v is not None and v is not False:
                    pass  # strings/booleans okay for non-target fields
            _check_no_y_target(v, f"{path}.{k}")
    elif isinstance(data, list):
        for i, item in enumerate(data):
            _check_no_y_target(item, f"{path}[{i}]")


# ---------------------------------------------------------------------------
# Tests 28–29: P11/P12/P13/P14/legacy not imported or modified
# ---------------------------------------------------------------------------

class TestModuleIsolation:
    def test_no_p11_p12_p13_import_in_activation_module(self):
        src = Path(
            "sciencer_d/btc_icft/labels/ds005620_contract_activation.py"
        ).read_text()
        assert "eeg_signal_residual" not in src
        assert "eeg_label_contracts" not in src
        assert "eeg_target_injection" not in src
        assert "run_eeg_signal_mt" not in src

    def test_no_legacy_mt_real_import_in_activation_module(self):
        src = Path(
            "sciencer_d/btc_icft/labels/ds005620_contract_activation.py"
        ).read_text()
        assert "run_ds005620_mt_real" not in src
        assert "ds005620_residual" not in src

    def test_no_p13_import_in_pipeline(self):
        src = Path(
            "sciencer_d/btc_icft/pipelines/prepare_ds005620_contract_activation.py"
        ).read_text()
        assert "eeg_target_injection" not in src
        assert "inject_eeg_targets" not in src

    def test_no_p11_import_in_pipeline(self):
        src = Path(
            "sciencer_d/btc_icft/pipelines/prepare_ds005620_contract_activation.py"
        ).read_text()
        assert "eeg_signal_residual" not in src
        assert "run_eeg_signal_mt" not in src


# ---------------------------------------------------------------------------
# Tests 30–31: contract_drafts as hints only; active draft downgraded
# ---------------------------------------------------------------------------

class TestContractDraftsAsHintsOnly:
    def _make_draft(self, status="draft_inactive_human_review_required",
                    pos_vals=None, neg_vals=None) -> dict:
        return {
            "drafts": [{
                "dataset_id": "DS005620",
                "status": status,
                "candidate_label_columns": ["trial_type"],
                "unresolved_values": ["focus", "mind_wandering"],
                "positive_values": pos_vals or [],
                "negative_values": neg_vals or [],
            }]
        }

    def test_contract_drafts_used_as_hints_only(self):
        drafts = self._make_draft()
        result = prepare_ds005620_activation_proposal(_STANDARD_ROWS, drafts)
        proposal = result.activation_proposal
        # Still not activated
        assert proposal["contract_activation_allowed"] is False
        assert proposal["positive_values"] == []
        assert proposal["negative_values"] == []
        # But candidate columns included as hints
        assert "trial_type" in proposal["candidate_label_columns"]

    def test_active_looking_draft_is_downgraded_with_warning(self):
        drafts = self._make_draft(
            status="ready_to_activate",
            pos_vals=["focus"],
            neg_vals=["mind_wandering"],
        )
        result = prepare_ds005620_activation_proposal(_STANDARD_ROWS, drafts)
        # Still not activated
        assert result.activation_proposal["contract_activation_allowed"] is False
        assert result.activation_proposal["positive_values"] == []
        assert result.activation_proposal["negative_values"] == []
        # Warning should be present
        assert any("downgraded" in w.lower() or "inactive" in w.lower() or "ignored" in w.lower()
                   for w in result.warnings)

    def test_contract_drafts_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_contract_drafts(str(tmp_path / "nonexistent.json"))

    def test_unresolved_values_from_draft_appear_in_proposal(self):
        drafts = self._make_draft()
        result = prepare_ds005620_activation_proposal(_STANDARD_ROWS, drafts)
        unresolved = result.activation_proposal["unresolved_values"]
        # Hint values from draft appear in unresolved, not in pos/neg
        assert "focus" in unresolved or "mind_wandering" in unresolved


# ---------------------------------------------------------------------------
# Guardrail: safe_claim
# ---------------------------------------------------------------------------

class TestGuardrails:
    def test_safe_claim_has_no_banned_phrases(self):
        for phrase in _BANNED_PHRASES:
            assert phrase not in _SAFE_CLAIM.lower()

    def test_no_infer_label_in_module_source(self):
        src = Path(
            "sciencer_d/btc_icft/labels/ds005620_contract_activation.py"
        ).read_text()
        assert "infer_label" not in src
        assert "make_target" not in src

    def test_contract_activation_true_not_in_source(self):
        src = Path(
            "sciencer_d/btc_icft/labels/ds005620_contract_activation.py"
        ).read_text()
        assert '"contract_activation_allowed": True' not in src
        assert '"contract_activation_allowed": true' not in src
