"""Tests for tools/revalidate_dataset_reports.py's conclusion-generation logic.

The Phase 5 re-validation run against real ds003969 data caught a real bug in
an earlier draft of this script: `revalidate_ds003969` hardcoded a "CONFIRMED
(null result reproduced)" conclusion regardless of the actual computed
p-values, and the real run found q_net's mixedlm p=0.023 (significant) against
an original p=0.354 (non-significant) -- a genuine disagreement the hardcoded
text was masking. `_build_reconciliation_conclusion` was written to fix this
by deriving the conclusion from `results` instead; these tests are the
regression test for that fix, using synthetic results dicts so they run
without needing the real streamed CSVs.
"""
from __future__ import annotations

from tools.revalidate_dataset_reports import (
    _build_reconciliation_conclusion,
    _orig_p_was_significant,
)


def test_orig_p_was_significant_parses_bare_float():
    assert _orig_p_was_significant("0.021") is True
    assert _orig_p_was_significant("0.354") is False


def test_orig_p_was_significant_parses_trailing_annotation():
    assert _orig_p_was_significant("0.130 (trend)") is False


def _result(metric, orig_p_str, new_p, converged=True, boundary_warning=False):
    return {
        "metric": metric, "orig_p_str": orig_p_str, "new_p": new_p,
        "converged": converged, "boundary_warning": boundary_warning,
    }


def test_all_agree_reports_confirmed_not_partial():
    results = [
        _result("q_net", "0.354", 0.40),
        _result("q_abs", "0.936", 0.80),
    ]
    text = _build_reconciliation_conclusion(results)
    assert "CONFIRMED" in text
    assert "PARTIAL" not in text
    assert "q_net" in text and "q_abs" in text


def test_one_disagreement_reports_partial_not_confirmed():
    """This is the exact regression case: original null (p=0.354) but the new
    mixedlm result crosses the significance threshold (p=0.023) -- the
    conclusion must say PARTIAL, not silently claim CONFIRMED."""
    results = [
        _result("q_net", "0.354", 0.023),  # disagreement: orig non-sig, new sig
        _result("q_abs", "0.936", 0.842),  # agreement: both non-sig
        _result("f_dress", "0.500", 0.085),  # agreement: both non-sig
        _result("defect_density", "0.838", 0.749),  # agreement: both non-sig
    ]
    text = _build_reconciliation_conclusion(results)
    assert "PARTIAL" in text
    assert "CONFIRMED" not in text
    assert "1/4" in text
    assert "disagree on significance at α=0.05:** q_net" in text


def test_boundary_warning_surfaced_when_present():
    results = [_result("q_net", "0.021", 0.035, boundary_warning=True)]
    text = _build_reconciliation_conclusion(results)
    assert "Caution" in text
    assert "boundary" in text.lower()


def test_no_boundary_warning_section_when_none_present():
    results = [_result("q_net", "0.021", 0.035, boundary_warning=False)]
    text = _build_reconciliation_conclusion(results)
    assert "Caution" not in text
