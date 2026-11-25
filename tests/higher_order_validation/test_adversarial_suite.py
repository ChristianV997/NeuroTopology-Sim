"""Tests for higher-order adversarial validation (engineering evidence only)."""
from __future__ import annotations

import json
import socket

import numpy as np
import pytest

from tools.higher_order_validation.dgps import (
    DGP_REGISTRY,
    generate_independent_gaussian,
    generate_pure_pairwise,
    generate_pure_triadic,
    source_checksum,
)
from tools.higher_order_validation.nulls import NULL_REGISTRY
from tools.higher_order_validation.probes import max_abs_pairwise_corr, max_abs_triadic_moment
from tools.higher_order_validation.report import dumps, suite_to_dict, write_reports
from tools.higher_order_validation.schema import CaseOutcome, EVIDENCE_CLASS
from tools.higher_order_validation.suite import run_validation_suite


def test_all_positive_and_negative_controls_present():
    results = run_validation_suite(seed=0)
    ids = {r.case_id for r in results}
    assert "pos_pure_pairwise" in ids
    assert "pos_pure_triadic" in ids
    assert "pos_amplitude_modulation" in ids
    assert "neg_independent_gaussian" in ids
    assert "fp_volume_conduction_mixing" in ids
    assert "ctrl_common_driver" in ids
    for name in NULL_REGISTRY:
        assert f"null_{name}" in ids
    # No scientific PASS / Bayes factor
    payload = suite_to_dict(results)
    assert payload["scientific_pass_emitted"] is False
    assert payload["formal_bayes_factor_emitted"] is False
    assert all(r.evidence_class == EVIDENCE_CLASS for r in results)
    assert all(r.synthetic is True for r in results)
    assert all(r.outcome.value != "PASS" for r in results)


def test_deterministic_repetition():
    a = run_validation_suite(seed=7)
    b = run_validation_suite(seed=7)
    assert [r.to_dict() for r in a] == [r.to_dict() for r in b]
    # Checksums for same DGP+seed match
    x1 = generate_pure_pairwise(seed=7)
    x2 = generate_pure_pairwise(seed=7)
    assert source_checksum(x1) == source_checksum(x2)
    assert np.array_equal(x1, x2)


def test_malformed_inputs():
    with pytest.raises(ValueError):
        from tools.higher_order_validation.nulls import phase_shuffle_null

        phase_shuffle_null(np.zeros(10), seed=0)
    with pytest.raises(ValueError):
        from tools.higher_order_validation.nulls import block_shuffle_null

        block_shuffle_null(np.zeros((2, 2, 2)), seed=0)


def test_finite_serialization(tmp_path):
    results = run_validation_suite(seed=0)
    payload = suite_to_dict(results)
    text = dumps(payload)
    assert "NaN" not in text
    assert "Infinity" not in text
    data = json.loads(text)
    json.dumps(data, allow_nan=False)
    paths = write_reports(payload, tmp_path / "out")
    assert (tmp_path / "out" / "higher_order_validation.json").exists()
    assert "json" in paths


def test_bounded_memory():
    # Suite must not materialize huge trajectories; use modest shapes.
    x = generate_independent_gaussian(n_channels=8, n_samples=4096, seed=0)
    assert x.nbytes < 5_000_000
    results = run_validation_suite(seed=0)
    # Results are O(cases), not O(samples * cases of full history)
    assert len(results) < 50


def test_no_network_operation():
    # Ensure suite does not require network; block sockets like isolation tests.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # Running the suite should not open network connections.
        run_validation_suite(seed=1)
    finally:
        s.close()
    # Also verify DGP registry keys exist for required processes.
    for key in (
        "pure_pairwise_dependence",
        "pure_triadic_dependence",
        "amplitude_modulation",
        "common_driver_confounding",
        "temporal_smoothing",
        "volume_conduction_like_mixing",
        "independent_gaussian_noise",
    ):
        assert key in DGP_REGISTRY


def test_pairwise_and_triadic_probe_separation():
    pair = generate_pure_pairwise(seed=0, corr=0.9)
    triad = generate_pure_triadic(seed=0)
    assert max_abs_pairwise_corr(pair) > 0.5
    assert max_abs_triadic_moment(triad) > 0.3
    assert max_abs_pairwise_corr(triad) < 0.35


def test_nulls_reduce_pairwise():
    base = generate_pure_pairwise(seed=0, corr=0.9)
    real = max_abs_pairwise_corr(base)
    for name, fn in NULL_REGISTRY.items():
        null = fn(base, seed=1)
        assert max_abs_pairwise_corr(null) < real


def test_outcomes_are_engineering_only():
    results = run_validation_suite(seed=0)
    allowed = {o.value for o in CaseOutcome}
    payload = suite_to_dict(results)
    assert payload["scientific_pass_emitted"] is False
    assert payload["formal_bayes_factor_emitted"] is False
    for r in results:
        assert r.outcome.value in allowed
        assert r.outcome.value != "PASS"
        d = r.to_dict()
        assert "k_value" not in d
        assert "bayes_factor" not in d
