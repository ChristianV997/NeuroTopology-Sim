"""The gate is read, never written. A mapping cannot declare, carry, or promote evidence."""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

import shared.measurement_hypothesis.validate as validate_module

REPO_ROOT = Path(__file__).resolve().parents[2]


def _codes(report):
    return {error["code"] for error in report["errors"]}


@pytest.mark.parametrize("path, key, value", [
    (("top",), "evidence_state", "empirical"),
    (("top",), "evidence_class", "engineering_fact"),
    (("top",), "scientific_pass", True),
    (("top",), "formal_bayes_factor", 0.5),
    (("top",), "gate_decision", "CLAIM_ADMISSIBLE"),
    (("interpretation",), "evidence_ready", True),
    (("interpretation",), "scientific_eligibility", True),
    (("operator",), "promotion", "EMPIRICAL"),
    (("measurement",), "evidence_promotion", "release"),
])
def test_evidence_or_promotion_field_is_rejected_at_any_depth(valid_mapping, check, path, key, value):
    target = valid_mapping if path == ("top",) else valid_mapping[path[0]]
    target[key] = value
    report = check(valid_mapping)
    assert report["contract_status"] == "REJECTED"
    assert "EVIDENCE_FIELD_NOT_PERMITTED" in _codes(report)
    assert report["evidence_ready"] is False


def test_evidence_key_inside_a_source_reference_is_rejected(valid_mapping, check):
    valid_mapping["sources"][0]["scientific_pass"] = True
    assert "EVIDENCE_FIELD_NOT_PERMITTED" in _codes(check(valid_mapping))


def test_report_never_reports_eligibility_or_a_formal_factor(valid_mapping, check):
    report = check(valid_mapping)
    assert report["evidence_ready"] is False
    assert report["gate"]["scientific_eligibility"] is False
    assert report["gate"]["scientific_pass"] is False
    assert report["gate"]["formal_bayes_factor"] is None


def test_gate_block_is_recorded_not_stored_by_the_mapping(valid_mapping, check):
    # The gate result is derived each time from the proposal. A mapping cannot supply one.
    valid_mapping["gate"] = {"decision": "CLAIM_ADMISSIBLE", "scientific_eligibility": True}
    report = check(valid_mapping)
    assert "EVIDENCE_FIELD_NOT_PERMITTED" in _codes(report)
    assert report["gate"]["scientific_eligibility"] is False


def test_gate_block_that_blocks_the_mapping_is_enforced(valid_mapping, check, monkeypatch):
    monkeypatch.setattr(validate_module, "evaluate_claim", lambda _claim: None)
    monkeypatch.setattr(
        validate_module,
        "serialize_json",
        lambda _result: json.dumps({"decision": "CLAIM_REJECTED", "claim_class": "hypothesis",
                                    "reason_codes": ["UNVERIFIED_LABELS"], "scientific_eligibility": False,
                                    "scientific_pass": False}),
    )
    report = check(valid_mapping)
    assert "GATE_DECISION_BLOCKS_MAPPING" in _codes(report)
    assert report["gate"]["decision"] == "CLAIM_REJECTED"


def test_gate_eligibility_drift_is_detected(valid_mapping, check, monkeypatch):
    monkeypatch.setattr(validate_module, "evaluate_claim", lambda _claim: None)
    monkeypatch.setattr(
        validate_module,
        "serialize_json",
        lambda _result: json.dumps({"decision": "CLAIM_ADMISSIBLE", "claim_class": "hypothesis",
                                    "reason_codes": [], "scientific_eligibility": True,
                                    "scientific_pass": False}),
    )
    assert "GATE_ELIGIBILITY_UNEXPECTED" in _codes(check(valid_mapping))


def test_validation_makes_no_network_call(valid_mapping, check, monkeypatch):
    calls: list[object] = []

    def _forbidden(*args, **kwargs):
        calls.append(args)
        raise RuntimeError("network access attempted")

    monkeypatch.setattr(socket, "create_connection", _forbidden)
    monkeypatch.setattr(socket.socket, "connect", _forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
    assert check(valid_mapping)["contract_status"] == "VALID_HYPOTHESIS_MAPPING"
    assert calls == []


def test_cli_exit_codes_and_strict_json_output(tmp_path):
    fixture = REPO_ROOT / "tests" / "measurement_hypothesis" / "fixtures"
    ok = subprocess.run(
        [sys.executable, "-m", "shared.measurement_hypothesis", str(fixture / "valid_hypothetical_mapping.json"),
         "--as-of", "2026-10-16"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False, timeout=120,
    )
    assert ok.returncode == 0, ok.stderr
    assert json.loads(ok.stdout)["contract_status"] == "VALID_HYPOTHESIS_MAPPING"

    bad = subprocess.run(
        [sys.executable, "-m", "shared.measurement_hypothesis", str(fixture / "theory_term_leak.json"),
         "--as-of", "2026-10-16"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False, timeout=120,
    )
    assert bad.returncode == 1
    assert json.loads(bad.stdout)["contract_status"] == "REJECTED"


def test_cli_reports_unreadable_input_without_crashing(tmp_path):
    completed = subprocess.run(
        [sys.executable, "-m", "shared.measurement_hypothesis", str(tmp_path / "missing.json")],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False, timeout=120,
    )
    assert completed.returncode == 1
    report = json.loads(completed.stdout)
    assert report["errors"][0]["code"] == "MAPPING_UNREADABLE"
    assert report["evidence_ready"] is False
