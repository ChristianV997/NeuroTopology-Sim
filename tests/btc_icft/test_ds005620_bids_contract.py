from __future__ import annotations

import json
import subprocess
import sys

import pytest

from sciencer_d.btc_icft.datasets.ds005620_bids import (
    build_label_candidates,
    discover_ds005620_bids_files,
    inspect_ds005620_bids_root,
    write_bids_inspection_outputs,
)


def mk_tree(tmp_path):
    (tmp_path / "participants.tsv").write_text("participant_id\nsub-001\nsub-002\n", encoding="utf-8")
    p1 = tmp_path / "sub-001" / "ses-01" / "eeg"
    p1.mkdir(parents=True)
    (p1 / "sub-001_ses-01_task-awake_run-01_eeg.edf").write_text("", encoding="utf-8")
    p2 = tmp_path / "sub-002" / "ses-01" / "eeg"
    p2.mkdir(parents=True)
    (p2 / "sub-002_ses-01_task-sedated_run-01_eeg.edf").write_text("", encoding="utf-8")


def test_discover_minimal(tmp_path):
    mk_tree(tmp_path)
    records = discover_ds005620_bids_files(str(tmp_path))
    assert len(records) == 3


def test_tokens(tmp_path):
    mk_tree(tmp_path)
    r = [x for x in discover_ds005620_bids_files(str(tmp_path)) if x.subject_id == "001"][0]
    assert r.session_id == "01" and r.task_label == "awake" and r.run_id == "01" and r.suffix == "eeg" and r.extension == ".edf"


def test_inventory_counts(tmp_path):
    mk_tree(tmp_path)
    i = inspect_ds005620_bids_root(str(tmp_path))
    assert i.n_files == 3 and i.n_subjects == 2


def test_label_candidates_contract(tmp_path):
    mk_tree(tmp_path)
    labels = build_label_candidates(discover_ds005620_bids_files(str(tmp_path)))
    assert labels and labels[0].row_id and labels[0].subject_id
    assert all(x.state_label in {"awake", "sedated", "unknown", None} for x in labels)


def test_unresponsive_not_unconscious_and_sedated_not_noexperience(tmp_path):
    p = tmp_path / "sub-001" / "ses-01" / "eeg"
    p.mkdir(parents=True)
    (p / "sub-001_ses-01_task-unresponsive_run-01_eeg.edf").write_text("")
    labels = build_label_candidates(discover_ds005620_bids_files(str(tmp_path)))
    assert all(l.state_label != "unconscious" for l in labels)
    assert all(not (l.state_label == "sedated" and l.report_label == "no_experience") for l in labels)


def test_explicit_no_experience_report_only(tmp_path):
    p = tmp_path / "sub-001" / "ses-01" / "eeg"
    p.mkdir(parents=True)
    (p / "sub-001_ses-01_task-no_experience_run-01_eeg.edf").write_text("")
    l = build_label_candidates(discover_ds005620_bids_files(str(tmp_path)))[0]
    assert l.report_label == "no_experience"


def test_forbidden_terms_raise(tmp_path):
    p = tmp_path / "sub-001_soul.edf"
    p.write_text("")
    with pytest.raises(ValueError):
        discover_ds005620_bids_files(str(tmp_path))


def test_missing_root_raises():
    with pytest.raises(FileNotFoundError):
        discover_ds005620_bids_files("/tmp/does_not_exist_xyz")


def test_cli_missing_root_nonzero():
    proc = subprocess.run([sys.executable, "-m", "sciencer_d.btc_icft.pipelines.inspect_ds005620_bids", "--bids-root", "/tmp/none_xyz"], capture_output=True, text=True)
    assert proc.returncode != 0


def test_cli_outputs_and_report(tmp_path):
    mk_tree(tmp_path)
    out = tmp_path / "out"
    proc = subprocess.run([sys.executable, "-m", "sciencer_d.btc_icft.pipelines.inspect_ds005620_bids", "--bids-root", str(tmp_path), "--out", str(out)], capture_output=True, text=True)
    assert proc.returncode == 0
    for fn in ["file_inventory.json", "label_candidates.json", "contract_report.json", "report.md"]:
        assert (out / fn).exists()
    inv = json.loads((out / "file_inventory.json").read_text())
    assert "n_files" in inv and "eeg_candidates" in inv
    rpt = (out / "report.md").read_text().lower()
    assert "operational metadata candidates" in rpt and "future level m" in rpt and "future level t" in rpt and "residual testing" in rpt
    for bad in ["proves consciousness", "soul proven", "afterlife proven", "liberation detected", "ontology solved", "ultimate reality", "q equals self", "q equals soul", "q_abs equals suffering", "f_dress equals karma"]:
        assert bad not in rpt


def test_config_exists_guardrails():
    txt = open("configs/btc_icft/ds005620_bids.yaml", encoding="utf-8").read()
    assert "required_outputs" in txt and "guardrails" in txt
