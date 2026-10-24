"""Deterministic gates for the Batch 3 falsification matrix.

These tests do not fit models, fetch data, or emit a scientific PASS.
"""

from __future__ import annotations

import hashlib
import json
import re
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
EXPECTED_TRANSITIONS = {
    "PLANNING": {"REGISTERED", "ABORTED"},
    "REGISTERED": {"EXECUTING", "ABORTED"},
    "EXECUTING": {"INTERRUPTED", "COMPLETED", "ABORTED"},
    "INTERRUPTED": {"RESUMED", "ABORTED"},
    "RESUMED": {"INTERRUPTED", "COMPLETED", "ABORTED"},
    "COMPLETED": set(),
    "ABORTED": set(),
}
FORBIDDEN_PASS = {"PASS", "scientific_PASS", "FORMAL_BAYES_FACTOR"}
EXPECTED_DOWNGRADE_TARGETS = {"proxy_inference", "unsupported_claim"}
EXPECTED_CLAIM_EVIDENCE_CLASSES = {"hypothesis", "engineering_fact"}
EXPECTED_ALLOWED_OUTCOMES = {
    "NO_INCREMENTAL_GAIN",
    "GAIN_UNSTABLE",
    "GAIN_CONFUNDED",
    "GAIN_NOT_REPLICATED",
    "INSUFFICIENT_POWER",
    "INCONCLUSIVE",
    "FORMAL_FORECAST_EVIDENCE_PENDING_REVIEW",
    "BLOCKED_BY_MISSING_SUBJECTS",
    "BLOCKED_BY_LANGUAGE",
}
EXPECTED_MATRIX_KEYS = {
    "schema",
    "matrix_id",
    "status",
    "scientific_pass",
    "formal_bayes_factor",
    "k_value",
    "evidence_class",
    "empirical_claim_allowed",
    "synthetic_demo",
    "rea_status",
    "note",
    "protocol_limits",
    "campaign_execution_states",
    "terminal_states",
    "valid_state_transitions",
    "resumability_policy",
    "sample_requirements",
    "replication",
    "splits_required",
    "null_models_required",
    "minimum_null_replicates",
    "positive_controls",
    "negative_controls",
    "confound_controls",
    "forbidden_outcomes",
    "allowed_outcomes",
    "forbidden_phrases",
    "claims",
    "gates",
}
CLAIM_REQUIRED_KEYS = {
    "claim_id",
    "text",
    "category",
    "evidence_class",
    "falsification",
    "blocked_if_missing_baseline",
}
CLAIM_ALLOWED_KEYS = CLAIM_REQUIRED_KEYS | {
    "required_baselines",
    "required_controls",
    "downgrade_if_missing_baseline",
    "forbidden_interpretations",
    "required_instruments",
    "required_fields",
    "forbidden_conversions",
    "required_classes",
    "minimum_paired_subjects",
    "scientific_pass",
    "formal_bayes_factor",
    "k_value",
}


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys at every level."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict:
        self.flatten_mapping(node)
        mapping = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in mapping
            except TypeError as exc:
                raise ValueError("YAML mapping keys must be hashable") from exc
            if duplicate:
                raise ValueError(f"duplicate YAML mapping key: {key!r}")
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def _string_list(value: object, name: str, issues: list[str]) -> set[str] | None:
    """Validate a declared string list before using set operations on it."""
    if not isinstance(value, list):
        issues.append(f"{name} must be a list of strings")
        return None
    if any(not isinstance(item, str) or not item.strip() for item in value):
        issues.append(f"{name} must contain only non-empty strings")
        return None
    if len(value) != len(set(value)):
        issues.append(f"{name} must not contain duplicate entries")
    return set(value)


