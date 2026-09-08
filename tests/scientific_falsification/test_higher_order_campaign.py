"""Protocol tests for the higher-order campaign preregistration.

These tests audit the locked YAML. They do not fit models, fetch data,
or emit a scientific PASS.
"""
from __future__ import annotations

import hashlib
import json
import socket
from copy import deepcopy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = ROOT / "configs" / "scientific_falsification" / "higher_order_campaign.yaml"
DOC_PATH = ROOT / "docs" / "scientific_falsification" / "higher_order_campaign_audit.md"

REQUIRED_LADDER = [
    "power_spectral_density",
    "pairwise_functional_connectivity",
    "triadic_functional_connectivity",
    "higher_order_spectra",
    "directed_hypergraph",
]
REQUIRED_NULLS = {
    "flat", "gaussian", "phase_shuffle", "label_permutation",
    "circular_shift", "block_shuffle", "matched_variance", "matched_autocorrelation",
}
REQUIRED_OUTCOMES = {
    "NO_INCREMENTAL_GAIN", "GAIN_UNSTABLE", "GAIN_CONFUNDED", "GAIN_NOT_REPLICATED",
    "INSUFFICIENT_POWER", "INCONCLUSIVE", "FORMAL_FORECAST_EVIDENCE_PENDING_REVIEW",
}
REQUIRED_REJECTS = {
    "training_only_improvements", "test_set_tuning", "post_hoc_feature_selection",
    "subject_leakage", "uncorrected_multiple_comparisons", "unverified_condition_labels",
    "synthetic_empirical_claims", "prediction_interpreted_as_causation",
    "triadic_dependence_interpreted_as_biological_mechanism",
    "respiration_interpreted_as_equanimity",
    "discernment_inferred_from_eeg_without_behavioral_measurement",
}


def load_protocol(path: Path = PROTOCOL_PATH) -> dict:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("protocol must be a mapping")
    return doc


def validate_protocol(doc: dict) -> dict:
    issues: list[str] = []
    if doc.get("scientific_pass") is not False:
        issues.append("scientific_pass must be false")
    if doc.get("formal_bayes_factor") is not None:
        issues.append("formal_bayes_factor must be null")
    if doc.get("k_value") is not None:
        issues.append("k_value must be null")
    if "PASS" in str(doc.get("outcomes")):
        issues.append("outcomes must not include PASS")
    ladder = [item.get("family") for item in (doc.get("campaign") or {}).get("ladder") or []]
    if ladder != REQUIRED_LADDER:
        issues.append("campaign ladder is incomplete or reordered")
    phys = (doc.get("campaign") or {}).get("physiology_autonomic") or {}
    if phys.get("role") != "candidate_predictors_or_controls":
        issues.append("physiology/autonomic role missing")
    splits = doc.get("splits") or {}
    for name in ("subject_held_out", "session_held_out", "forward_time"):
        if not (splits.get(name) or {}).get("required"):
            issues.append(f"missing split: {name}")
    nulls = set((doc.get("null_models") or {}).get("models") or [])
    if not (doc.get("null_models") or {}).get("required"):
        issues.append("missing null")
    if not REQUIRED_NULLS.issubset(nulls):
        issues.append("missing null")
    multi = doc.get("multiplicity") or {}
    if not multi.get("required") or not multi.get("correction"):
        issues.append("missing multiplicity policy")
    if multi.get("unknown_n_tests_not_one") is not True:
        issues.append("unknown n_tests must not be treated as one")
    outcomes = set(doc.get("outcomes") or [])
    if outcomes != REQUIRED_OUTCOMES:
        issues.append("ambiguous outcome set")
    rejects = set(doc.get("rejected_practices") or [])
    if not REQUIRED_REJECTS.issubset(rejects):
        issues.append("rejected-practice list incomplete")
    if doc.get("synthetic_demo") is True and doc.get("empirical_claim_allowed") is True:
        issues.append("synthetic-only protocol cannot make an empirical claim")
    if doc.get("synthetic_demo") is True:
        issues.append("synthetic-only protocol")
    target = doc.get("target") or {}
    if not target.get("transition") or not (target.get("prediction_horizon") or {}).get("locked"):
        issues.append("target or horizon not locked")
    if not (doc.get("preprocessing") or {}).get("lock"):
        issues.append("preprocessing lock missing")
    if not (doc.get("falsification_thresholds") or {}).get("replication", {}).get("required"):
        issues.append("replication requirement missing")
    return {"complete": not issues, "issues": issues, "scientific_pass": False, "formal_bayes_factor": None}


def test_complete_protocol() -> None:
    report = validate_protocol(load_protocol())
    assert report["complete"] is True
    assert report["scientific_pass"] is False
    assert report["formal_bayes_factor"] is None
    assert DOC_PATH.is_file()
    assert "preregistered protocol is not empirical evidence" in DOC_PATH.read_text(encoding="utf-8").lower()


def test_missing_null() -> None:
    doc = load_protocol()
    doc["null_models"] = {"required": False, "models": []}
    report = validate_protocol(doc)
    assert report["complete"] is False
    assert any("null" in item for item in report["issues"])


def test_missing_split() -> None:
    doc = load_protocol()
    doc["splits"]["forward_time"]["required"] = False
    report = validate_protocol(doc)
    assert report["complete"] is False
    assert any("forward_time" in item for item in report["issues"])


def test_ambiguous_outcome() -> None:
    doc = load_protocol()
    doc["outcomes"] = ["MAYBE", "PASS"]
    report = validate_protocol(doc)
    assert report["complete"] is False
    assert any("outcome" in item or "PASS" in item for item in report["issues"])


def test_missing_multiplicity_policy() -> None:
    doc = load_protocol()
    doc["multiplicity"] = {"required": False}
    report = validate_protocol(doc)
    assert report["complete"] is False
    assert any("multiplicity" in item for item in report["issues"])


def test_synthetic_only_protocol() -> None:
    doc = load_protocol()
    doc["synthetic_demo"] = True
    doc["empirical_claim_allowed"] = True
    report = validate_protocol(doc)
    assert report["complete"] is False
    assert any("synthetic" in item for item in report["issues"])
    assert report["scientific_pass"] is False


def test_deterministic_serialization() -> None:
    first = yaml.dump(load_protocol(), sort_keys=True)
    second = yaml.dump(load_protocol(), sort_keys=True)
    assert first == second
    assert hashlib.sha256(PROTOCOL_PATH.read_bytes()).hexdigest() == hashlib.sha256(PROTOCOL_PATH.read_bytes()).hexdigest()
    dumped = json.dumps(load_protocol(), sort_keys=True, default=str)
    assert json.dumps(load_protocol(), sort_keys=True, default=str) == dumped


def test_no_network_operation() -> None:
    original = socket.socket

    def blocked(*_args, **_kwargs):
        raise AssertionError("network was used")

    socket.socket = blocked
    try:
        report = validate_protocol(load_protocol())
        assert report["scientific_pass"] is False
        assert deepcopy(report)["formal_bayes_factor"] is None
    finally:
        socket.socket = original
