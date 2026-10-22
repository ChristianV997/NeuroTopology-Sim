"""Deterministic gates for the Batch 3 falsification matrix.

These tests do not fit models, fetch data, or emit a scientific PASS.
"""

from __future__ import annotations

import hashlib
import json
import socket
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "configs" / "scientific_falsification" / "batch3_falsification_matrix.yaml"
DOC = ROOT / "docs" / "scientific_falsification" / "batch3_adversarial_review.md"

REQUIRED_CLAIMS = {
    "HOI-VS-PAIRWISE",
    "HOS-VS-CFC",
    "RESP-AUTONOMIC",
    "DISCERNMENT-CONSTRUCTS",
    "TOPOLOGY-PROXY",
    "EVIDENCE-SEPARATION",
    "CONFOUND-LEAKAGE",
    "MULTIPLICITY-SAMPLE",
    "NO-SCIENTIFIC-PASS",
    "MISSING-SUBJECTS",
}
REQUIRED_NULLS = {
    "flat",
    "gaussian",
    "phase_shuffle",
    "label_permutation",
    "circular_shift",
    "block_shuffle",
    "matched_variance",
    "matched_autocorrelation",
}
FORBIDDEN_PASS = {"PASS", "scientific_PASS", "FORMAL_BAYES_FACTOR"}


def load_matrix(path: Path = MATRIX) -> dict:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("matrix must be a mapping")
    return doc


def evaluate(doc: dict) -> dict:
    issues: list[str] = []
    if doc.get("scientific_pass") is not False:
        issues.append("scientific_pass must be false")
    if doc.get("formal_bayes_factor") is not None or doc.get("k_value") is not None:
        issues.append("formal k must be null")
    outcomes = set(doc.get("allowed_outcomes") or [])
    if FORBIDDEN_PASS & outcomes:
        issues.append("PASS outcome present")
    claims = {item.get("claim_id") for item in doc.get("claims") or []}
    if not REQUIRED_CLAIMS.issubset(claims):
        issues.append("missing claim")
    nulls = set(doc.get("null_models_required") or [])
    if not REQUIRED_NULLS.issubset(nulls):
        issues.append("missing null")
    splits = set(doc.get("splits_required") or [])
    if not {"subject_held_out", "session_held_out", "forward_time"}.issubset(splits):
        issues.append("missing split")
    multi = doc.get("gates") or {}
    if multi.get("unknown_n_tests_is_one") is not False:
        issues.append("missing multiplicity policy")
    if multi.get("scientific_pass_allowed") is not False:
        issues.append("scientific pass allowed")
    sample = doc.get("sample_requirements") or {}
    if int(sample.get("minimum_paired_subjects") or 0) < 20:
        issues.append("sample too small")
    phrases = " ".join(doc.get("forbidden_phrases") or []).lower()
    for token in ("consciousness", "equanimity", "quantum", "topological charge", "bayes"):
        if token not in phrases:
            issues.append(f"missing forbidden phrase family: {token}")
    if (doc.get("gates") or {}).get("synthetic_to_empirical") is not False:
        issues.append("synthetic-only protocol")
    if (doc.get("gates") or {}).get("missing_subject_zero_fill") is not False:
        issues.append("missing subjects zero-filled")
    return {
        "complete": not issues,
        "issues": issues,
        "scientific_pass": False,
        "formal_bayes_factor": None,
    }


def test_complete_matrix() -> None:
    report = evaluate(load_matrix())
    assert report["complete"] is True
    assert report["scientific_pass"] is False
    assert report["formal_bayes_factor"] is None
    text = DOC.read_text(encoding="utf-8").lower()
    assert "does not validate the theory" in text
    assert "not empirical evidence" in text or "not an empirical result" in text


def test_missing_null() -> None:
    doc = load_matrix()
    doc["null_models_required"] = []
    assert evaluate(doc)["complete"] is False


def test_missing_split() -> None:
    doc = load_matrix()
    doc["splits_required"] = ["subject_held_out"]
    assert evaluate(doc)["complete"] is False


def test_ambiguous_outcome() -> None:
    doc = load_matrix()
    doc["allowed_outcomes"] = ["MAYBE", "PASS"]
    assert evaluate(doc)["complete"] is False


