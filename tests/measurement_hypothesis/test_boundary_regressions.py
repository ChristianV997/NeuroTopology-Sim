"""Regression tests for boundary gaps found in review of the five-level contract.

Each test names one bypass. Inputs are fixtures or in-memory text; no participant data is read.
"""
from __future__ import annotations

import hashlib
from datetime import date

import pytest

from shared.measurement_hypothesis import validate_mapping
from shared.measurement_hypothesis.language import scan_interpretation, target_construct_hits
from shared.measurement_hypothesis.validate import load_mapping

AS_OF = date(2026, 10, 16)
TARGET_SENTENCE = "The descriptor is a cortical wave."


def _codes(report):
    return {error["code"] for error in report["errors"]}


def _set(root, path, value):
    node = root
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value


# ── F1: target-construct equation in every free-text field ───────────────────

@pytest.mark.parametrize("path", [
    ("measurement", "definition"),
    ("interpretation", "alternative_explanations", 0),
    ("interpretation", "confounds", 0),
    ("interpretation", "falsifiers", 0, "discriminates"),
    ("interpretation", "falsifiers", 0, "test"),
    ("operator", "name"),
    ("construct_validity", "basis"),
    ("empirical_claim", "required_data"),
])
def test_target_equation_is_rejected_in_every_free_text_field(valid_mapping, check, path):
    _set(valid_mapping, path, TARGET_SENTENCE)
    assert "EQUIVALENCE_TO_TARGET_CONSTRUCT" in _codes(check(valid_mapping))


def test_affirmative_empirical_statement_naming_the_target_is_rejected(valid_mapping, check):
    valid_mapping["empirical_claim"]["statement"] = "The channel-index phase gradient is a cortical wave."
    assert "EQUIVALENCE_TO_TARGET_CONSTRUCT" in _codes(check(valid_mapping))


def test_question_form_empirical_statement_naming_the_target_is_admitted(valid_mapping, check):
    valid_mapping["empirical_claim"]["statement"] = "Is the channel-index phase gradient a cortical wave?"
    assert check(valid_mapping)["contract_status"] == "VALID_HYPOTHESIS_MAPPING"


# ── F2: spelling and synonym variants of a target construct ──────────────────

@pytest.mark.parametrize("variant", [
    "cortical-wave",
    "cortical_wave",
    "cortical​wave",
    "ｃｏｒｔｉｃａｌ ｗａｖｅ",
    "сortical wave",
    "source localisation",
    "travelling wave",
    "biologically valid",
])
def test_target_construct_variants_are_detected(variant):
    assert target_construct_hits(f"The descriptor is a {variant} measure.")


def test_variant_in_the_proposed_interpretation_is_rejected(valid_mapping, check):
    valid_mapping["interpretation"]["proposed_interpretation"] = "The descriptor is a cortical-wave measure."
    assert "EQUIVALENCE_TO_TARGET_CONSTRUCT" in _codes(check(valid_mapping))


# ── F3: negation exemption must be a whole-word negation directly before the match ──

@pytest.mark.parametrize("text", [
    "The descriptor is not not a cortical wave measure.",
    "The descriptor is a piano cortical wave measure.",
])
def test_double_negation_and_embedded_negation_text_are_not_exempt(text):
    assert target_construct_hits(text)


def test_single_negation_stays_admissible():
    assert target_construct_hits("The descriptor is not a cortical wave measure.") == []


# ── F4: support and causal wording beyond the closed lists ───────────────────

@pytest.mark.parametrize("text", [
    "The gradient supports phase circulation.",
    "The gradient gives rise to phase circulation.",
    "The gradient explains phase circulation.",
])
def test_support_and_causal_wording_beyond_the_closed_lists_is_flagged(text):
    hits = scan_interpretation(text)
    assert hits["empirical_support"] or hits["causal_or_mechanism"]


def test_support_wording_in_the_proposal_is_rejected(valid_mapping, check):
    valid_mapping["interpretation"]["proposed_interpretation"] = "The gradient supports phase circulation."
    assert "EMPIRICAL_SUPPORT_IMPLIED" in _codes(check(valid_mapping))


