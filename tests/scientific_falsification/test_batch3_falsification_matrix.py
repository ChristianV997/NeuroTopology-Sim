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
REQUIRED_SPLITS = {"subject_held_out", "session_held_out", "forward_time"}
REQUIRED_POSITIVE_CONTROLS = {
    "known_synthetic_pairwise_coupling",
    "known_synthetic_power_change",
}
REQUIRED_NEGATIVE_CONTROLS = {
    "independent_gaussian",
    "phase_shuffled_spectrum_preserved",
}
REQUIRED_CONFOUND_CONTROLS = {
    "volume_conduction_imaginary_coherence",
    "respiration_rate",
    "heart_rate",
    "heart_rate_variability",
    "motion",
    "global_signal",
    "temporal_smoothing_matched",
}
EXPECTED_CAMPAIGN_STATES = {
    "PLANNING",
    "REGISTERED",
    "EXECUTING",
    "INTERRUPTED",
    "RESUMED",
    "COMPLETED",
    "ABORTED",
}
EXPECTED_TERMINAL_STATES = {"COMPLETED", "ABORTED"}
FORBIDDEN_PASS = {"PASS", "scientific_PASS", "FORMAL_BAYES_FACTOR"}


def _strict_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def load_matrix(path: Path = MATRIX) -> dict:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("matrix must be a mapping")
    return doc