def test_missing_multiplicity() -> None:
    doc = load_matrix()
    doc["gates"]["unknown_n_tests_is_one"] = True
    assert evaluate(doc)["complete"] is False


def test_synthetic_only_blocked() -> None:
    doc = load_matrix()
    doc["gates"]["synthetic_to_empirical"] = True
    assert evaluate(doc)["complete"] is False


def test_missing_subjects_not_zero_filled() -> None:
    doc = load_matrix()
    doc["gates"]["missing_subject_zero_fill"] = True
    assert evaluate(doc)["complete"] is False


def test_no_scientific_pass_gate() -> None:
    doc = load_matrix()
    assert doc["claims"]
    assert all(item.get("claim_id") for item in doc["claims"])
    doc["scientific_pass"] = True
    assert evaluate(doc)["complete"] is False
    assert evaluate(load_matrix())["scientific_pass"] is False


def test_deterministic_finite_json() -> None:
    dumped = yaml.dump(load_matrix(), sort_keys=True)
    assert dumped == yaml.dump(load_matrix(), sort_keys=True)
    digest_a = hashlib.sha256(MATRIX.read_bytes()).hexdigest()
    digest_b = hashlib.sha256(MATRIX.read_bytes()).hexdigest()
    assert digest_a == digest_b
    payload = json.dumps(load_matrix(), sort_keys=True, default=str, allow_nan=False)
    assert "NaN" not in payload
    assert json.loads(payload)["scientific_pass"] is False


def test_no_network() -> None:
    original = socket.socket

    def blocked(*_args, **_kwargs):
        raise AssertionError("network was used")

    socket.socket = blocked  # type: ignore[assignment]
    try:
        report = evaluate(load_matrix())
        assert report["scientific_pass"] is False
    finally:
        socket.socket = original  # type: ignore[assignment]


def test_campaign_execution_states_and_terminal_transitions() -> None:
    doc = load_matrix()
    expected_states = {
        "PLANNING",
        "REGISTERED",
        "EXECUTING",
        "INTERRUPTED",
        "RESUMED",
        "COMPLETED",
        "ABORTED",
    }
    states = set(doc.get("campaign_execution_states") or [])
    assert expected_states == states

    terminal_states = set(doc.get("terminal_states") or [])
    assert terminal_states == {"COMPLETED", "ABORTED"}

    transitions = doc.get("valid_state_transitions") or {}
    assert isinstance(transitions, dict)
    for state in expected_states:
        assert state in transitions

    # Terminal states must have zero outgoing transitions
    for term in terminal_states:
        assert transitions[term] == []

    # Verify transitions from planning, executing, interrupted, resumed
    assert set(transitions["PLANNING"]) == {"REGISTERED", "ABORTED"}
    assert set(transitions["REGISTERED"]) == {"EXECUTING", "ABORTED"}
    assert set(transitions["EXECUTING"]) == {"INTERRUPTED", "COMPLETED", "ABORTED"}
    assert set(transitions["INTERRUPTED"]) == {"RESUMED", "ABORTED"}
    assert set(transitions["RESUMED"]) == {"INTERRUPTED", "COMPLETED", "ABORTED"}


def test_resumability_policy_invariants() -> None:
    doc = load_matrix()
    policy = doc.get("resumability_policy") or {}
    assert policy.get("allowed") is True
    assert policy.get("require_exact_hash_match") is True
    assert policy.get("require_checkpoint_manifest") is True
    assert policy.get("recompute_interrupted_units_only") is True
    assert policy.get("prohibit_terminal_state_reopening") is True
    assert policy.get("prohibit_non_protocol_state") is True


def test_proposed_thresholds_not_power_validation() -> None:
    doc = load_matrix()
    assert doc.get("scientific_pass") is False
    assert doc.get("empirical_claim_allowed") is False

    limits = doc.get("protocol_limits") or {}
    assert limits.get("scientific_pass") is False
    assert limits.get("empirical_claim_allowed") is False
    assert limits.get("proposed_thresholds_are_power_validation") is False

    sample = doc.get("sample_requirements") or {}
    assert sample.get("proposed_thresholds_power_validated") is False

    text = DOC.read_text(encoding="utf-8").lower()
    assert "proposed thresholds are not power validation" in text
    assert "protocol-only" in text or "protocol floor" in text
