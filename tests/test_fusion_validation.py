"""Tests for cross-modal fusion validation framework, determinism, and fail-closed gates."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from dual_engine.fusion_validation import (
    FusionValidator,
    GateResult,
    NullModelType,
    PermutationResult,
    ValidationStatus,
    compute_data_identity,
)


@pytest.fixture
def sample_embeddings() -> np.ndarray:
    """Deterministic synthetic embeddings (100 samples, 16 dimensions)."""
    rng = np.random.default_rng(12345)
    # Generate structured trajectories (superposition of slow sines + noise)
    t = np.linspace(0, 4 * np.pi, 100)[:, None]
    base = np.sin(t * np.linspace(1, 4, 16)[None, :])
    noise = rng.normal(0, 0.2, (100, 16))
    return base + noise


@pytest.fixture
def condition_labels() -> np.ndarray:
    """Balanced binary condition labels."""
    return np.array([0] * 50 + [1] * 50)


class TestFusionValidatorDeterminism:
    """Verify that permutation and surrogate gates are strictly deterministic and reproducible."""

    def test_surrogate_gate_repeatability(self, sample_embeddings: np.ndarray, tmp_path: Path):
        validator = FusionValidator(output_dir=tmp_path)
        res1 = validator.surrogate_gate(sample_embeddings, n_surrogates=50, seed=42)
        res2 = validator.surrogate_gate(sample_embeddings, n_surrogates=50, seed=42)

        assert res1.real_mean == res2.real_mean
        assert res1.null_mean == res2.null_mean
        assert res1.null_std == res2.null_std
        assert res1.z_score == res2.z_score
        assert res1.p_value == res2.p_value
        assert res1.passes == res2.passes
        assert res1.status == res2.status

    def test_surrogate_gate_seed_divergence(self, sample_embeddings: np.ndarray, tmp_path: Path):
        validator = FusionValidator(output_dir=tmp_path)
        res1 = validator.surrogate_gate(sample_embeddings, n_surrogates=30, seed=42)
        res2 = validator.surrogate_gate(sample_embeddings, n_surrogates=30, seed=999)

        # Real metric is identical, but null distributions differ across seeds
        assert res1.real_mean == res2.real_mean
        assert res1.null_mean != res2.null_mean or res1.null_std != res2.null_std

    def test_permutation_test_repeatability(self, sample_embeddings: np.ndarray,
                                            condition_labels: np.ndarray, tmp_path: Path):
        validator = FusionValidator(output_dir=tmp_path)
        res1 = validator.permutation_test(sample_embeddings, condition_labels, n_perms=200, seed=101)
        res2 = validator.permutation_test(sample_embeddings, condition_labels, n_perms=200, seed=101)

        assert res1.real_effect == res2.real_effect
        assert res1.null_mean == res2.null_mean
        assert res1.null_std == res2.null_std
        assert res1.p_value == res2.p_value
        assert res1.passes == res2.passes
        assert res1.status == res2.status

    def test_permutation_test_seed_divergence(self, sample_embeddings: np.ndarray,
                                              condition_labels: np.ndarray, tmp_path: Path):
        validator = FusionValidator(output_dir=tmp_path)
        res1 = validator.permutation_test(sample_embeddings, condition_labels, n_perms=150, seed=11)
        res2 = validator.permutation_test(sample_embeddings, condition_labels, n_perms=150, seed=77)

        assert res1.real_effect == res2.real_effect
        assert res1.null_mean != res2.null_mean or res1.null_std != res2.null_std


class TestFailClosedSemantics:
    """Verify that validator fails closed under degenerate conditions, invalid input, or insufficient iterations."""

    def test_insufficient_permutations_fails_closed(self, sample_embeddings: np.ndarray,
                                                    condition_labels: np.ndarray, tmp_path: Path):
        validator = FusionValidator(output_dir=tmp_path)
        # Attempt permutation test with only 20 iterations (below default min 100)
        result = validator.permutation_test(sample_embeddings, condition_labels, n_perms=20)

        assert result.status == ValidationStatus.INCONCLUSIVE.value
        assert not result.passes
        assert result.diagnostics.get("insufficient_permutations") is True

    def test_insufficient_surrogates_fails_closed(self, sample_embeddings: np.ndarray, tmp_path: Path):
        validator = FusionValidator(output_dir=tmp_path)
        # Attempt surrogate gate with only 5 surrogates (below default min 20)
        result = validator.surrogate_gate(sample_embeddings, n_surrogates=5)

        assert result.status == ValidationStatus.INCONCLUSIVE.value
        assert not result.passes
        assert result.diagnostics.get("insufficient_surrogates") is True

    def test_non_finite_embeddings_blocked(self, sample_embeddings: np.ndarray,
                                           condition_labels: np.ndarray, tmp_path: Path):
        corrupted = sample_embeddings.copy()
        corrupted[10, 2] = np.nan
        corrupted[25, 4] = np.inf

        validator = FusionValidator(output_dir=tmp_path)

        gate_res = validator.surrogate_gate(corrupted, n_surrogates=50, seed=42)
        assert gate_res.status == ValidationStatus.BLOCKED.value
        assert not gate_res.passes
        assert not gate_res.finite_status

        perm_res = validator.permutation_test(corrupted, condition_labels, n_perms=100, seed=42)
        assert perm_res.status == ValidationStatus.BLOCKED.value
        assert not perm_res.passes
        assert not perm_res.finite_status

    def test_degenerate_labels_blocked(self, sample_embeddings: np.ndarray, tmp_path: Path):
        validator = FusionValidator(output_dir=tmp_path)
        # All labels are 0 (no condition contrast)
        mono_labels = np.zeros(len(sample_embeddings), dtype=int)
        res = validator.permutation_test(sample_embeddings, mono_labels, n_perms=100)

        assert res.status == ValidationStatus.BLOCKED.value
        assert not res.passes


class TestStructureSensitivityAndInvariantMetrics:
    """Verify that tests are incapable of validating a statistic preserved by the null by construction."""

    def test_invariant_metric_under_null_blocked(self, sample_embeddings: np.ndarray, tmp_path: Path):
        validator = FusionValidator(output_dir=tmp_path)

        # Define a statistic that solely measures total power / FFT energy
        # Because phase_randomize preserves magnitude spectrum exactly, this statistic
        # is PRESERVED BY CONSTRUCTION under phase randomization!
        def total_spectral_power(x: np.ndarray) -> float:
            return float(np.sum(np.abs(np.fft.fft(x, axis=0)) ** 2))

        result = validator.surrogate_gate(
            sample_embeddings,
            n_surrogates=30,
            seed=42,
            null_type=NullModelType.PHASE_RANDOMIZE,
            metric_fn=total_spectral_power,
        )

        assert result.status == ValidationStatus.BLOCKED.value
        assert not result.passes
        assert result.diagnostics.get("invariant_under_null") is True
        assert result.z_score == 0.0

    def test_constant_metric_blocked(self, sample_embeddings: np.ndarray, tmp_path: Path):
        validator = FusionValidator(output_dir=tmp_path)

        def dummy_constant_metric(_: np.ndarray) -> float:
            return 42.0

        result = validator.surrogate_gate(
            sample_embeddings,
            n_surrogates=25,
            seed=42,
            metric_fn=dummy_constant_metric,
        )

        assert result.status == ValidationStatus.BLOCKED.value
        assert not result.passes
        assert result.diagnostics.get("invariant_under_null") is True


class TestHeldOutGeneralization:
    """Verify cross-dataset and cross-validation generalization routines."""

    def test_cross_dataset_generalization_deterministic(self, sample_embeddings: np.ndarray,
                                                        condition_labels: np.ndarray, tmp_path: Path):
        validator = FusionValidator(output_dir=tmp_path)
        train_emb = sample_embeddings[:60]
        train_lbl = condition_labels[:60]
        test_emb = sample_embeddings[60:]
        test_lbl = condition_labels[60:]

        res1 = validator.cross_dataset_generalization(train_emb, train_lbl, test_emb, test_lbl, seed=42)
        res2 = validator.cross_dataset_generalization(train_emb, train_lbl, test_emb, test_lbl, seed=42)

        assert res1["accuracy"] == res2["accuracy"]
        assert res1["auc"] == res2["auc"]
        assert res1["f1"] == res2["f1"]
        assert 0.0 <= res1["accuracy"] <= 1.0

    def test_stratified_kfold_cross_validation(self, sample_embeddings: np.ndarray,
                                              condition_labels: np.ndarray, tmp_path: Path):
        validator = FusionValidator(output_dir=tmp_path)
        res = validator.kfold_cross_validation(sample_embeddings, condition_labels, n_splits=5, seed=42)

        assert res["status"] in (ValidationStatus.PASS.value, ValidationStatus.FAIL.value)
        assert "accuracy_mean" in res
        assert "auc_mean" in res
        assert "f1_mean" in res
        assert len(res["folds"]) == 5

    def test_generalization_fallback_without_sklearn(self, sample_embeddings: np.ndarray,
                                                    condition_labels: np.ndarray, tmp_path: Path):
        """Regression test: verify fallback solver functions directly."""
        from dual_engine.fusion_validation import (
            _fit_predict_logistic_fallback,
            _accuracy_score_fallback,
            _roc_auc_score_fallback,
            _f1_score_fallback,
            _stratified_kfold_fallback,
        )

        train_emb = sample_embeddings[:60]
        train_lbl = condition_labels[:60]
        test_emb = sample_embeddings[60:]
        test_lbl = condition_labels[60:]

        pred, prob = _fit_predict_logistic_fallback(train_emb, train_lbl, test_emb, seed=42)
        assert len(pred) == len(test_lbl)
        assert len(prob) == len(test_lbl)
        assert np.all((prob >= 0.0) & (prob <= 1.0))

        acc = _accuracy_score_fallback(test_lbl, pred)
        assert 0.0 <= acc <= 1.0

        auc = _roc_auc_score_fallback(test_lbl, prob)
        assert 0.0 <= auc <= 1.0

        f1 = _f1_score_fallback(test_lbl, pred)
        assert 0.0 <= f1 <= 1.0

        splits = _stratified_kfold_fallback(condition_labels, n_splits=5, seed=42)
        assert len(splits) == 5
        for train_idx, val_idx in splits:
            assert len(train_idx) + len(val_idx) == len(condition_labels)
            assert len(np.intersect1d(train_idx, val_idx)) == 0


class TestSerializationAndGovernance:
    """Verify serialization to finite JSON and governance outputs."""

    def test_gate_result_serialization(self):
        res = GateResult(
            metric_name="dispersion",
            real_mean=1.5,
            null_mean=1.2,
            null_std=0.1,
            z_score=3.0,
            p_value=0.0027,
            passes=True,
            status=ValidationStatus.PASS.value,
            seed=42,
            null_type=NullModelType.PHASE_RANDOMIZE.value,
            n_surrogates=50,
            diagnostics={"info": "valid"},
            data_identity="hash_abc123",
            finite_status=True,
        )

        d = res.to_dict()
        assert d["metric_name"] == "dispersion"
        assert d["passes"] is True

        j_str = res.to_json()
        parsed = json.loads(j_str)
        assert parsed["seed"] == 42
        assert parsed["null_type"] == "phase_randomize"

    def test_validate_all_writes_finite_json(self, sample_embeddings: np.ndarray,
                                            condition_labels: np.ndarray, tmp_path: Path):
        validator = FusionValidator(output_dir=tmp_path)
        results = validator.validate_all(
            sample_embeddings,
            condition_labels,
            n_surrogates=25,
            n_perms=120,
            seed=42,
        )

        assert "surrogate_gate" in results
        assert "permutation_test" in results
        assert "scientific_disclaimer" in results
        assert "null_audit" in results

        out_path = tmp_path / "validation_results.json"
        assert out_path.exists()
        loaded = json.loads(out_path.read_text(encoding="utf-8"))
        assert loaded["surrogate_gate"]["status"] in [s.value for s in ValidationStatus]
        assert "not scientific confirmation" in loaded["scientific_disclaimer"]