def _exact_keys(
    value: object,
    name: str,
    allowed: set[str],
    issues: list[str],
    *,
    required: set[str] | None = None,
) -> bool:
    if not isinstance(value, dict):
        issues.append(f"{name} must be a mapping")
        return False
    actual = set(value)
    required = allowed if required is None else required
    missing = required - actual
    unknown = actual - allowed
    if missing:
        issues.append(f"{name} is missing keys: {', '.join(sorted(missing))}")
    if unknown:
        issues.append(f"{name} has unsupported keys: {', '.join(sorted(map(str, unknown)))}")
    return not missing and not unknown


def _strict_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def load_matrix(path: Path = MATRIX) -> dict:
    doc = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
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
    _exact_keys(doc, "matrix", EXPECTED_MATRIX_KEYS, issues)
    if not isinstance(doc.get("note"), str) or not doc.get("note", "").strip():
        issues.append("note must be a non-empty string")
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
    # Top-level formal K fields must be present and explicitly null (unset-by-omission is not enough).
    if "formal_bayes_factor" not in doc or doc.get("formal_bayes_factor") is not None:
        issues.append("formal_bayes_factor must be present and null")
    if "k_value" not in doc or doc.get("k_value") is not None:
        issues.append("k_value must be present and null")

    limits = doc.get("protocol_limits")
    limits_keys = {
        "scientific_pass",
        "empirical_claim_allowed",
        "proposed_thresholds_are_power_validation",
        "proposed_splits_nulls_controls_are_proposals_only",
        "completeness_implies_scientific_adequacy",
        "note",
    }
    if _exact_keys(limits, "protocol_limits", limits_keys, issues):
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
        if not isinstance(limits.get("note"), str) or not limits["note"].strip():
            issues.append("protocol_limits.note must be a non-empty string")

    allowed_outcomes_raw = doc.get("allowed_outcomes")
    forbidden_outcomes_raw = doc.get("forbidden_outcomes")
    outcomes = _string_list(allowed_outcomes_raw, "allowed_outcomes", issues)
    if not outcomes:
        issues.append("missing allowed_outcomes")
    elif outcomes != EXPECTED_ALLOWED_OUTCOMES:
        issues.append("allowed_outcomes do not match the versioned protocol vocabulary")
    forbidden_outcomes = _string_list(forbidden_outcomes_raw, "forbidden_outcomes", issues)
    if forbidden_outcomes is None or not FORBIDDEN_PASS.issubset(forbidden_outcomes):
        issues.append("missing forbidden_outcomes")
    if outcomes is not None and (FORBIDDEN_PASS & outcomes or any("pass" in o.lower() for o in outcomes)):
        issues.append("PASS outcome present")

    claims_raw = doc.get("claims")
    if not isinstance(claims_raw, list) or not all(isinstance(item, dict) for item in claims_raw):
        issues.append("claims must be a list of mappings")
        claims: set[str] = set()
    else:
        claim_ids: list[str] = []
        for item in claims_raw:
            cid = item.get("claim_id")
            _exact_keys(
                item,
                f"claim {cid!r}",
                CLAIM_ALLOWED_KEYS,
                issues,
                required=CLAIM_REQUIRED_KEYS,
            )
            missing_claim_keys = CLAIM_REQUIRED_KEYS - set(item)
            if missing_claim_keys:
                issues.append(f"claim {cid!r} is missing required fields: {', '.join(sorted(missing_claim_keys))}")
            for key in ("claim_id", "text", "category", "evidence_class", "falsification"):
                if not isinstance(item.get(key), str) or not item.get(key, "").strip():
                    issues.append(f"claim {cid!r} {key} must be a non-empty string")
            evidence_class = item.get("evidence_class")
            if isinstance(evidence_class, str) and evidence_class not in EXPECTED_CLAIM_EVIDENCE_CLASSES:
                issues.append(f"claim {cid!r} evidence_class is not in the versioned claim vocabulary")
            if isinstance(cid, str) and cid.strip():
                claim_ids.append(cid)
            if item.get("blocked_if_missing_baseline") is not True:
                issues.append(f"claim {cid} must block if baseline is missing")
            for key in (
                "required_baselines",
                "required_controls",
                "forbidden_interpretations",
                "required_instruments",
                "required_fields",
                "forbidden_conversions",
                "required_classes",
            ):
                if key in item:
                    declared = _string_list(item[key], f"claim {cid!r}.{key}", issues)
                    if declared is not None and not declared:
                        issues.append(f"claim {cid!r}.{key} must not be empty")
            if "downgrade_if_missing_baseline" in item:
                downgrade = item["downgrade_if_missing_baseline"]
                if isinstance(downgrade, str):
                    targets = {downgrade}
                elif isinstance(downgrade, list):
                    targets = _string_list(downgrade, f"claim {cid!r}.downgrade_if_missing_baseline", issues)
                else:
                    targets = None
                    issues.append(
                        f"claim {cid!r}.downgrade_if_missing_baseline must be a non-empty string or string list"
                    )
                if targets is not None and (not targets or not targets <= EXPECTED_DOWNGRADE_TARGETS):
                    issues.append(
                        f"claim {cid!r}.downgrade_if_missing_baseline must name a declared downgrade target"
                    )
            if "minimum_paired_subjects" in item:
                value = _strict_int(item["minimum_paired_subjects"])
                if value is None or value < 1:
                    issues.append(f"claim {cid!r}.minimum_paired_subjects must be a positive integer")
            if "scientific_pass" in item and item.get("scientific_pass") is not False:
                issues.append(f"claim {cid} scientific_pass must be false")
            if "formal_bayes_factor" in item and item.get("formal_bayes_factor") is not None:
                issues.append(f"claim {cid} formal_bayes_factor must be null")
            if "k_value" in item and item.get("k_value") is not None:
                issues.append(f"claim {cid} k_value must be null")
            if cid == "NO-SCIENTIFIC-PASS":
                if "scientific_pass" not in item or item.get("scientific_pass") is not False:
                    issues.append("claim NO-SCIENTIFIC-PASS must set scientific_pass false")
                if "formal_bayes_factor" not in item or item.get("formal_bayes_factor") is not None:
                    issues.append("claim NO-SCIENTIFIC-PASS must set formal_bayes_factor null")
        if len(claim_ids) != len(set(claim_ids)):
            issues.append("claim IDs must be unique")
        claims = set(claim_ids)
    missing_claims = REQUIRED_CLAIMS - claims
    unknown_claims = claims - REQUIRED_CLAIMS
    if missing_claims:
        issues.append(f"missing claims: {', '.join(sorted(missing_claims))}")
    if unknown_claims:
        issues.append(f"unsupported claim IDs: {', '.join(sorted(unknown_claims))}")

    nulls = _string_list(doc.get("null_models_required"), "null_models_required", issues)
    if nulls is None or not REQUIRED_NULLS.issubset(nulls):
        issues.append("missing null")
    min_null_reps = _strict_int(doc.get("minimum_null_replicates"))
    if min_null_reps is None or min_null_reps < 100:
        issues.append("minimum_null_replicates must be an integer >= 100")

    splits = _string_list(doc.get("splits_required"), "splits_required", issues)
    if splits is None or not REQUIRED_SPLITS.issubset(splits):
        issues.append("missing split")

    pos = _string_list(doc.get("positive_controls"), "positive_controls", issues)
    neg = _string_list(doc.get("negative_controls"), "negative_controls", issues)
    conf = _string_list(doc.get("confound_controls"), "confound_controls", issues)
    if pos is None or not REQUIRED_POSITIVE_CONTROLS.issubset(pos):
        issues.append("missing positive_controls")
    if neg is None or not REQUIRED_NEGATIVE_CONTROLS.issubset(neg):
        issues.append("missing negative_controls")
    if conf is None or not REQUIRED_CONFOUND_CONTROLS.issubset(conf):
        issues.append("missing confound_controls")

    gates = doc.get("gates")
    gate_keys = {
        "scientific_pass_allowed",
        "formal_k_allowed",
        "synthetic_to_empirical",
        "unknown_n_tests_is_one",
        "missing_subject_zero_fill",
        "prediction_as_causation",
        "eeg_only_discernment",
        "respiration_as_equanimity",
        "beta1_as_spatial_charge",
    }
    if _exact_keys(gates, "gates", gate_keys, issues):
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
    sample_keys = {
        "minimum_paired_subjects",
        "minimum_held_out_subjects",
        "minimum_sessions_per_split",
        "below_minimum_outcome",
        "missing_subjects_policy",
        "failed_subjects_policy",
        "proposed_thresholds_power_validated",
    }
    if _exact_keys(sample, "sample_requirements", sample_keys, issues):
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
    replication_keys = {"required", "independent_cohort_or_site", "failure_outcome"}
    if _exact_keys(replication, "replication", replication_keys, issues):
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
    states = _string_list(states_raw, "campaign_execution_states", issues)
    if states != EXPECTED_CAMPAIGN_STATES:
        issues.append("invalid campaign_execution_states")
    terminals = _string_list(term_raw, "terminal_states", issues)
    if terminals != EXPECTED_TERMINAL_STATES:
        issues.append("invalid terminal_states")
    if _exact_keys(transitions, "valid_state_transitions", EXPECTED_CAMPAIGN_STATES, issues):
        for state, expected_targets in EXPECTED_TRANSITIONS.items():
            raw_targets = transitions.get(state)
            targets = _string_list(raw_targets, f"valid_state_transitions.{state}", issues)
            if targets is None:
                continue
            if targets != expected_targets:
                issues.append(f"invalid transition set for {state}")
            if not targets.issubset(EXPECTED_CAMPAIGN_STATES):
                issues.append(f"non-protocol transition target from {state}")
        for term in EXPECTED_TERMINAL_STATES:
            if transitions.get(term) != []:
                issues.append(f"terminal state {term} must have empty transitions")
    if not isinstance(resumability, dict):
        issues.append("missing resumability_policy")
    else:
        resumability_keys = {
            "allowed",
            "require_exact_hash_match",
            "require_checkpoint_manifest",
            "recompute_interrupted_units_only",
            "prohibit_terminal_state_reopening",
            "prohibit_non_protocol_state",
        }
        _exact_keys(resumability, "resumability_policy", resumability_keys, issues)
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

    phrases_list = _string_list(doc.get("forbidden_phrases"), "forbidden_phrases", issues)
    for token in (
        "consciousness",
        "equanimity",
        "quantum",
        "topological charge",
        "bayes",
        "scientific pass",
    ):
        marker_pattern = rf"\b{re.escape(token)}\b"
        if phrases_list is None or not any(
            any(match.group(0).isascii() for match in re.finditer(marker_pattern, phrase, flags=re.IGNORECASE))
            for phrase in phrases_list
        ):
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
    assert report["complete"] is True, report["issues"]
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
        "formal_bayes_factor",
        "k_value",
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
        lambda d: d["valid_state_transitions"].__setitem__("EXECUTING", ["NOT_A_STATE", "PASS"]),
        lambda d: d["valid_state_transitions"].__setitem__("PLANNING", ["COMPLETED"]),
        lambda d: d["resumability_policy"].__setitem__("prohibit_terminal_state_reopening", False),
        lambda d: d["claims"].append("not-a-dict"),
    ):
        doc = load_matrix()
        mutator(doc)
        report = evaluate(doc)
        assert report["complete"] is False
        assert report["scientific_pass"] is False
        assert report["formal_bayes_factor"] is None


