#!/usr/bin/env python3
"""Validation framework for cross-modal fusion engine.

Validates that learned latent representations:
1. Pass surrogate gates (phase-randomized null tests)
2. Resist permutation (condition labels shuffled)
3. Generalize across datasets
4. Preserve topological structure (z-score separation from null)

Usage:
    validator = FusionValidator(fusion_engine)
    gate_result = validator.surrogate_gate(embeddings, labels, n_surrogates=200)
    perm_result = validator.permutation_test(embeddings, condition_labels, n_perms=5000)
"""
from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass
from typing import Tuple, Dict

import numpy as np
from scipy import stats
import torch


@dataclass
class GateResult:
    """Results from surrogate gate validation."""
    metric_name: str
    real_mean: float
    null_mean: float
    null_std: float
    z_score: float
    p_value: float
    passes: bool  # |z| > 3 and p < 0.05


@dataclass
class PermutationResult:
    """Results from permutation test."""
    metric_name: str
    real_effect: float
    null_mean: float
    null_std: float
    p_value: float
    passes: bool  # p < 0.05


class FusionValidator:
    """Validates cross-modal fusion embeddings against null controls."""

    def __init__(self, fusion_engine, output_dir: Path | None = None):
        self.engine = fusion_engine
        self.output_dir = Path(output_dir or fusion_engine.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def phase_randomize_embeddings(self, embeddings: np.ndarray, seed: int | None = None) -> np.ndarray:
        """Phase-randomized null: shuffle frequency domain while preserving magnitude spectrum.

        Applies FFT → randomize phase → IFFT to each embedding dimension,
        creating a spectrally-matched null while destroying cross-sample structure.

        Args:
            embeddings: (n_samples, latent_dim)
            seed: RNG seed for reproducibility

        Returns:
            null_embeddings: (n_samples, latent_dim) phase-randomized
        """
        rng = np.random.default_rng(seed)

        null_embeddings = np.zeros_like(embeddings)
        n = embeddings.shape[0]
        # Number of independent positive-frequency bins (excludes DC, and
        # excludes the Nyquist bin for even n -- both must stay real-valued,
        # i.e. phase 0, for the inverse transform to come out real).
        half = (n - 1) // 2

        for dim in range(embeddings.shape[1]):
            signal = embeddings[:, dim]

            # FFT
            fft_signal = np.fft.fft(signal)
            magnitude = np.abs(fft_signal)

            # Randomize phase, preserving Hermitian symmetry (phase[k] =
            # -phase[n-k]) so the reconstructed signal is real AND its FFT
            # magnitude spectrum is exactly `magnitude` again. Randomizing
            # every bin independently (the prior implementation) breaks that
            # symmetry, so np.real(ifft(...)) discards an imaginary residual
            # and the resulting magnitude spectrum silently drifts from the
            # original -- the null was not actually magnitude-preserving.
            random_phase = np.zeros(n)
            free_phase = rng.uniform(0, 2 * np.pi, half)
            random_phase[1:half + 1] = free_phase
            random_phase[n - half:n] = -free_phase[::-1]

            # Reconstruct
            fft_randomized = magnitude * np.exp(1j * random_phase)
            null_embeddings[:, dim] = np.real(np.fft.ifft(fft_randomized))

        return null_embeddings

    def embedding_distance_metric(self, embeddings: np.ndarray) -> float:
        """Compute mean pairwise Euclidean distance (proxy for "structure").

        Args:
            embeddings: (n_samples, latent_dim)

        Returns:
            mean_distance: scalar
        """
        pairwise_dists = np.linalg.norm(embeddings[:, None, :] - embeddings[None, :, :], axis=2)
        # Exclude diagonal (self-distance)
        np.fill_diagonal(pairwise_dists, np.nan)
        return np.nanmean(pairwise_dists)

    def surrogate_gate(self, embeddings: np.ndarray, n_surrogates: int = 200) -> GateResult:
        """Test if embeddings show structure beyond phase-randomized null.

        Args:
            embeddings: (n_samples, latent_dim)
            n_surrogates: number of null samples to generate

        Returns:
            GateResult with z-score and pass/fail
        """
        real_metric = self.embedding_distance_metric(embeddings)

        null_metrics = []
        for i in range(n_surrogates):
            null_emb = self.phase_randomize_embeddings(embeddings, seed=i)
            null_metrics.append(self.embedding_distance_metric(null_emb))

        null_metrics = np.array(null_metrics)
        null_mean = np.mean(null_metrics)
        null_std = np.std(null_metrics, ddof=1)

        # Z-score: how many SDs is real below null?
        # (We expect real > null for structured data, so z = (real - null_mean) / null_std)
        z_score = (real_metric - null_mean) / (null_std + 1e-8)
        p_value = 2 * (1 - stats.norm.cdf(abs(z_score)))  # Two-sided

        passes = abs(z_score) > 3 and p_value < 0.05

        result = GateResult(
            metric_name="embedding_structure",
            real_mean=real_metric,
            null_mean=null_mean,
            null_std=null_std,
            z_score=z_score,
            p_value=p_value,
            passes=passes,
        )

        return result

    def permutation_test(self, embeddings: np.ndarray, condition_labels: np.ndarray,
                        n_perms: int = 5000) -> PermutationResult:
        """Test if condition effect survives label permutation.

        Args:
            embeddings: (n_samples, latent_dim)
            condition_labels: (n_samples,) binary condition (0 or 1)
            n_perms: number of label permutations

        Returns:
            PermutationResult with p-value
        """
        # Real effect: distance between condition centroids
        cond_0 = embeddings[condition_labels == 0]
        cond_1 = embeddings[condition_labels == 1]

        real_effect = np.linalg.norm(cond_0.mean(axis=0) - cond_1.mean(axis=0))

        # Permuted effects
        perm_effects = []
        for i in range(n_perms):
            perm_labels = np.random.permutation(condition_labels)
            perm_cond_0 = embeddings[perm_labels == 0]
            perm_cond_1 = embeddings[perm_labels == 1]

            if len(perm_cond_0) > 0 and len(perm_cond_1) > 0:
                perm_effect = np.linalg.norm(perm_cond_0.mean(axis=0) - perm_cond_1.mean(axis=0))
                perm_effects.append(perm_effect)

        perm_effects = np.array(perm_effects)
        p_value = (np.sum(perm_effects >= real_effect) + 1) / (len(perm_effects) + 1)

        result = PermutationResult(
            metric_name="condition_separation",
            real_effect=real_effect,
            null_mean=np.mean(perm_effects),
            null_std=np.std(perm_effects, ddof=1),
            p_value=p_value,
            passes=p_value < 0.05,
        )

        return result

    def cross_dataset_generalization(self, train_embeddings: np.ndarray, train_labels: np.ndarray,
                                     test_embeddings: np.ndarray, test_labels: np.ndarray) -> Dict:
        """Evaluate generalization: train simple classifier on train set, test on held-out dataset.

        Args:
            train_embeddings: (n_train, latent_dim)
            train_labels: (n_train,) binary state labels
            test_embeddings: (n_test, latent_dim)
            test_labels: (n_test,) binary state labels

        Returns:
            dict with accuracy, AUC, F1
        """
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import accuracy_score, roc_auc_score, f1_score

        # Train simple logistic regression
        clf = LogisticRegression(max_iter=1000)
        clf.fit(train_embeddings, train_labels)

        # Predict on test set
        test_pred = clf.predict(test_embeddings)
        test_pred_proba = clf.predict_proba(test_embeddings)[:, 1]

        results = {
            "accuracy": accuracy_score(test_labels, test_pred),
            "auc": roc_auc_score(test_labels, test_pred_proba),
            "f1": f1_score(test_labels, test_pred),
        }

        return results

    def validate_all(self, embeddings: np.ndarray, condition_labels: np.ndarray,
                    n_surrogates: int = 200, n_perms: int = 5000) -> Dict:
        """Run all validation tests."""
        results = {
            "surrogate_gate": self.surrogate_gate(embeddings, n_surrogates=n_surrogates).__dict__,
            "permutation_test": self.permutation_test(embeddings, condition_labels, n_perms=n_perms).__dict__,
        }

        # Save to file
        (self.output_dir / "validation_results.json").write_text(json.dumps(results, indent=2))

        return results
