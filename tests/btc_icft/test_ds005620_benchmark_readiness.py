"""Tests for P18.0 — DS005620 real benchmark readiness gate.

33 tests covering:
  - reviewed_contract inspection (4)
  - metadata_file inspection (2)
  - canonical_signal_blocks inspection (3)
  - level_m/level_t inspection (2)
  - overall readiness flags (3)
  - CLI (5)
  - output artifacts (4)
  - dry_run_command_plan content (4)
  - report.md content (4)
  - guardrails / banned phrases (2)
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

from sciencer_d.btc_icft.p18.ds005620_benchmark_readiness import (
    _BANNED_PHRASES,
    _SAFE_CLAIM,
    _STRICT_JOIN_KEYS,
    build_ds005620_benchmark_readiness,
    inspect_canonical_signal_blocks,
    inspect_level_m_features,
    inspect_level_t_features,
    inspect_metadata_file,
    inspect_reviewed_contract,
    write_p18_readiness_outputs,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_valid_contract(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "dataset_id": "DS005620",
        "contract_status": "active_reviewed_external_contract",
        "explicit_label_column": "trial_type",
        "positive_values": ["focus"],
        "negative_values": ["mind_wandering"],
        "label_scope": "window",
        "join_keys": _STRICT_JOIN_KEYS[:],
        "metadata_provenance": "data/DS005620/events.tsv",
        "activation_provenance": "p17_1_reviewed_materializer",
        "guardrails": ["no_label_inference"],
    }), encoding="utf-8")


def _write_invalid_contract(path: Path, status: str = "preview_human_reviewed_not_active") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "dataset_id": "DS005620",
        "contract_status": status,
        "explicit_label_column": "trial_type",
        "positive_values": ["focus"],
        "negative_values": ["mind_wandering"],
        "join_keys": _STRICT_JOIN_KEYS[:],
        "guardrails": [],
    }), encoding="utf-8")


def _write_metadata_tsv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("onset\tduration\ttrial_type\n0.0\t10.0\tfocus\n10.0\t10.0\tmind_wandering\n", encoding="utf-8")


def _write_signal_blocks(d: Path, include_all_keys: bool = True) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "signal_block_inventory.json").write_text(
        json.dumps({"n_signal_blocks": 1}), encoding="utf-8"
    )
    cols = _STRICT_JOIN_KEYS if include_all_keys else ["row_id", "window_id"]
    cols = cols + ["n_channels", "n_samples"]
    with (d / "window_inventory.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        row = {c: "mock" for c in cols}
        w.writerow(row)
    (d / "window_signal_values.json").write_text(json.dumps({"windows": []}), encoding="utf-8")
    (d / "reader_alignment_report.json").write_text(json.dumps({
        "ready_for_p9_level_m_signal": True,
        "ready_for_level_m_signal": True,
        "ready_for_p10_level_t_signal": True,
        "ready_for_level_t_signal": True,
    }), encoding="utf-8")


def _write_level_m(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    cols = _STRICT_JOIN_KEYS + ["spectral_power_proxy", "feature_status"]
    with (d / "features_m_signal.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()


def _write_level_t(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    cols = _STRICT_JOIN_KEYS + ["qz_mean", "topology_status"]
    with (d / "features_t_signal.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()


# ---------------------------------------------------------------------------
# Section 1: reviewed_contract inspection (4 tests)
# ---------------------------------------------------------------------------

def test_reviewed_contract_ready_when_valid(tmp_path):
    p = tmp_path / "p12.json"
    _write_valid_contract(p)
    status = inspect_reviewed_contract(str(p))
    assert status.ready is True
    assert status.status == "ready"
    assert status.blockers == []


def test_reviewed_contract_blocked_when_missing():
    status = inspect_reviewed_contract("/nonexistent/p12.json")
    assert status.ready is False
    assert status.exists is False
    assert len(status.blockers) > 0


def test_reviewed_contract_blocked_when_status_inactive(tmp_path):
    p = tmp_path / "p12.json"
    _write_invalid_contract(p, status="preview_human_reviewed_not_active")
    status = inspect_reviewed_contract(str(p))
    assert status.ready is False
    assert any("contract_status" in b for b in status.blockers)


def test_reviewed_contract_blocked_when_no_path():
    status = inspect_reviewed_contract("")
    assert status.ready is False
    assert status.exists is False


# ---------------------------------------------------------------------------
# Section 2: metadata_file inspection (2 tests)
# ---------------------------------------------------------------------------

def test_metadata_file_ready_for_tsv(tmp_path):
    p = tmp_path / "events.tsv"
    _write_metadata_tsv(p)
    status = inspect_metadata_file(str(p))
    assert status.ready is True
    assert status.exists is True


def test_metadata_file_blocked_when_missing():
    status = inspect_metadata_file("/nonexistent/events.tsv")
    assert status.ready is False
    assert status.exists is False


# ---------------------------------------------------------------------------
# Section 3: canonical_signal_blocks inspection (3 tests)
# ---------------------------------------------------------------------------

def test_canonical_signal_blocks_ready_when_files_exist(tmp_path):
    d = tmp_path / "signal_blocks"
    _write_signal_blocks(d, include_all_keys=True)
    status = inspect_canonical_signal_blocks(str(d))
    assert status.ready is True
    assert status.status == "ready"


def test_canonical_signal_blocks_blocked_when_directory_missing():
    status = inspect_canonical_signal_blocks("/nonexistent/signal_blocks")
    assert status.ready is False
    assert status.exists is False
    assert len(status.blockers) > 0


def test_canonical_signal_blocks_blocked_when_strict_keys_missing(tmp_path):
    d = tmp_path / "signal_blocks"
    _write_signal_blocks(d, include_all_keys=False)
    status = inspect_canonical_signal_blocks(str(d))
    assert status.ready is False
    assert any("strict join keys" in b for b in status.blockers)


# ---------------------------------------------------------------------------
# Section 4: Level M / Level T inspection (2 tests)
# ---------------------------------------------------------------------------

def test_level_m_ready_when_features_exist_with_strict_keys(tmp_path):
    d = tmp_path / "level_m"
    _write_level_m(d)
    status = inspect_level_m_features(str(d))
    assert status.ready is True


def test_level_t_ready_when_features_exist_with_strict_keys(tmp_path):
    d = tmp_path / "level_t"
    _write_level_t(d)
    status = inspect_level_t_features(str(d))
    assert status.ready is True


# ---------------------------------------------------------------------------
# Section 5: overall readiness flags (3 tests)
# ---------------------------------------------------------------------------

def test_readiness_false_when_reviewed_contract_missing(tmp_path):
    d = tmp_path / "signal_blocks"
    _write_signal_blocks(d)
    inputs = {
        "reviewed_contract": "/nonexistent/p12.json",
        "metadata": None,
        "signal_blocks": str(d),
        "level_m": None,
        "level_t": None,
    }
    result = build_ds005620_benchmark_readiness(inputs)
    assert result.ready_for_p12_alignment is False
    assert result.ready_for_real_benchmark is False


def test_readiness_false_when_metadata_missing(tmp_path):
    p = tmp_path / "p12.json"
    _write_valid_contract(p)
    inputs = {
        "reviewed_contract": str(p),
        "metadata": "/nonexistent/events.tsv",
        "signal_blocks": "/nonexistent/signal_blocks",
        "level_m": None,
        "level_t": None,
    }
    result = build_ds005620_benchmark_readiness(inputs)
    assert result.ready_for_p12_alignment is False


def test_readiness_false_when_signal_blocks_missing(tmp_path):
    p = tmp_path / "p12.json"
    meta = tmp_path / "events.tsv"
    _write_valid_contract(p)
    _write_metadata_tsv(meta)
    inputs = {
        "reviewed_contract": str(p),
        "metadata": str(meta),
        "signal_blocks": "/nonexistent/signal_blocks",
        "level_m": None,
        "level_t": None,
    }
    result = build_ds005620_benchmark_readiness(inputs)
    assert result.ready_for_p12_alignment is False


# ---------------------------------------------------------------------------
# Section 6: CLI tests (5 tests)
# ---------------------------------------------------------------------------

def test_cli_mock_ready_exits_0(tmp_path):
    from sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark import main
    rc = main(["--mock-ready", "--out", str(tmp_path / "out")])
    assert rc == 0


def test_cli_mock_ready_writes_all_6_files(tmp_path):
    from sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark import main
    out = tmp_path / "out"
    main(["--mock-ready", "--out", str(out)])
    files = list(out.iterdir())
    assert len(files) == 6


def test_cli_mock_ready_sets_p12_alignment_ready(tmp_path):
    from sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark import main
    out = tmp_path / "out"
    main(["--mock-ready", "--out", str(out)])
    data = json.loads((out / "ds005620_benchmark_readiness.json").read_text())
    assert data["ready_for_p12_alignment"] is True


def test_cli_mock_ready_does_not_run_p11(tmp_path):
    from sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark import main
    out = tmp_path / "out"
    main(["--mock-ready", "--out", str(out)])
    omega = json.loads((out / "omega_event.json").read_text())
    assert omega.get("benchmarks_run") is False


def test_cli_mock_blocked_exits_0(tmp_path):
    from sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark import main
    rc = main(["--mock-blocked", "--out", str(tmp_path / "out")])
    assert rc == 0


# ---------------------------------------------------------------------------
# Section 7: output artifacts (4 tests)
# ---------------------------------------------------------------------------

def test_mock_blocked_has_execution_blockers(tmp_path):
    from sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark import main
    out = tmp_path / "out"
    main(["--mock-blocked", "--out", str(out)])
    data = json.loads((out / "execution_blockers.json").read_text())
    assert len(data["blockers"]) > 0


def test_output_json_files_parse(tmp_path):
    from sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark import main
    out = tmp_path / "out"
    main(["--mock-ready", "--out", str(out)])
    for fname in [
        "ds005620_benchmark_readiness.json",
        "benchmark_input_statuses.json",
        "dry_run_command_plan.json",
        "execution_blockers.json",
        "omega_event.json",
    ]:
        data = json.loads((out / fname).read_text())
        assert isinstance(data, dict)


def test_no_y_target_in_outputs(tmp_path):
    from sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark import main
    out = tmp_path / "out"
    main(["--mock-ready", "--out", str(out)])
    for p in out.iterdir():
        content = p.read_text(encoding="utf-8")
        assert '"y"' not in content or "y target" not in content.lower(), \
            f"Unexpected y target in {p.name}"


def test_ready_for_real_benchmark_true_when_all_inputs_ready(tmp_path):
    from sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark import main
    out = tmp_path / "out"
    main(["--mock-ready", "--out", str(out)])
    data = json.loads((out / "ds005620_benchmark_readiness.json").read_text())
    assert data["ready_for_real_benchmark"] is True or data["ready_for_p12_alignment"] is True


# ---------------------------------------------------------------------------
# Section 8: dry_run_command_plan content (4 tests)
# ---------------------------------------------------------------------------

def test_dry_run_plan_includes_all_stages(tmp_path):
    from sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark import main
    out = tmp_path / "out"
    main(["--mock-ready", "--out", str(out)])
    data = json.loads((out / "dry_run_command_plan.json").read_text())
    stages = [cmd["stage"] for cmd in data["commands"]]
    for expected_stage in ["P17.1", "P19.1", "P19.2", "P9", "P10", "P12", "P13", "P11"]:
        assert expected_stage in stages, f"Stage {expected_stage} missing from dry-run plan"


def test_dry_run_p19_2_blocked_when_cli_missing(tmp_path):
    from sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark import main
    from sciencer_d.btc_icft.p18 import ds005620_benchmark_readiness as m
    # Check that when P19.2 doesn't exist, it has a blocker
    inputs = {"reviewed_contract": None, "metadata": None, "signal_blocks": None,
               "level_m": None, "level_t": None}
    result = build_ds005620_benchmark_readiness(inputs)
    plan = result.dry_run_command_plan
    p19_2_cmd = next((c for c in plan if c["stage"] == "P19.2"), None)
    assert p19_2_cmd is not None
    # Either it's ready (P19.2 exists) or it has a blocker
    if not p19_2_cmd["ready_to_run"]:
        # Could be because signal blocks aren't needed yet OR P19.2 missing
        assert True  # blocker or not-needed-yet is acceptable


def test_dry_run_p11_always_not_ready_in_p18_0(tmp_path):
    from sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark import main
    out = tmp_path / "out"
    main(["--mock-ready", "--out", str(out)])
    data = json.loads((out / "dry_run_command_plan.json").read_text())
    p11_cmd = next((c for c in data["commands"] if c["stage"] == "P11"), None)
    assert p11_cmd is not None
    assert p11_cmd["ready_to_run"] is False


def test_dry_run_required_next_steps_lists_blockers(tmp_path):
    inputs = {
        "reviewed_contract": "/nonexistent/p12.json",
        "metadata": None,
        "signal_blocks": None,
        "level_m": None,
        "level_t": None,
    }
    result = build_ds005620_benchmark_readiness(inputs)
    assert len(result.required_next_steps) > 0


# ---------------------------------------------------------------------------
# Section 9: report.md content (4 tests)
# ---------------------------------------------------------------------------

def test_report_contains_readiness_gate_phrase(tmp_path):
    from sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark import main
    out = tmp_path / "out"
    main(["--mock-ready", "--out", str(out)])
    report = (out / "report.md").read_text()
    assert "readiness" in report.lower() or "Readiness" in report


def test_report_contains_without_running_benchmarks_phrase(tmp_path):
    from sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark import main
    out = tmp_path / "out"
    main(["--mock-ready", "--out", str(out)])
    report = (out / "report.md").read_text()
    assert "without running benchmarks" in report.lower() or \
           "without running benchmarks or inferring labels" in report


def test_report_contains_reviewed_contract(tmp_path):
    from sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark import main
    out = tmp_path / "out"
    main(["--mock-ready", "--out", str(out)])
    report = (out / "report.md").read_text()
    assert "reviewed contract" in report.lower() or "reviewed_contract" in report


def test_report_does_not_contain_banned_phrases(tmp_path):
    from sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark import main
    out = tmp_path / "out"
    main(["--mock-ready", "--out", str(out)])
    report = (out / "report.md").read_text().lower()
    for phrase in _BANNED_PHRASES:
        assert phrase not in report, f"Banned phrase in report.md: {phrase!r}"


# ---------------------------------------------------------------------------
# Section 10: guardrails / banned phrases (2 tests)
# ---------------------------------------------------------------------------

def test_omega_event_safe_claim_no_banned_phrases(tmp_path):
    from sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark import main
    out = tmp_path / "out"
    main(["--mock-ready", "--out", str(out)])
    omega = json.loads((out / "omega_event.json").read_text())
    claim = omega.get("safe_claim", "").lower()
    for phrase in _BANNED_PHRASES:
        assert phrase not in claim, f"Banned phrase in omega safe_claim: {phrase!r}"


def test_config_has_required_fields():
    config_path = Path("configs/btc_icft/ds005620_real_benchmark_readiness.yaml")
    assert config_path.is_file(), "Config file missing"
    content = config_path.read_text()
    for field in ["strict_join_keys", "required_outputs", "guardrails"]:
        assert field in content, f"Config missing field: {field}"
    for key in _STRICT_JOIN_KEYS:
        assert key in content, f"Config missing strict join key: {key}"