def test_transition_graph_and_required_null_keys_reject_false_success() -> None:
    """Regression: invalid edges / omitted formal-K keys must not yield complete=True."""
    # Invalid non-protocol destination previously passed complete=True.
    doc = load_matrix()
    doc["valid_state_transitions"]["EXECUTING"] = ["NOT_A_STATE", "PASS"]
    report = evaluate(doc)
    assert report["complete"] is False
    assert report["scientific_pass"] is False
    assert report["formal_bayes_factor"] is None
    assert report["k_value"] is None

    # Skipping REGISTERED/EXECUTING into COMPLETED previously passed complete=True.
    doc = load_matrix()
    doc["valid_state_transitions"]["PLANNING"] = ["COMPLETED"]
    report = evaluate(doc)
    assert report["complete"] is False
    assert report["scientific_pass"] is False

    # Omitting top-level formal_bayes_factor / k_value previously passed complete=True.
    doc = load_matrix()
    doc.pop("formal_bayes_factor", None)
    doc.pop("k_value", None)
    report = evaluate(doc)
    assert report["complete"] is False
    assert report["scientific_pass"] is False
    assert report["formal_bayes_factor"] is None
    assert report["k_value"] is None

    # NO-SCIENTIFIC-PASS must keep explicit scientific_pass=false and formal_bayes_factor=null.
    doc = load_matrix()
    for item in doc["claims"]:
        if item.get("claim_id") == "NO-SCIENTIFIC-PASS":
            item.pop("scientific_pass", None)
            item.pop("formal_bayes_factor", None)
    report = evaluate(doc)
    assert report["complete"] is False
    assert report["scientific_pass"] is False


