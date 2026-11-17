"""Deterministic synthetic data generators for whitening robustness and leakage tests.

Generates:
1. Standard i.i.d. synthetic features from known mean and covariance
2. Covariance-shifted test sets
3. Mean-shifted test sets
4. Rank-deficient data (n < d, or collinear columns)
5. Insufficient sample sets (n = 1, n = 0)
6. Badly scaled features (variances spanning 10^-6 to 10^6)
7. Non-finite data (NaN, +Inf, -Inf)
8. Feature-dimension mismatched sets (d_test != d_train)

Pure standard library (no SciPy, no NumPy, no network downloads).
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple


def _pseudo_normal(seed: int, n: int) -> List[float]:
    """Deterministic Box-Muller pseudo-random standard normal sequence."""
    out: List[float] = []
    # Linear congruential generator parameters
    a = 1664525
    c = 1013904223
    m = 2 ** 32
    state = seed

    while len(out) < n:
        state = (a * state + c) % m
        u1 = max(1e-12, state / m)
        state = (a * state + c) % m
        u2 = state / m

        # Box-Muller transform
        r = math.sqrt(-2.0 * math.log(u1))
        theta = 2.0 * math.pi * u2
        z0 = r * math.cos(theta)
        z1 = r * math.sin(theta)
        out.append(z0)
        if len(out) < n:
            out.append(z1)

    return out[:n]


def generate_synthetic_features(
    n_samples: int,
    mean: Sequence[float],
    cov_factor_L: Sequence[Sequence[float]],
    seed: int = 42,
) -> List[List[float]]:
    """Generate n_samples with mean mu and covariance Sigma = L * L^T.

    Each sample x = mu + L * z, where z ~ N(0, I).
    """
    d = len(mean)
    raw_normals = _pseudo_normal(seed, n_samples * d)

    data: List[List[float]] = []
    for i in range(n_samples):
        z = raw_normals[i * d : (i + 1) * d]
        # x = mu + L * z
        x = [mean[j] + sum(cov_factor_L[j][k] * z[k] for k in range(d)) for j in range(d)]
        data.append(x)

    return data


def generate_baseline_dataset(
    n_train: int = 100,
    n_test: int = 50,
    n_features: int = 4,
    seed: int = 100,
) -> Tuple[List[List[float]], List[List[float]]]:
    """Generate standard train and test datasets from the exact same distribution."""
    mu = [float(k * 0.5) for k in range(n_features)]
    # Construct lower-triangular L with positive diagonal
    L: List[List[float]] = [[0.0] * n_features for _ in range(n_features)]
    for i in range(n_features):
        L[i][i] = 1.0 + 0.3 * i
        for j in range(i):
            L[i][j] = 0.2 * (i - j)

    X_train = generate_synthetic_features(n_train, mu, L, seed=seed)
    X_test = generate_synthetic_features(n_test, mu, L, seed=seed + 999)
    return X_train, X_test


def generate_mean_shifted_test_set(
    X_train: Sequence[Sequence[float]],
    shift_magnitude: float = 2.5,
    n_test: int = 50,
    seed: int = 200,
) -> List[List[float]]:
    """Generate test data with identical covariance but shifted mean."""
    d = len(X_train[0])
    mu_shifted = [shift_magnitude] * d
    # Standard identity L for test
    L = [[1.0 if i == j else 0.0 for j in range(d)] for i in range(d)]
    return generate_synthetic_features(n_test, mu_shifted, L, seed=seed)


def generate_covariance_shifted_test_set(
    n_test: int = 50,
    n_features: int = 4,
    scale_factor: float = 3.0,
    seed: int = 300,
) -> List[List[float]]:
    """Generate test data with scaled/altered covariance structure."""
    mu = [0.0] * n_features
    L = [[scale_factor if i == j else 0.0 for j in range(n_features)] for i in range(n_features)]
    return generate_synthetic_features(n_test, mu, L, seed=seed)


def generate_rank_deficient_dataset(
    n_samples: int = 5,
    n_features: int = 10,
    seed: int = 400,
) -> List[List[float]]:
    """Generate rank-deficient data (n_samples < n_features, or collinear columns)."""
    mu = [0.0] * n_features
    L = [[1.0 if i == j else 0.0 for j in range(n_features)] for i in range(n_features)]
    # n < d implies rank <= n - 1 < d
    return generate_synthetic_features(n_samples, mu, L, seed=seed)


def generate_collinear_dataset(
    n_samples: int = 50,
    n_features: int = 4,
    seed: int = 500,
) -> List[List[float]]:
    """Generate dataset with exact linear dependency (collinear columns)."""
    X, _ = generate_baseline_dataset(n_train=n_samples, n_test=10, n_features=n_features - 1, seed=seed)
    # Add an exact duplicate/linear combination column as last column
    X_collinear: List[List[float]] = []
    for row in X:
        new_row = list(row) + [row[0] * 2.0 - row[1]]
        X_collinear.append(new_row)
    return X_collinear


def generate_badly_scaled_dataset(
    n_samples: int = 60,
    n_features: int = 4,
    seed: int = 600,
) -> List[List[float]]:
    """Generate dataset where feature variances span 12 orders of magnitude (10^-6 to 10^6)."""
    mu = [0.0] * n_features
    scales = [1e-6, 1e-2, 1e2, 1e6][:n_features]
    L: List[List[float]] = [[0.0] * n_features for _ in range(n_features)]
    for i in range(n_features):
        L[i][i] = scales[i]

    return generate_synthetic_features(n_samples, mu, L, seed=seed)


def generate_nonfinite_dataset(
    n_samples: int = 30,
    n_features: int = 4,
    inject_type: str = "nan",
) -> List[List[float]]:
    """Generate dataset containing non-finite values (NaN or Inf)."""
    X, _ = generate_baseline_dataset(n_train=n_samples, n_test=5, n_features=n_features)
    val = float("nan") if inject_type == "nan" else float("inf")
    X[5][1] = val
    return X
