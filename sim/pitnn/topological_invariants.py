"""Discrete topological-invariant tracking for PITNN spin configurations.

The ``beta1_loops`` value is a localized-defect proxy, not a replacement for
formal persistent homology.  All calculations are snapshot-local and require
an ordered periodic spin ring.
"""
from __future__ import annotations

import numpy as np


class TopologicalInvariantTracker:
    """Compute winding, scalar chirality, and a beta-1 defect proxy."""

    def __init__(self, num_spins: int):
        if int(num_spins) < 3:
            raise ValueError("num_spins must be at least 3")
        self.N = int(num_spins)

    def _validate(self, spins: np.ndarray) -> np.ndarray:
        values = np.asarray(spins, dtype=float)
        if values.shape != (self.N, 3):
            raise ValueError(f"spins must have shape {(self.N, 3)}")
        if not np.all(np.isfinite(values)):
            raise ValueError("spins must contain only finite values")
        return values

    def compute_winding_number(self, spins: np.ndarray) -> float:
        """Compute the periodic XY-plane winding number ``W``."""
        values = self._validate(spins)
        phi = np.arctan2(values[:, 1], values[:, 0])
        dphi = np.diff(phi, append=phi[0])
        wrapped = (dphi + np.pi) % (2.0 * np.pi) - np.pi
        return float(np.round(np.sum(wrapped) / (2.0 * np.pi), 6))

    def compute_chirality_density(self, spins: np.ndarray) -> np.ndarray:
        """Compute ``q_i = S_i · (S_(i+1) × S_(i+2))`` on periodic triads."""
        values = self._validate(spins)
        s1 = np.roll(values, -1, axis=0)
        s2 = np.roll(values, -2, axis=0)
        return np.einsum("ij,ij->i", values, np.cross(s1, s2))

    def compute_topological_charge(self, spins: np.ndarray) -> float:
        """Return integrated normalized scalar chirality ``Q``."""
        return float(np.sum(self.compute_chirality_density(spins)) / (4.0 * np.pi))

    def compute_beta1_proxy(self, spins: np.ndarray, threshold: float = 0.3) -> int:
        """Count localized triad defects whose absolute chirality exceeds threshold."""
        if threshold < 0.0 or not np.isfinite(threshold):
            raise ValueError("threshold must be finite and non-negative")
        return int(np.count_nonzero(np.abs(self.compute_chirality_density(spins)) > threshold))

    def audit_snapshot(self, spins: np.ndarray, threshold: float = 0.3) -> dict:
        """Return the complete invariant snapshot for one spin-ring state."""
        density = self.compute_chirality_density(spins)
        return {
            "winding_number": self.compute_winding_number(spins),
            "topological_charge": float(np.sum(density) / (4.0 * np.pi)),
            "beta1_loops": self.compute_beta1_proxy(spins, threshold=threshold),
            "max_chirality": float(np.max(np.abs(density))),
            "mean_chirality": float(np.mean(density)),
        }
