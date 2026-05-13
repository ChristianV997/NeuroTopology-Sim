"""Tests for DS005620 real/local preflight (P18.2)."""
import json
import os
from pathlib import Path

import pytest

from sciencer_d.btc_icft.p18.ds005620_real_local_preflight import (
    run_real_local_preflight,
    write_preflight_outputs,
)

_STRICT_JOIN_KEYS = [
    "dataset_id", "row_id", "source_file", "window_id",
    "window_start_s", "window_end_s", "sample_start", "sample_end",
]


def _write_contract(tmp_path: Path, status: str = "active_reviewed_external_contract") -> Path:
    p = tmp_path / "contract.json"
    p.write_text(json.dumps({
        "contract_status": status,
        "dataset_id": "DS005620",
        "join_keys": _STRICT_JOIN_KEYS,
        "explicit_label_column": "trial_type",
        "positive_values": ["focus"],
        "negative_values": ["mind_wandering"],
    }), encoding="utf-8")
    return p


def _write_metadata(tmp_path: Path) -> Path:
    p = tmp_path / "events.tsv"
    p.write_text("onset\tduration\ttrial_type\n0\t2\tfocus\n", encoding="utf-8")
    return p


def _write_signal_blocks(tmp_path: Path) -> Path:
    d = tmp_path / "signal_blocks"
    d.mkdir()
    for fname in ("signal_block_inventory.json", "window_inventory.csv",
                  "window_signal_values.json", "reader_alignment_report.json"):
        (d / fname).write_text("{}", encoding="utf-8")
    return d


def _write_level_m(tmp_path: Path) -> Path:
    d = tmp_path / "level_m"
    d.mkdir()
    (d / "features_m_signal.csv").write_text("header\n", encoding="utf-8")
    return d


def _write_level_t(tmp_path: Path) -> Path:
    d = tmp_path / "level_t"
    d.mkdir()
    (d / "features_t_signal.csv").write_text("header\n", encoding="utf-8")
    return d


def test_all_inputs_missing_not_ready():
    result = run_real_local_preflight("DS005620")
    assert not result.all_ready
    assert len(result.blockers) > 0


def test_metadata_missing_next_action(tmp_path):
    contract = _write_contract(tmp_path)
    result = run_real_local_preflight(
        "DS005620",
        reviewed_contract=str(contract),
        metadata=None,
    )
    assert not result.all_ready
    assert result.next_action == "provide_metadata"


def test_contract_bad_status_blocked(tmp_path):
    contract = _write_contract(tmp_path, status="preview")
    meta = _write_metadata(tmp_path)
    result = run_real_local_preflight(
        "DS005620",
        reviewed_contract=str(contract),
        metadata=str(meta),
    )
    assert not result.all_ready
    blockers_text = " ".join(result.blockers)
    assert "active_reviewed_external_contract" in blockers_text


def test_contract_missing_blocked(tmp_path):
    meta = _write_metadata(tmp_path)
    result = run_real_local_preflight(
        "DS005620",
        reviewed_contract=str(tmp_path / "does_not_exist.json"),
        metadata=str(meta),
    )
    assert not result.all_ready
    assert any("not found" in b for b in result.blockers)


def test_signal_blocks_missing_action(tmp_path):
    contract = _write_contract(tmp_path)
    meta = _write_metadata(tmp_path)
    result = run_real_local_preflight(
        "DS005620",
        reviewed_contract=str(contract),
        metadata=str(meta),
        signal_blocks=str(tmp_path / "missing_dir"),
    )
    assert not result.all_ready
    assert "run_p19_2" in result.next_action


def test_all_ready_real_local_execute(tmp_path):
    contract = _write_contract(tmp_path)
    meta = _write_metadata(tmp_path)
    sb = _write_signal_blocks(tmp_path)
    lm = _write_level_m(tmp_path)
    lt = _write_level_t(tmp_path)
    result = run_real_local_preflight(
        "DS005620",
        reviewed_contract=str(contract),
        metadata=str(meta),
        signal_blocks=str(sb),
        level_m=str(lm),
        level_t=str(lt),
    )
    assert result.all_ready
    assert result.next_action == "run_p18_1_real_local_execute"
    assert len(result.blockers) == 0


def test_write_preflight_outputs_creates_files(tmp_path):
    contract = _write_contract(tmp_path)
    meta = _write_metadata(tmp_path)
    sb = _write_signal_blocks(tmp_path)
    lm = _write_level_m(tmp_path)
    lt = _write_level_t(tmp_path)
    result = run_real_local_preflight(
        "DS005620",
        reviewed_contract=str(contract),
        metadata=str(meta),
        signal_blocks=str(sb),
        level_m=str(lm),
        level_t=str(lt),
    )
    out = tmp_path / "preflight_out"
    artifacts = write_preflight_outputs(result, str(out))
    assert Path(artifacts["preflight_report.json"]).exists()
    assert Path(artifacts["preflight_report.md"]).exists()


def test_preflight_safe_claim_present(tmp_path):
    result = run_real_local_preflight("DS005620")
    assert result.safe_claim
    assert len(result.safe_claim) > 20


def test_preflight_no_banned_phrases(tmp_path):
    contract = _write_contract(tmp_path)
    meta = _write_metadata(tmp_path)
    sb = _write_signal_blocks(tmp_path)
    lm = _write_level_m(tmp_path)
    lt = _write_level_t(tmp_path)
    result = run_real_local_preflight(
        "DS005620",
        reviewed_contract=str(contract),
        metadata=str(meta),
        signal_blocks=str(sb),
        level_m=str(lm),
        level_t=str(lt),
    )
    out = tmp_path / "preflight_out"
    artifacts = write_preflight_outputs(result, str(out))
    _BANNED = [
        "proves consciousness", "consciousness proven", "soul proven",
        "afterlife proven", "liberation detected", "ontology solved",
        "ultimate reality", "q equals self", "q equals soul",
        "q_abs equals suffering", "f_dress equals karma",
        "sedated implies no_experience", "unresponsive implies unconscious",
        "topology proves liberation", "eeg proves consciousness",
    ]
    md_text = Path(artifacts["preflight_report.md"]).read_text(encoding="utf-8").lower()
    for phrase in _BANNED:
        assert phrase not in md_text, f"banned phrase {phrase!r} in preflight_report.md"


def test_level_m_missing_action(tmp_path):
    contract = _write_contract(tmp_path)
    meta = _write_metadata(tmp_path)
    sb = _write_signal_blocks(tmp_path)
    result = run_real_local_preflight(
        "DS005620",
        reviewed_contract=str(contract),
        metadata=str(meta),
        signal_blocks=str(sb),
        level_m=str(tmp_path / "missing_level_m"),
        level_t=None,
    )
    assert not result.all_ready
    assert "p9" in result.next_action