def test_duplicate_state_and_transition_entries_fail_closed() -> None:
    """Set-equivalent duplicates are malformed protocol declarations, not valid lists."""
    cases = (
        lambda d: d["campaign_execution_states"].append("PLANNING"),
        lambda d: d["terminal_states"].append("COMPLETED"),
        lambda d: d["valid_state_transitions"]["PLANNING"].append("REGISTERED"),
    )
    for mutate in cases:
        doc = load_matrix()
        mutate(doc)
        assert evaluate(doc)["complete"] is False


def test_duplicate_protocol_lists_and_claim_ids_fail_closed() -> None:
    cases = (
        lambda d: d["null_models_required"].append("flat"),
        lambda d: d["splits_required"].append("forward_time"),
        lambda d: d["positive_controls"].append("known_synthetic_power_change"),
        lambda d: d["forbidden_outcomes"].append("PASS"),
        lambda d: d["claims"].append(dict(d["claims"][0])),
    )
    for mutate in cases:
        doc = load_matrix()
        mutate(doc)
        assert evaluate(doc)["complete"] is False


def test_unrecognized_claim_id_is_not_admitted_by_versioned_matrix() -> None:
    doc = load_matrix()
    doc["claims"].append(
        {
            "claim_id": "UNRECOGNIZED",
            "text": "unsupported claim",
            "category": "protocol",
            "evidence_class": "preregistered_protocol",
            "falsification": "unsupported",
            "blocked_if_missing_baseline": True,
        }
    )
    assert evaluate(doc)["complete"] is False


