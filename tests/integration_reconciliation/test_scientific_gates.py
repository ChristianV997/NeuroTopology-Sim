from __future__ import annotations

from tools.integration_reconciliation import scientific_gates


def test_empty_text_has_no_hints():
    hints = scientific_gates.evaluate_text("")
    assert hints.scientific_review_required is False


def test_synthetic_and_pass_without_safeguard_is_flagged():
    hints = scientific_gates.evaluate_text("Ran on a synthetic fixture; verdict was PASS.")
    assert hints.synthetic_pass_claim_risk is True
    assert hints.scientific_review_required is True


def test_synthetic_and_pass_with_safeguard_is_not_flagged():
    text = "Ran on a synthetic demo; PASS is reserved for empirical data and synthetic runs cannot produce PASS."
    hints = scientific_gates.evaluate_text(text)
    assert hints.synthetic_pass_claim_risk is False


def test_pr219_style_text_does_not_trip_the_bayes_factor_hint():
    """Regression: PR #219's real description explicitly distinguishes
    proxies from formal Bayes factors -- good hygiene, must not be
    flagged."""
    text = (
        "distinguish RSS/AICc/BIC evidence proxies from formal "
        "marginal-likelihood Bayes factors; enforce K > 100 plus explicit "
        "empirical provenance, effective sample size, controls, and "
        "multiplicity gates; make synthetic/null/degenerate inputs unable "
        "to produce PASS"
    )
    hints = scientific_gates.evaluate_text(text)
    assert hints.unqualified_bayes_factor_claim is False
    assert hints.synthetic_pass_claim_risk is False


def test_unqualified_bayes_factor_is_flagged():
    hints = scientific_gates.evaluate_text("The Bayes factor for this comparison was 150.")
    assert hints.unqualified_bayes_factor_claim is True


def test_empirical_without_provenance_terms_is_flagged():
    hints = scientific_gates.evaluate_text("This run used real EEG data and found an effect.")
    assert hints.empirical_claim_missing_provenance_terms is True


def test_empirical_with_provenance_terms_is_not_flagged():
    text = "This run used real EEG data; provenance is recorded via source_kind and a sha256 checksum."
    hints = scientific_gates.evaluate_text(text)
    assert hints.empirical_claim_missing_provenance_terms is False


def test_significance_without_control_terms_is_flagged():
    hints = scientific_gates.evaluate_text("The result was significant across all subjects.")
    assert hints.significance_claim_missing_control_terms is True


def test_significance_with_control_terms_is_not_flagged():
    hints = scientific_gates.evaluate_text("The result was significant against a null control baseline.")
    assert hints.significance_claim_missing_control_terms is False


def test_strong_claim_without_qualifier_is_flagged():
    hints = scientific_gates.evaluate_text("This demonstrates the topological model is correct.")
    assert hints.strong_claim_missing_qualifier is True


def test_strong_claim_with_qualifier_is_not_flagged():
    hints = scientific_gates.evaluate_text("This demonstrates a descriptive only effect; NOT_SUPPORTED as proof.")
    assert hints.strong_claim_missing_qualifier is False


def test_touches_scientific_paths_true_for_bayesian_falsification():
    assert scientific_gates.touches_scientific_paths(("sim/pitnn/bayesian_falsification.py",)) is True


def test_touches_scientific_paths_false_for_docs_only():
    assert scientific_gates.touches_scientific_paths(("docs/README.md",)) is False


def test_touches_scientific_paths_none_input_is_false():
    assert scientific_gates.touches_scientific_paths(None) is False


def test_to_dict_includes_scientific_review_required():
    hints = scientific_gates.evaluate_text("The Bayes factor was 5.")
    payload = hints.to_dict()
    assert payload["scientific_review_required"] is True
    assert "reasons" in payload