def test_past_tense_result_in_the_empirical_statement_is_rejected(valid_mapping, check):
    valid_mapping["empirical_claim"]["statement"] = (
        "The channel-index phase gradient was validated across 40 recordings.")
    assert "EMPIRICAL_SUPPORT_IMPLIED" in _codes(check(valid_mapping))


# ── F5: duplicate JSON keys must not be silently last-wins ───────────────────

def test_duplicate_keys_in_a_mapping_file_are_rejected(tmp_path):
    path = tmp_path / "mapping.json"
    path.write_text('{"construct_validity": {"status": "VALIDATED"}, '
                    '"construct_validity": {"status": "NOT_ESTABLISHED"}}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_mapping(path)


# ── F6: a key counts only when a function returns it ─────────────────────────

def _module_repo(tmp_path, body: str):
    module = tmp_path / "validation" / "analytic_phase.py"
    module.parent.mkdir(parents=True)
    module.write_text(body, encoding="utf-8")
    return hashlib.sha256(module.read_bytes()).hexdigest()


def test_key_named_only_in_a_docstring_or_bare_string_does_not_resolve(valid_mapping, tmp_path):
    digest = _module_repo(tmp_path,
        'def channel_phase_gradient_metrics(x):\n'
        '    """Computes phase_grad and analytic_phase_proxy."""\n'
        '    "analytic_phase_proxy"\n'
        '    return {"other_key": 1.0}\n')
    valid_mapping["operational"]["implementation"]["sha256"] = digest
    report = validate_mapping(valid_mapping, repo_root=tmp_path, as_of=AS_OF)
    assert {"OUTPUT_KEY_UNRESOLVED", "METRIC_KIND_UNRESOLVED"} <= _codes(report)
    assert report["computable"] is False


def test_keys_returned_by_the_function_resolve(valid_mapping, tmp_path):
    digest = _module_repo(tmp_path,
        'def channel_phase_gradient_metrics(x):\n'
        '    return {"phase_grad": 1.0, "metric_kind": "analytic_phase_proxy"}\n')
    valid_mapping["operational"]["implementation"]["sha256"] = digest
    report = validate_mapping(valid_mapping, repo_root=tmp_path, as_of=AS_OF)
    assert not {"OUTPUT_KEY_UNRESOLVED", "METRIC_KIND_UNRESOLVED"} & _codes(report)


# ── F7: a NUL byte in the module path is reported, not raised ────────────────

def test_nul_byte_in_module_path_is_reported_not_raised(valid_mapping, check):
    valid_mapping["operational"]["implementation"]["module"] = "validation/analytic_phase.py\x00"
    assert "IMPLEMENTATION_UNRESOLVED" in _codes(check(valid_mapping))


# ── F8: theory terms are found after compatibility folding and in every prose field ──

@pytest.mark.parametrize("section,key,value", [
    ("measurement", "definition", "A ｕｔｔｌ reading of the channel phase gradient."),
    ("operational", "family_note", "No family; this is the TTFCD phase term."),
    ("measurement", "observables", ["ttfcd phase-gradient readout, alpha band"]),
])
def test_theory_term_is_detected_in_operational_prose(valid_mapping, check, section, key, value):
    valid_mapping[section][key] = value
    assert "THEORY_TERM_IN_OPERATIONAL_IDENTIFIER" in _codes(check(valid_mapping))


# ── F9: every report states the empirical and access status it assigns ───────

def test_every_report_states_the_empirical_and_access_status(valid_mapping, check):
    report = check(valid_mapping)
    assert report["empirical_claim_status"] == "NOT_RUN"
    assert report["data_access_status"] == "NOT_AUTHORIZED"


def test_overstated_empirical_status_is_rejected_and_the_report_keeps_not_run(valid_mapping, check):
    valid_mapping["empirical_claim"]["status"] = "PASS"
    report = check(valid_mapping)
    assert "EMPIRICAL_STATUS_OVERSTATED" in _codes(report)
    assert report["empirical_claim_status"] == "NOT_RUN"
    assert report["evidence_ready"] is False