def test_unhashable_malformed_list_entries_return_incomplete_not_exceptions() -> None:
    cases = (
        ("campaign_execution_states", {}),
        ("terminal_states", []),
        ("null_models_required", {}),
        ("splits_required", []),
        ("positive_controls", {}),
        ("forbidden_outcomes", {}),
    )
    for key, malformed in cases:
        doc = load_matrix()
        doc[key].append(malformed)
        report = evaluate(doc)
        assert report["complete"] is False
        assert report["scientific_pass"] is False


def test_unknown_outcomes_and_extra_status_keys_fail_closed() -> None:
    # A versioned matrix must not silently accept unsupported science/status fields.
    for key, value in (
        ("scientific_status", "VALIDATED"),
        ("outcome", "PASS"),
        ("execution_state", "COMPLETED"),
    ):
        doc = load_matrix()
        doc[key] = value
        assert evaluate(doc)["complete"] is False

    doc = load_matrix()
    doc["allowed_outcomes"] = ["VALIDATED"]
    assert evaluate(doc)["complete"] is False


def test_claim_rows_require_core_fields_and_reject_extra_status_fields() -> None:
    doc = load_matrix()
    del doc["claims"][0]["text"]
    assert evaluate(doc)["complete"] is False

    doc = load_matrix()
    doc["claims"][0]["status"] = "PASS"
    report = evaluate(doc)
    assert report["complete"] is False
    assert report["scientific_pass"] is False


