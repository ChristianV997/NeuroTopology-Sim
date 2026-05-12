from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from sciencer_d.btc_icft.labels.ds005620_contract_activation import (
    audit_metadata_values,
    build_activation_blockers,
    build_human_review_packet,
    load_contract_drafts,
    load_metadata_rows,
    prepare_ds005620_activation_proposal,
    write_ds005620_activation_outputs,
)


def _base_rows() -> list[dict]:
    return [
        {
            "dataset_id": "DS005620",
            "row_id": "r0",
            "source_file": "/mock/a.edf",
            "window_id": "w0",
            "window_start_s": "0.0",
            "window_end_s": "1.0",
            "sample_start": "0",
            "sample_end": "100",
            "candidate_state": "yes",
            "condition_group": "a",
            "notes": "free text notes row zero",
            "file_path": "/tmp/mock/a.tsv",
            "single_value": "only_one",
        },
        {
            "dataset_id": "DS005620",
            "row_id": "r1",
            "source_file": "/mock/b.edf",
            "window_id": "w1",
            "window_start_s": "1.0",
            "window_end_s": "2.0",
            "sample_start": "100",
            "sample_end": "200",
            "candidate_state": "no",
            "condition_group": "b",
            "notes": "free text notes row one",
            "file_path": "/tmp/mock/b.tsv",
            "single_value": "only_one",
        },
        {
            "dataset_id": "DS005620",
            "row_id": "r2",
            "source_file": "/mock/c.edf",
            "window_id": "w2",
            "window_start_s": "2.0",
            "window_end_s": "3.0",
            "sample_start": "200",
            "sample_end": "300",
            "candidate_state": "yes",
            "condition_group": "c",
            "notes": "free text notes row two",
            "file_path": "/tmp/mock/c.tsv",
            "single_value": "only_one",
        },
    ]


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_01_load_metadata_rows_reads_csv(tmp_path: Path) -> None:
    p = tmp_path / "m.csv"
    rows = _base_rows()
    _write_csv(p, rows)
    loaded = load_metadata_rows(str(p))
    assert len(loaded) == len(rows)
    assert loaded[0]["candidate_state"] == "yes"


def test_02_load_metadata_rows_reads_tsv(tmp_path: Path) -> None:
    p = tmp_path / "m.tsv"
    rows = _base_rows()
    with p.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    loaded = load_metadata_rows(str(p))
    assert len(loaded) == len(rows)
    assert loaded[1]["condition_group"] == "b"


def test_03_load_metadata_rows_reads_json_list(tmp_path: Path) -> None:
    p = tmp_path / "m.json"
    rows = _base_rows()
    p.write_text(json.dumps(rows), encoding="utf-8")
    loaded = load_metadata_rows(str(p))
    assert len(loaded) == len(rows)


def test_04_load_metadata_rows_reads_json_rows_object(tmp_path: Path) -> None:
    p = tmp_path / "m.json"
    rows = _base_rows()
    p.write_text(json.dumps({"rows": rows}), encoding="utf-8")
    loaded = load_metadata_rows(str(p))
    assert len(loaded) == len(rows)


def test_05_unsupported_metadata_extension_raises_value_error(tmp_path: Path) -> None:
    p = tmp_path / "m.txt"
    p.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        load_metadata_rows(str(p))