def evaluate(doc: dict) -> dict:
    issues: list[str] = []
    if not isinstance(doc, dict):
        return {
            "complete": False,
            "issues": ["matrix must be a mapping"],
            "scientific_pass": False,
            "formal_bayes_factor": None,
            "k_value": None,
            "empirical_claim_allowed": False,
            "proposed_thresholds_are_power_validation": False,
        }
    if doc.get("schema") != "NeuroTopology.Batch3FalsificationMatrix.v1":
        issues.append("invalid or missing schema")
    if not isinstance(doc.get("matrix_id"), str) or not doc.get("matrix_id", "").strip():
        issues.append("invalid or missing matrix_id")
    if doc.get("status") != "FALSIFICATION_HARNESS_ONLY":
        issues.append("status must be FALSIFICATION_HARNESS_ONLY")
    if doc.get("evidence_class") != "preregistered_protocol":
        issues.append("evidence_class must be preregistered_protocol")
    if doc.get("scientific_pass") is not False:
        issues.append("scientific_pass must be false")
    if doc.get("empirical_claim_allowed") is not False:
        issues.append("empirical_claim_allowed must be false")
    if doc.get("synthetic_demo") is not False:
        issues.append("synthetic_demo must be false")
    if doc.get("rea_status") != "REA_UNAVAILABLE":
        issues.append("rea_status must be REA_UNAVAILABLE")
    if doc.get("formal_bayes_factor") is not None or doc.get("k_value") is not None:
        issues.append("formal k must be null")

    limits = doc.get("protocol_limits")
    if not isinstance(limits, dict):
        issues.append("missing protocol_limits")
    else:
        if limits.get("scientific_pass") is not False:
            issues.append("protocol_limits.scientific_pass must be false")
        if limits.get("empirical_claim_allowed") is not False:
            issues.append("protocol_limits.empirical_claim_allowed must be false")
        if limits.get("proposed_thresholds_are_power_validation") is not False:
            issues.append("protocol_limits.proposed_thresholds_are_power_validation must be false")
        if limits.get("proposed_splits_nulls_controls_are_proposals_only") is not True:
            issues.append("protocol_limits.proposed_splits_nulls_controls_are_proposals_only must be true")
        if limits.get("completeness_implies_scientific_adequacy") is not False:
            issues.append("protocol_limits.completeness_implies_scientific_adequacy must be false")

    allowed_outcomes_raw = doc.get("allowed_outcomes")
    forbidden_outcomes_raw = doc.get("forbidden_outcomes")
    if not isinstance(allowed_outcomes_raw, list) or not allowed_outcomes_raw:
        issues.append("missing allowed_outcomes")
        outcomes: set[str] = set()
    else:
        outcomes = {str(x) for x in allowed_outcomes_raw}
    if not isinstance(forbidden_outcomes_raw, list) or not FORBIDDEN_PASS.issubset(set(forbidden_outcomes_raw)):
        issues.append("missing forbidden_outcomes")
    if FORBIDDEN_PASS & outcomes or any("pass" in o.lower() for o in outcomes):
        issues.append("PASS outcome present")

    claims_raw = doc.get("claims")
    if not isinstance(claims_raw, list) or not all(isinstance(item, dict) for item in claims_raw):
        issues.append("claims must be a list of mappings")
        claims: set[str] = set()
    else:
        claims = {str(item.get("claim_id")) for item in claims_raw if item.get("claim_id")}
        for item in claims_raw:
            if item.get("blocked_if_missing_baseline") is not True:
                issues.append(f"claim {item.get('claim_id')} must block if baseline is missing")
            if "scientific_pass" in item and item.get("scientific_pass") is not False:
                issues.append(f"claim {item.get('claim_id')} scientific_pass must be false")
            if "formal_bayes_factor" in item and item.get("formal_bayes_factor") is not None:
                issues.append(f"claim {item.get('claim_id')} formal_bayes_factor must be null")
            if "k_value" in item and item.get("k_value") is not None:
                issues.append(f"claim {item.get('claim_id')} k_value must be null")
    if not REQUIRED_CLAIMS.issubset(claims):
        issues.append("missing claim")

    nulls_raw = doc.get("null_models_required")
    nulls = set(nulls_raw) if isinstance(nulls_raw, list) else set()
    if not REQUIRED_NULLS.issubset(nulls):
        issues.append("missing null")
    min_null_reps = _strict_int(doc.get("minimum_null_replicates"))
    if min_null_reps is None or min_null_reps < 100:
        issues.append("minimum_null_replicates must be an integer >= 100")

    splits_raw = doc.get("splits_required")
    splits = set(splits_raw) if isinstance(splits_raw, list) else set()
    if not REQUIRED_SPLITS.issubset(splits):
        issues.append("missing split")

    pos_raw = doc.get("positive_controls")
    neg_raw = doc.get("negative_controls")
    conf_raw = doc.get("confound_controls")
    if not isinstance(pos_raw, list) or not REQUIRED_POSITIVE_CONTROLS.issubset(set(pos_raw)):
        issues.append("missing positive_controls")
    if not isinstance(neg_raw, list) or not REQUIRED_NEGATIVE_CONTROLS.issubset(set(neg_raw)):
        issues.append("missing negative_controls")
    if not isinstance(conf_raw, list) or not REQUIRED_CONFOUND_CONTROLS.issubset(set(conf_raw)):
        issues.append("missing confound_controls")

    gates = doc.get("gates")
    if not isinstance(gates, dict):
        issues.append("missing gates")
    else:
        for gate_key in (
            "scientific_pass_allowed",
            "formal_k_allowed",
            "synthetic_to_empirical",
            "unknown_n_tests_is_one",
            "missing_subject_zero_fill",
            "prediction_as_causation",
            "eeg_only_discernment",
            "respiration_as_equanimity",
            "beta1_as_spatial_charge",
        ):
            if gates.get(gate_key) is not False:
                issues.append(f"gate {gate_key} must be false")

    sample = doc.get("sample_requirements")
    if not isinstance(sample, dict):
        issues.append("missing sample_requirements")
    else:
        min_paired = _strict_int(sample.get("minimum_paired_subjects"))
        min_held_out = _strict_int(sample.get("minimum_held_out_subjects"))
        min_sessions = _strict_int(sample.get("minimum_sessions_per_split"))
        if min_paired is None or min_paired < 20:
            issues.append("sample too small")
        if min_held_out is None or min_held_out < 8:
            issues.append("held-out sample too small")
        if min_sessions is None or min_sessions < 2:
            issues.append("minimum_sessions_per_split too small")
        if sample.get("below_minimum_outcome") != "INSUFFICIENT_POWER":
            issues.append("below_minimum_outcome must be INSUFFICIENT_POWER")
        if sample.get("missing_subjects_policy") != "exclude_and_report":
            issues.append("invalid missing_subjects_policy")
        if sample.get("failed_subjects_policy") != "exclude_and_report_never_impute_as_null_effect":
            issues.append("invalid failed_subjects_policy")
        if sample.get("proposed_thresholds_power_validated") is not False:
            issues.append("sample_requirements.proposed_thresholds_power_validated must be false")

    replication = doc.get("replication")
    if not isinstance(replication, dict):
        issues.append("missing replication")
    else:
        if replication.get("required") is not True:
            issues.append("replication.required must be true")
        if replication.get("independent_cohort_or_site") is not True:
            issues.append("replication.independent_cohort_or_site must be true")
        if replication.get("failure_outcome") != "GAIN_NOT_REPLICATED":
            issues.append("replication.failure_outcome must be GAIN_NOT_REPLICATED")

    states_raw = doc.get("campaign_execution_states")
    term_raw = doc.get("terminal_states")
    transitions = doc.get("valid_state_transitions")
    resumability = doc.get("resumability_policy")
    if not isinstance(states_raw, list) or set(states_raw) != EXPECTED_CAMPAIGN_STATES:
        issues.append("invalid campaign_execution_states")
    if not isinstance(term_raw, list) or set(term_raw) != EXPECTED_TERMINAL_STATES:
        issues.append("invalid terminal_states")
    if not isinstance(transitions, dict) or set(transitions.keys()) != EXPECTED_CAMPAIGN_STATES:
        issues.append("invalid valid_state_transitions")
    else:
        for term in EXPECTED_TERMINAL_STATES:
            if transitions.get(term) != []:
                issues.append(f"terminal state {term} must have empty transitions")
    if not isinstance(resumability, dict):
        issues.append("missing resumability_policy")
    else:
        for res_key in (
            "allowed",
            "require_exact_hash_match",
            "require_checkpoint_manifest",
            "recompute_interrupted_units_only",
            "prohibit_terminal_state_reopening",
            "prohibit_non_protocol_state",
        ):
            if resumability.get(res_key) is not True:
                issues.append(f"resumability_policy.{res_key} must be true")

    phrases_raw = doc.get("forbidden_phrases")
    phrases = " ".join(str(x) for x in phrases_raw).lower() if isinstance(phrases_raw, list) else ""
    for token in ("consciousness", "equanimity", "quantum", "topological charge", "bayes"):
        if token not in phrases:
            issues.append(f"missing forbidden phrase family: {token}")

    return {
        "complete": not issues,
        "issues": issues,
        "scientific_pass": False,
        "formal_bayes_factor": None,
        "k_value": None,
        "empirical_claim_allowed": False,
        "proposed_thresholds_are_power_validation": False,
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


def test_contradictory_flags_fail_closed() -> None:
    # Contradictory empirical_claim_allowed or protocol_limits flags must fail evaluate()
    for mutator in (
        lambda d: d.__setitem__("empirical_claim_allowed", True),
        lambda d: d["protocol_limits"].__setitem__("scientific_pass", True),
        lambda d: d["protocol_limits"].__setitem__("empirical_claim_allowed", True),
        lambda d: d["protocol_limits"].__setitem__("proposed_thresholds_are_power_validation", True),
        lambda d: d["sample_requirements"].__setitem__("proposed_thresholds_power_validated", True),
        lambda d: d["gates"].__setitem__("formal_k_allowed", True),
        lambda d: d["gates"].__setitem__("prediction_as_causation", True),
        lambda d: d["gates"].__setitem__("eeg_only_discernment", True),
        lambda d: d["gates"].__setitem__("respiration_as_equanimity", True),
        lambda d: d["gates"].__setitem__("beta1_as_spatial_charge", True),
        lambda d: d["replication"].__setitem__("required", False),
        lambda d: d["replication"].__setitem__("independent_cohort_or_site", False),
        lambda d: d["claims"][8].__setitem__("scientific_pass", True),
        lambda d: d["claims"][8].__setitem__("formal_bayes_factor", 10.0),
    ):
        doc = load_matrix()
        mutator(doc)
        report = evaluate(doc)
        assert report["complete"] is False
        assert report["scientific_pass"] is False
        assert report["formal_bayes_factor"] is None


def test_missing_fields_and_controls_fail_closed() -> None:
    for missing_key in (
        "schema",
        "matrix_id",
        "status",
        "evidence_class",
        "protocol_limits",
        "sample_requirements",
        "replication",
        "positive_controls",
        "negative_controls",
        "confound_controls",
        "campaign_execution_states",
        "terminal_states",
        "valid_state_transitions",
        "resumability_policy",
    ):
        doc = load_matrix()
        doc.pop(missing_key, None)
        report = evaluate(doc)
        assert report["complete"] is False
        assert report["scientific_pass"] is False


def test_malformed_values_fail_closed_without_uncaught_exception() -> None:
    for mutator in (
        lambda d: d["sample_requirements"].__setitem__("minimum_paired_subjects", "twenty"),
        lambda d: d["sample_requirements"].__setitem__("minimum_paired_subjects", True),
        lambda d: d["sample_requirements"].__setitem__("minimum_held_out_subjects", 3),
        lambda d: d["sample_requirements"].__setitem__("minimum_sessions_per_split", 1),
        lambda d: d.__setitem__("minimum_null_replicates", "not-an-int"),
        lambda d: d.__setitem__("minimum_null_replicates", 10),
        lambda d: d.__setitem__("formal_bayes_factor", 3.2),
        lambda d: d.__setitem__("k_value", 5.0),
        lambda d: d["valid_state_transitions"].__setitem__("COMPLETED", ["EXECUTING"]),
        lambda d: d["resumability_policy"].__setitem__("prohibit_terminal_state_reopening", False),
        lambda d: d["claims"].append("not-a-dict"),
    ):
        doc = load_matrix()
        mutator(doc)
        report = evaluate(doc)
        assert report["complete"] is False
        assert report["scientific_pass"] is False
        assert report["formal_bayes_factor"] is None


def test_complete_matrix_never_implies_scientific_success() -> None:
    doc = load_matrix()
    report = evaluate(doc)
    assert report["complete"] is True
    assert report["scientific_pass"] is False
    assert report["formal_bayes_factor"] is None
    assert report.get("k_value") is None
    assert report.get("empirical_claim_allowed", False) is False
    assert report.get("proposed_thresholds_are_power_validation", False) is False
    assert doc.get("status") == "FALSIFICATION_HARNESS_ONLY"
    assert doc.get("evidence_class") == "preregistered_protocol"
