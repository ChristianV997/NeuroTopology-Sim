"""Transparent comparison of PITNN and classical Wilson-Cowan surrogates."""
import math
import numpy as np


def _fit_linear(y: np.ndarray, design: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    beta, *_ = np.linalg.lstsq(design, y, rcond=None)
    return design @ beta, beta


def _fit_l1(y: np.ndarray, design: np.ndarray, penalty: float, iterations: int = 2000) -> tuple[np.ndarray, np.ndarray]:
    """Coordinate-descent L1 fit; intercept is the first unpenalized column."""
    if penalty < 0 or not np.isfinite(penalty): raise ValueError("l1 penalty must be finite and non-negative")
    x = np.asarray(design, float); beta = np.zeros(x.shape[1]); beta[0] = float(np.mean(y))
    scale = np.sqrt(np.sum(x[:, 1:] ** 2, axis=0)); scale[scale == 0] = 1.0
    xs = x.copy(); xs[:, 1:] /= scale
    for _ in range(iterations):
        previous = beta.copy(); beta[0] = float(np.mean(y - xs[:, 1:] @ beta[1:]))
        for column in range(1, xs.shape[1]):
            residual = y - xs @ beta + xs[:, column] * beta[column]
            rho = float(xs[:, column] @ residual); norm = float(xs[:, column] @ xs[:, column])
            beta[column] = np.sign(rho) * max(abs(rho) - penalty, 0.0) / max(norm, np.finfo(float).tiny)
        if np.max(np.abs(beta - previous)) < 1e-12: break
    original = beta.copy(); original[1:] /= scale
    return x @ original, original


def _aicc(rss: float, n: int, k: int) -> float:
    if n <= k + 1 or rss <= 0:
        return float("inf")
    return float(n * math.log(rss / n) + 2 * k + (2 * k * (k + 1)) / (n - k - 1))


def compare_models(signal: np.ndarray, inversion: dict, *, topological_l1_penalty: float = 1e-4) -> dict:
    y = np.asarray(signal, dtype=float).reshape(-1)
    if y.size < 8 or not np.all(np.isfinite(y)):
        raise ValueError("at least eight finite observations are required")
    x = np.linspace(0.0, 1.0, y.size)
    q_series = inversion.get("q_emp_series", inversion.get("topological_charge_series"))
    if q_series is None:
        topology = np.full(y.size, float(inversion.get("q_emp_mean", 0.0)))
    else:
        source = np.asarray(q_series, dtype=float).reshape(-1)
        if source.size < 2 or not np.all(np.isfinite(source)): raise ValueError("topological series must contain at least two finite values")
        topology = np.interp(x, np.linspace(0.0, 1.0, source.size), source)
    topology_static = bool(np.ptp(topology) <= 1e-12)
    topological = np.column_stack([np.ones(y.size), x, np.sin(2*np.pi*x), np.cos(2*np.pi*x), topology])
    classical = np.column_stack([np.ones(y.size), x, np.sin(2*np.pi*x), np.cos(2*np.pi*x)])
    pred_q, beta_q = _fit_l1(y, topological, topological_l1_penalty)
    pred_c, _ = _fit_linear(y, classical)
    rss_q = float(np.sum((y - pred_q) ** 2)); rss_c = float(np.sum((y - pred_c) ** 2))
    active_q = int(1 + np.count_nonzero(np.abs(beta_q[1:]) > 1e-12))
    aicc_q = _aicc(rss_q, y.size, active_q); aicc_c = _aicc(rss_c, y.size, classical.shape[1])
    # Gaussian likelihood ratio with common unknown variance, reported as a
    # descriptive Bayes-factor proxy; no prior-sensitive claim is implied.
    log_k = 0.5 * y.size * math.log(max(rss_c, np.finfo(float).tiny) / max(rss_q, np.finfo(float).tiny))
    log_k = float(np.clip(log_k, -700.0, 700.0))
    k = float(math.exp(log_k))
    topological_active = bool(not topology_static and abs(beta_q[-1]) > 1e-12)
    return {"pitnn": {"rss": rss_q, "aicc": aicc_q, "topological_l1_penalty": topological_l1_penalty,
                      "topological_weight": float(beta_q[-1]), "topological_feature_static": topology_static,
                      "topological_feature_active": topological_active, "active_parameters": active_q}, "classical_wilson_cowan": {"rss": rss_c, "aicc": aicc_c},
            "log_bayes_factor": log_k, "bayes_factor": k,
            "verdict": "PASS" if k > 100.0 else "NOT_SUPPORTED", "threshold": 100.0}