def test_claim_text_must_not_be_empty_or_whitespace() -> None:
    for text in ("", " \t\n"):
        doc = load_matrix()
        doc["claims"][0]["text"] = text
        report = evaluate(doc)
        assert report["complete"] is False
        assert report["scientific_pass"] is False


def test_downgrade_policy_accepts_declared_scalar_vocabulary() -> None:
    doc = load_matrix()
    policies = [
        item["downgrade_if_missing_baseline"]
        for item in doc["claims"]
        if "downgrade_if_missing_baseline" in item
    ]
    assert all(isinstance(policy, str) for policy in policies)
    assert set(policies) == {"proxy_inference", "unsupported_claim"}
    report = evaluate(doc)
    assert report["complete"] is True, report["issues"]


def test_explicit_nulls_and_invalid_nested_types_fail_closed() -> None:
    cases = (
        lambda d: d.__setitem__("status", None),
        lambda d: d.__setitem__("evidence_class", None),
        lambda d: d["protocol_limits"].__setitem__("note", None),
        lambda d: d["valid_state_transitions"].__setitem__("PLANNING", "REGISTERED"),
        lambda d: d["claims"][0].__setitem__("text", None),
        lambda d: d["claims"][0].__setitem__("required_baselines", ["pairwise", None]),
    )
    for mutate in cases:
        doc = load_matrix()
        mutate(doc)
        report = evaluate(doc)
        assert report["complete"] is False
        assert report["scientific_pass"] is False


def test_incomplete_or_failed_execution_status_cannot_be_smuggled_into_matrix() -> None:
    for key, value in (
        ("status", "FAILED"),
        ("status", "VALIDATED"),
        ("run_status", "INCOMPLETE"),
        ("execution_state", "ABORTED"),
    ):
        doc = load_matrix()
        doc[key] = value
        assert evaluate(doc)["complete"] is False


def test_required_disclaimer_families_cannot_be_removed_from_declaration() -> None:
    doc = load_matrix()
    doc["forbidden_phrases"] = [
        phrase for phrase in doc["forbidden_phrases"] if "scientific pass" not in phrase.lower()
    ]
    report = evaluate(doc)
    assert report["complete"] is False
    assert report["scientific_pass"] is False


def test_required_disclaimer_families_reject_substring_lookalikes() -> None:
    """A word embedded in an unrelated token is not a disclaimer marker."""
    cases = (
        ("consciousness", "unconsciousness"),
        ("equanimity", "inequanimity"),
        ("quantum", "quantumization"),
        ("topological charge", "topological charger"),
        ("bayes", "bayesian"),
        ("scientific pass", "scientific passport"),
    )
    for marker, lookalike in cases:
        doc = load_matrix()
        doc["forbidden_phrases"] = [
            phrase for phrase in doc["forbidden_phrases"] if marker not in phrase.lower()
        ]
        doc["forbidden_phrases"].append(lookalike)

        report = evaluate(doc)
        assert report["complete"] is False, marker
        assert any(f"missing forbidden phrase family: {marker}" in issue for issue in report["issues"])


def test_duplicate_yaml_mapping_keys_are_rejected(tmp_path: Path) -> None:
    source = MATRIX.read_text(encoding="utf-8")
    duplicate = tmp_path / "duplicate-matrix.yaml"
    duplicate.write_text(source + "\nmatrix_id: shadowed-id\n", encoding="utf-8")
    try:
        load_matrix(duplicate)
    except ValueError as exc:
        assert "duplicate" in str(exc).lower()
    else:
        raise AssertionError("duplicate YAML keys must not be silently overwritten")


def test_required_disclaimers_remain_in_adversarial_review_document() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    for phrase in (
        "does not validate the theory",
        "not an empirical result",
        "completeness never implies scientific success",
        "proposed thresholds are not power validation",
        "does not validate actual execution histories",
    ):
        assert phrase in text


