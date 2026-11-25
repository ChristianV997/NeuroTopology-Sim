"""Unit tests for centralized non-parametric testing and falsification gates."""
from __future__ import annotations

import numpy as np
import pytest

from analysis.non_parametric import wilcoxon_paired_test
from validation.falsification_gates import evaluate_falsification_gate


class TestWilcoxonPairedTest:
    def test_valid_paired_differences(self):
        """Standard non-degenerate paired data must yield valid Wilcoxon results."""
        a = [1.2, 2.5, 3.1, 4.0, 5.2, 6.1]
        b = [0.8, 1.9, 2.7, 3.2, 4.5, 5.0]

        res = wilcoxon_paired_test(a, b)
        assert res["valid"] is True
        assert res["p_value"] is not None
        assert res["statistic"] is not None
        assert res["n_pairs"] == 6

    def test_degenerate_guards(self):
        """Degenerate cases (N < 2, all identical, NaN) must fail closed safely."""
        # 1. Single pair (N < 2)
        r_single = wilcoxon_paired_test([1.0], [2.0])
        assert r_single["valid"] is False
        assert r_single["status"] == "insufficient_paired_subjects"

        # 2. Identical pairs (all differences zero)
        r_zero = wilcoxon_paired_test([3.0, 4.0, 5.0], [3.0, 4.0, 5.0])
        assert r_zero["valid"] is False
        assert r_zero["status"] == "zero_variance_differences"

        # 3. Non-finite values
        r_nan = wilcoxon_paired_test([1.0, np.nan], [2.0, 3.0])
        assert r_nan["valid"] is False
        assert r_nan["status"] == "non_finite_values_detected"


class TestFalsificationGates:
    def test_bayesian_falsification_evaluation(self):
        """Bayesian falsification gates must correctly classify evidence without proof claims."""
        # Decisive evidence
        gate_decisive = evaluate_falsification_gate(bayes_factor=150.0, threshold_k=100.0)
        assert gate_decisive["verdict"] == "DECISIVE_SUPPORT"
        assert gate_decisive["guardrails"]["no_clinical_claims"] is True

        # Null-favored / not supported
        gate_null = evaluate_falsification_gate(bayes_factor=0.8, threshold_k=100.0)
        assert gate_null["verdict"] == "NOT_SUPPORTED"
        assert gate_null["falsification_status"] == "NULL_FAVORED"

        # Decisive falsification
        gate_falsified = evaluate_falsification_gate(bayes_factor=0.005, threshold_k=100.0)
        assert gate_falsified["verdict"] == "DECISIVE_FALSIFICATION"