def test_06_missing_metadata_raises_file_not_found_error(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_metadata_rows(str(tmp_path / "missing.csv"))


def test_07_audit_identifies_binary_candidate_column() -> None:
    audits = audit_metadata_values(_base_rows())
    row = next(a for a in audits if a.column == "candidate_state")
    assert row.binary_candidate is True


def test_08_audit_rejects_free_text_notes_column() -> None:
    audits = audit_metadata_values(_base_rows())
    row = next(a for a in audits if a.column == "notes")
    assert row.rejected_reason == "likely_free_text"


def test_09_audit_rejects_file_path_column() -> None:
    audits = audit_metadata_values(_base_rows())
    row = next(a for a in audits if a.column == "file_path")
    assert row.rejected_reason == "likely_file_path"


def test_10_audit_rejects_single_value_column() -> None:
    audits = audit_metadata_values(_base_rows())
    row = next(a for a in audits if a.column == "single_value")
    assert row.rejected_reason == "single_value_only"


def test_11_proposal_never_sets_contract_activation_allowed_true() -> None:
    result = prepare_ds005620_activation_proposal(_base_rows())
    assert result.activation_proposal["contract_activation_allowed"] is False


def test_12_positive_and_negative_values_remain_empty() -> None:
    result = prepare_ds005620_activation_proposal(_base_rows())
    assert result.activation_proposal["positive_values"] == []
    assert result.activation_proposal["negative_values"] == []


def test_13_candidate_values_go_to_unresolved_values_only() -> None:
    result = prepare_ds005620_activation_proposal(_base_rows())
    unresolved = result.activation_proposal["unresolved_values"]
    assert "yes" in unresolved and "no" in unresolved
    assert result.activation_proposal["positive_values"] == []
    assert result.activation_proposal["negative_values"] == []


def test_14_activation_blockers_include_human_review_required() -> None:
    result = prepare_ds005620_activation_proposal(_base_rows())
    blockers = build_activation_blockers(result)
    assert "human_review_required" in blockers["blockers"]


def test_15_activation_blockers_include_separate_contract_activation_pr_required() -> None:
    result = prepare_ds005620_activation_proposal(_base_rows())
    blockers = build_activation_blockers(result)
    assert "separate_contract_activation_pr_required" in blockers["blockers"]


def test_16_human_review_packet_activation_allowed_false() -> None:
    result = prepare_ds005620_activation_proposal(_base_rows())
    packet = build_human_review_packet(result)
    assert packet["activation_allowed"] is False


def test_17_metadata_value_audit_csv_writes_required_columns(tmp_path: Path) -> None:
    result = prepare_ds005620_activation_proposal(_base_rows())
    outputs = write_ds005620_activation_outputs(result, str(tmp_path))
    with Path(outputs["metadata_value_audit.csv"]).open("r", encoding="utf-8") as fh:
        cols = csv.DictReader(fh).fieldnames or []
    assert cols == [
        "column",
        "n_rows",
        "n_nonempty",
        "n_unique",
        "unique_values",
        "binary_candidate",
        "likely_label_candidate",
        "rejected_reason",
        "warnings",
    ]


def test_18_write_outputs_writes_all_six_files(tmp_path: Path) -> None:
    result = prepare_ds005620_activation_proposal(_base_rows())
    outputs = write_ds005620_activation_outputs(result, str(tmp_path))
    assert set(outputs.keys()) == {
        "activation_proposal.json",
        "human_review_packet.json",
        "metadata_value_audit.csv",
        "activation_blockers.json",
        "omega_event.json",
        "report.md",
    }


def test_19_json_outputs_parse(tmp_path: Path) -> None:
    result = prepare_ds005620_activation_proposal(_base_rows())
    outputs = write_ds005620_activation_outputs(result, str(tmp_path))
    for name in [
        "activation_proposal.json",
        "human_review_packet.json",
        "activation_blockers.json",
        "omega_event.json",
    ]:
        json.loads(Path(outputs[name]).read_text(encoding="utf-8"))


def test_20_omega_event_safe_claim_has_no_banned_phrases(tmp_path: Path) -> None:
    result = prepare_ds005620_activation_proposal(_base_rows())
    outputs = write_ds005620_activation_outputs(result, str(tmp_path))
    omega = json.loads(Path(outputs["omega_event.json"]).read_text(encoding="utf-8"))
    safe_claim = omega["safe_claim"].lower()
    banned = [
        "proves consciousness",
        "consciousness proven",
        "soul proven",
        "afterlife proven",
        "liberation detected",
        "ontology solved",
        "ultimate reality",
        "q equals self",
        "q equals soul",
        "q_abs equals suffering",
        "f_dress equals karma",
        "sedated implies no_experience",
        "unresponsive implies unconscious",
    ]
    assert all(p not in safe_claim for p in banned)


def test_21_report_contains_required_cautious_terms(tmp_path: Path) -> None:
    result = prepare_ds005620_activation_proposal(_base_rows())
    outputs = write_ds005620_activation_outputs(result, str(tmp_path))
    report = Path(outputs["report.md"]).read_text(encoding="utf-8").lower()
    assert "human-reviewed" in report
    assert "without inferring labels or targets" in report
    assert "separate contract-activation pr" in report


def test_22_report_does_not_contain_banned_phrases(tmp_path: Path) -> None:
    result = prepare_ds005620_activation_proposal(_base_rows())
    outputs = write_ds005620_activation_outputs(result, str(tmp_path))
    report = Path(outputs["report.md"]).read_text(encoding="utf-8").lower()
    for p in [
        "proves consciousness",
        "soul proven",
        "afterlife proven",
        "liberation detected",
        "ontology solved",
        "ultimate reality",
        "q equals self",
        "q equals soul",
        "q_abs equals suffering",
        "f_dress equals karma",
        "sedated implies no_experience",
        "unresponsive implies unconscious",
    ]:
        assert p not in report


def test_23_cli_mock_fixture_exits_0_and_writes_outputs(tmp_path: Path) -> None:
    out = tmp_path / "out"
    cmd = [
        sys.executable,
        "-m",
        "sciencer_d.btc_icft.pipelines.prepare_ds005620_contract_activation",
        "--mock-fixture",
        "--out",
        str(out),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    assert p.returncode == 0
    for name in [
        "activation_proposal.json",
        "human_review_packet.json",
        "metadata_value_audit.csv",
        "activation_blockers.json",
        "omega_event.json",
        "report.md",
    ]:
        assert (out / name).exists()


def test_24_cli_missing_metadata_without_mock_fails_cleanly(tmp_path: Path) -> None:
    cmd = [
        sys.executable,
        "-m",
        "sciencer_d.btc_icft.pipelines.prepare_ds005620_contract_activation",
        "--out",
        str(tmp_path / "out"),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    assert p.returncode != 0
    assert "DS005620 local metadata is required. Provide --metadata or use --mock-fixture." in p.stderr


def test_25_config_contains_required_outputs_gates_guardrails() -> None:
    txt = Path("configs/btc_icft/ds005620_contract_activation.yaml").read_text(encoding="utf-8")
    assert "required_outputs" in txt
    assert "activation_proposal.json" in txt
    assert "human_review_packet.json" in txt
    assert "metadata_value_audit.csv" in txt
    assert "activation_blockers.json" in txt
    assert "omega_event.json" in txt
    assert "report.md" in txt
    assert "activation_gates" in txt
    assert "contract_activation_allowed" in txt
    assert "guardrails" in txt
    assert "no_label_inference" in txt


def test_26_no_y_target_appears_in_any_output(tmp_path: Path) -> None:
    result = prepare_ds005620_activation_proposal(_base_rows())
    outputs = write_ds005620_activation_outputs(result, str(tmp_path))
    for path in outputs.values():
        text = Path(path).read_text(encoding="utf-8").lower()
        assert '"y"' not in text
        assert " y," not in text


def test_27_no_contract_status_is_set_to_active(tmp_path: Path) -> None:
    result = prepare_ds005620_activation_proposal(_base_rows())
    outputs = write_ds005620_activation_outputs(result, str(tmp_path))
    for path in outputs.values():
        text = Path(path).read_text(encoding="utf-8").lower()
        assert "\"status\": \"active\"" not in text


def test_28_p11_p12_p13_behavior_not_imported_or_modified() -> None:
    src = Path("sciencer_d/btc_icft/labels/ds005620_contract_activation.py").read_text(encoding="utf-8")
    cli = Path("sciencer_d/btc_icft/pipelines/prepare_ds005620_contract_activation.py").read_text(encoding="utf-8")
    banned_imports = [
        "run_eeg_signal_mt",
        "align_eeg_labels",
        "eeg_label_contracts",
        "eeg_target_injection",
        "inject_eeg_targets",
    ]
    for token in banned_imports:
        assert token not in src
        assert token not in cli


def test_29_legacy_mt_real_files_not_imported_or_modified() -> None:
    src = Path("sciencer_d/btc_icft/labels/ds005620_contract_activation.py").read_text(encoding="utf-8")
    cli = Path("sciencer_d/btc_icft/pipelines/prepare_ds005620_contract_activation.py").read_text(encoding="utf-8")
    assert "mt_real" not in src
    assert "mt_real" not in cli


def test_30_issue_80_acceptance_commands_pass(tmp_path: Path) -> None:
    cmds = [
        [sys.executable, "-m", "governance.validate"],
        [
            sys.executable,
            "-m",
            "sciencer_d.btc_icft.pipelines.prepare_ds005620_contract_activation",
            "--mock-fixture",
            "--out",
            str(tmp_path / "packet"),
        ],
    ]
    for cmd in cmds:
        p = subprocess.run(cmd, capture_output=True, text=True)
        assert p.returncode == 0, f"Command failed: {' '.join(cmd)}\nSTDOUT:{p.stdout}\nSTDERR:{p.stderr}"


def test_load_contract_drafts(tmp_path: Path) -> None:
    p = tmp_path / "drafts.json"
    p.write_text(json.dumps({"metadata_provenance": "manual_review"}), encoding="utf-8")
    data = load_contract_drafts(str(p))
    assert data["metadata_provenance"] == "manual_review"