def test_adversarial_review_does_not_label_a_pinned_sha_as_current_main() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert re.search(r"\bcurrent main\s+`?[0-9a-f]{40}", text, re.IGNORECASE) is None


def test_complete_matrix_never_implies_scientific_success() -> None:
    doc = load_matrix()
    report = evaluate(doc)
    assert report["complete"] is True, report["issues"]
    assert report["scientific_pass"] is False
    assert report["formal_bayes_factor"] is None
    assert report.get("k_value") is None
    assert report.get("empirical_claim_allowed", False) is False
    assert report.get("proposed_thresholds_are_power_validation", False) is False
    assert doc.get("status") == "FALSIFICATION_HARNESS_ONLY"
    assert doc.get("evidence_class") == "preregistered_protocol"


def test_downgrade_targets_must_come_from_declared_vocabulary() -> None:
    """A downgrade target is a declared scalar, never a PASS-like or formal-K label."""
    for target in ("scientific_PASS", "promote_to_pass", "PASS", "FORMAL_BAYES_FACTOR"):
        doc = load_matrix()
        doc["claims"][1]["downgrade_if_missing_baseline"] = target
        report = evaluate(doc)
        assert report["complete"] is False, target
        assert report["scientific_pass"] is False
    doc = load_matrix()
    doc["claims"][1]["downgrade_if_missing_baseline"] = ["FORMAL_BAYES_FACTOR"]
    assert evaluate(doc)["complete"] is False
    doc = load_matrix()
    doc["claims"][1]["downgrade_if_missing_baseline"] = []
    assert evaluate(doc)["complete"] is False


def test_claim_evidence_class_must_come_from_declared_vocabulary() -> None:
    """Claim evidence classes are the versioned vocabulary, not any free string."""
    for value in ("empirical_validated", "PASS", "formal"):
        doc = load_matrix()
        doc["claims"][0]["evidence_class"] = value
        report = evaluate(doc)
        assert report["complete"] is False, value
        assert report["scientific_pass"] is False


def test_claim_category_must_come_from_declared_vocabulary() -> None:
    """Claim categories are the versioned vocabulary, not any free string."""
    for value in ("scientific_PASS", "empirical_validated", "PASS", "formal"):
        doc = load_matrix()
        doc["claims"][0]["category"] = value
        report = evaluate(doc)
        assert report["complete"] is False, value
        assert report["scientific_pass"] is False
        assert any("category is not in the versioned claim vocabulary" in issue for issue in report["issues"])


def test_explicit_empty_claim_requirement_lists_fail_closed() -> None:
    """An explicitly empty baseline, control or instrument list declares nothing and must fail."""
    for key in ("required_baselines", "required_controls", "required_instruments"):
        doc = load_matrix()
        claim = next(item for item in doc["claims"] if key in item)
        claim[key] = []
        report = evaluate(doc)
        assert report["complete"] is False, key
        assert report["scientific_pass"] is False


def test_family_marker_must_use_ascii_spelling() -> None:
    """A long-s look-alike spelling of a disclaimer family is not that family marker."""
    doc = load_matrix()
    doc["forbidden_phrases"] = [p for p in doc["forbidden_phrases"] if "consciousness" not in p.lower()]
    doc["forbidden_phrases"].append("conſciouſnesſ claim")
    report = evaluate(doc)
    assert report["complete"] is False
    assert "missing forbidden phrase family: consciousness" in report["issues"]


def test_family_split_across_entries_fails_closed() -> None:
    """A family must appear whole within one entry; split words across entries do not satisfy it."""
    doc = load_matrix()
    doc["forbidden_phrases"] = [p for p in doc["forbidden_phrases"] if "scientific pass" not in p.lower()]
    doc["forbidden_phrases"].extend(["scientific", "pass"])
    report = evaluate(doc)
    assert report["complete"] is False
    assert "missing forbidden phrase family: scientific pass" in report["issues"]
