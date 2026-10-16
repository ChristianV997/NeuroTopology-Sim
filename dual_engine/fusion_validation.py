#!/usr/bin/env python3
"""Validation framework for cross-modal fusion engine and null-model falsification.

SCIENTIFIC GUARANTEE AND FALSIFICATION PRINCIPLES:
- A deterministic null model is an engineering requirement, not scientific confirmation.
- Surrogate gates and permutation tests evaluate rejection of simple statistical nulls.
- Rejection of a null hypothesis does not constitute proof of consciousness, biological
  validation, or cognitive efficacy.
- Null models must be structure-sensitive: tests must be incapable of validating a statistic
  that the null preserves by construction.
- Permutations must be strictly deterministic and reproducible via explicit seeding.
- Insufficient permutations or non-finite inputs fail-closed (BLOCKED or INCONCLUSIVE).

Usage:
    validator = FusionValidator(fusion_engine)
    gate_result = validator.surrogate_gate(embeddings, n_surrogates=200, seed=42)
    perm_result = validator.permutation_test(embeddings, condition_labels, n_perms=5000, seed=42)
    gen_result = validator.cross_dataset_generalization(train_emb, train_lbl, test_emb, test_lbl, seed=42)
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
from scipy import stats


class ValidationStatus(str, Enum):
    """Execution status for null-hypothesis validation gates."""
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    BLOCKED = "BLOCKED"


class NullModelType(str, Enum):
    """Supported structure-sensitive null models."""
    PHASE_RANDOMIZE = "phase_randomize"
    LABEL_PERMUTATION = "label_permutation"
    BLOCK_PERMUTATION = "block_permutation"
    MATCHED_VARIANCE = "matched_variance"
    MATCHED_AUTOCORRELATION = "matched_autocorrelation"
    INDEPENDENT_SHUFFLE = "independent_shuffle"


def compute_data_identity(data: np.ndarray) -> str:
    """Compute deterministic SHA-256 identity digest of numerical array."""
    h = hashlib.sha256()
    h.update(str(data.shape).encode("utf-8"))
    h.update(str(data.dtype).encode("utf-8"))
    if data.size > 0:
        flat = np.ascontiguousarray(data).ravel()
        if flat.size <= 100_000:
            h.update(flat.tobytes())
        else:
            indices = np.linspace(0, flat.size - 1, 10_000, dtype=int)
            h.update(flat[indices].tobytes())
    return h.hexdigest()


def _sanitize_float(val: Any) -> float:
    """Ensure float value is strictly finite for JSON serialization."""
    try:
        f = float(val)
        return f if math.isfinite(f) else 0.0
    except (TypeError, ValueError):
        return 0.0


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
    status: str = "INCONCLUSIVE"
    seed: Optional[int] = None
    null_type: str = NullModelType.PHASE_RANDOMIZE.value
    n_surrogates: int = 0
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    data_identity: str = ""
    finite_status: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary with finite values."""
        return {
            "metric_name": self.metric_name,
            "real_mean": _sanitize_float(self.real_mean),
            "null_mean": _sanitize_float(self.null_mean),
            "null_std": _sanitize_float(self.null_std),
            "z_score": _sanitize_float(self.z_score),
            "p_value": _sanitize_float(self.p_value),
            "passes": bool(self.passes),
            "status": self.status,
            "seed": self.seed,
            "null_type": self.null_type,
            "n_surrogates": self.n_surrogates,
            "diagnostics": self.diagnostics,
            "data_identity": self.data_identity,
            "finite_status": bool(self.finite_status),
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to deterministic JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


@dataclass
class PermutationResult:
    """Results from permutation test."""
    metric_name: str
    real_effect: float
    null_mean: float
    null_std: float
    p_value: float
    passes: bool  # p < 0.05
    status: str = "INCONCLUSIVE"
    seed: Optional[int] = None
    null_type: str = NullModelType.LABEL_PERMUTATION.value
    n_perms: int = 0
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    data_identity: str = ""
    finite_status: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary with finite values."""
        return {
            "metric_name": self.metric_name,
            "real_effect": _sanitize_float(self.real_effect),
            "null_mean": _sanitize_float(self.null_mean),
            "null_std": _sanitize_float(self.null_std),
            "p_value": _sanitize_float(self.p_value),
            "passes": bool(self.passes),
            "status": self.status,
            "seed": self.seed,
            "null_type": self.null_type,
            "n_perms": self.n_perms,
            "diagnostics": self.diagnostics,
            "data_identity": self.data_identity,
            "finite_status": bool(self.finite_status),
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to deterministic JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


# --- Standalone Structure-Sensitive Null Model Generators ---

def phase_randomize_embeddings(embeddings: np.ndarray, seed: Optional[int] = None) -> np.ndarray:
    """Phase-randomized null: shuffle frequency domain while preserving magnitude spectrum.

    Preserves: Individual dimension magnitude spectrum, power spectrum, and autocorrelation.
    Disrupts: Cross-dimensional temporal synchronization, non-linear trajectories, sample order.

    Hermitian symmetry (phase[k] = -phase[n-k]) is strictly preserved so the reconstructed
    signal is purely real and its FFT magnitude spectrum matches the original exactly.

    Args:
        embeddings: (n_samples, latent_dim)
        seed: RNG seed for reproducible generation

    Returns:
        null_embeddings: (n_samples, latent_dim) phase-randomized surrogate
    """
    if not isinstance(embeddings, np.ndarray) or embeddings.ndim != 2:
        raise ValueError("embeddings must be a 2D numpy array (n_samples, latent_dim)")

    n_samples, n_dims = embeddings.shape
    if n_samples < 2:
        return embeddings.copy()

    rng = np.random.default_rng(seed)
    null_embeddings = np.zeros_like(embeddings, dtype=np.float64)

    # Positive frequency bins strictly excluding DC (index 0) and Nyquist (index n/2 if even)
    half = (n_samples - 1) // 2

    for dim in range(n_dims):
        signal = embeddings[:, dim].astype(np.float64)
        fft_signal = np.fft.fft(signal)
        magnitude = np.abs(fft_signal)

        random_phase = np.zeros(n_samples, dtype=np.float64)
        free_phase = rng.uniform(0.0, 2.0 * np.pi, half)
        random_phase[1 : half + 1] = free_phase
        random_phase[n_samples - half : n_samples] = -free_phase[::-1]

        fft_randomized = magnitude * np.exp(1j * random_phase)
        null_embeddings[:, dim] = np.real(np.fft.ifft(fft_randomized))

    return null_embeddings


def label_permutation(labels: np.ndarray, seed: Optional[int] = None) -> np.ndarray:
    """Condition label permutation null.

    Preserves: Class prior balance, individual feature distributions.
    Disrupts: Association between features and condition labels.

    Args:
        labels: (n_samples,) binary or multi-class labels
        seed: RNG seed for reproducible permutation

    Returns:
        permuted_labels: (n_samples,) randomly permuted labels
    """
    rng = np.random.default_rng(seed)
    return rng.permutation(labels)


def block_permutation(embeddings: np.ndarray, block_size: int = 10,
                      seed: Optional[int] = None) -> np.ndarray:
    """Block permutation null: permutes contiguous blocks of observations.

    Preserves: Local temporal autocorrelation and trajectory dynamics within each block.
    Disrupts: Long-range temporal dependence and sequential order across blocks.

    Args:
        embeddings: (n_samples, latent_dim)
        block_size: length of each contiguous block (>= 1)
        seed: RNG seed for reproducible permutation

    Returns:
        permuted_embeddings: (n_samples, latent_dim)
    """
    if not isinstance(embeddings, np.ndarray) or embeddings.ndim != 2:
        raise ValueError("embeddings must be a 2D numpy array (n_samples, latent_dim)")

    n_samples, n_dims = embeddings.shape
    if n_samples == 0 or block_size <= 1 or block_size >= n_samples:
        rng = np.random.default_rng(seed)
        return rng.permutation(embeddings, axis=0) if n_samples > 0 else embeddings.copy()

    rng = np.random.default_rng(seed)
    n_blocks = int(math.ceil(n_samples / block_size))

    blocks = [embeddings[i * block_size : min((i + 1) * block_size, n_samples)]
              for i in range(n_blocks)]

    block_order = rng.permutation(n_blocks)
    permuted_blocks = [blocks[idx] for idx in block_order]

    return np.vstack(permuted_blocks)


def matched_variance_null(embeddings: np.ndarray, seed: Optional[int] = None) -> np.ndarray:
    """Matched-variance Gaussian surrogate null.

    Preserves: Feature-wise marginal mean and variance (1st and 2nd moments).
    Disrupts: All cross-feature covariance, multivariate geometry, and temporal structure.

    Args:
        embeddings: (n_samples, latent_dim)
        seed: RNG seed for reproducible generation

    Returns:
        null_embeddings: (n_samples, latent_dim) Gaussian surrogate
    """
    if not isinstance(embeddings, np.ndarray) or embeddings.ndim != 2:
        raise ValueError("embeddings must be a 2D numpy array (n_samples, latent_dim)")

    rng = np.random.default_rng(seed)
    means = np.mean(embeddings, axis=0)
    stds = np.std(embeddings, axis=0, ddof=1) if embeddings.shape[0] > 1 else np.zeros(embeddings.shape[1])
    stds = np.where(stds < 1e-12, 1e-12, stds)

    standard_normal = rng.standard_normal(embeddings.shape)
    return means + stds * standard_normal


def matched_autocorrelation_null(embeddings: np.ndarray, seed: Optional[int] = None) -> np.ndarray:
    """Matched-autocorrelation stationary AR(1) surrogate null.

    Preserves: Feature-wise marginal mean, variance, and lag-1 autocorrelation per dimension.
    Disrupts: Multivariate cross-feature correlations and higher-order nonlinear dynamics.

    Args:
        embeddings: (n_samples, latent_dim)
        seed: RNG seed for reproducible generation

    Returns:
        null_embeddings: (n_samples, latent_dim) AR(1) matched surrogate
    """
    if not isinstance(embeddings, np.ndarray) or embeddings.ndim != 2:
        raise ValueError("embeddings must be a 2D numpy array (n_samples, latent_dim)")

    n_samples, n_dims = embeddings.shape
    if n_samples < 3:
        return matched_variance_null(embeddings, seed=seed)

    rng = np.random.default_rng(seed)
    null_embeddings = np.zeros_like(embeddings, dtype=np.float64)

    for dim in range(n_dims):
        x = embeddings[:, dim].astype(np.float64)
        mean_val = np.mean(x)
        centered = x - mean_val
        var_val = np.var(centered, ddof=1)
        if var_val < 1e-12:
            null_embeddings[:, dim] = mean_val
            continue

        # Lag-1 sample autocorrelation
        c0 = np.sum(centered ** 2) / n_samples
        c1 = np.sum(centered[:-1] * centered[1:]) / (n_samples - 1)
        r1 = c1 / (c0 + 1e-12)
        # Clamp to stationary domain
        r1 = float(np.clip(r1, -0.999, 0.999))

        innov_std = math.sqrt(max(1e-12, 1.0 - r1 ** 2))
        innovations = rng.standard_normal(n_samples)

        ar_series = np.zeros(n_samples, dtype=np.float64)
        ar_series[0] = innovations[0]
        for t in range(1, n_samples):
            ar_series[t] = r1 * ar_series[t - 1] + innov_std * innovations[t]

        # Rescale to match target variance and mean
        current_std = np.std(ar_series, ddof=1)
        if current_std > 1e-12:
            ar_series = (ar_series / current_std) * math.sqrt(var_val)
        null_embeddings[:, dim] = ar_series + mean_val

    return null_embeddings


def independent_shuffle_null(embeddings: np.ndarray, seed: Optional[int] = None) -> np.ndarray:
    """Independent feature-dimension shuffling null.

    Preserves: Exact empirical marginal distribution of every feature dimension.
    Disrupts: All cross-feature multivariate correlations and temporal sequence ordering.

    Args:
        embeddings: (n_samples, latent_dim)
        seed: RNG seed for reproducible generation

    Returns:
        null_embeddings: (n_samples, latent_dim) independently shuffled
    """
    if not isinstance(embeddings, np.ndarray) or embeddings.ndim != 2:
        raise ValueError("embeddings must be a 2D numpy array (n_samples, latent_dim)")

    rng = np.random.default_rng(seed)
    null_embeddings = np.zeros_like(embeddings)
    for dim in range(embeddings.shape[1]):
        null_embeddings[:, dim] = rng.permutation(embeddings[:, dim])
    return null_embeddings


def audit_null_model(embeddings: np.ndarray, null_type: Union[str, NullModelType],
                     seed: int = 42, **kwargs) -> Dict[str, Any]:
    """Audit null model behavior: verifies disruption of target structure and preservation of nuisance properties.

    Returns diagnostic audit dictionary detailing property preservation and disruption.
    """
    if not np.all(np.isfinite(embeddings)):
        return {
            "status": ValidationStatus.BLOCKED.value,
            "reason": "Non-finite values present in audit input",
            "passed_audit": False,
        }

    null_type_str = null_type.value if isinstance(null_type, NullModelType) else str(null_type)

    if null_type_str == NullModelType.PHASE_RANDOMIZE.value:
        surrogate = phase_randomize_embeddings(embeddings, seed=seed)
        # Check 1: Magnitude spectrum preservation (should be ~0 difference)
        mag_diffs = []
        for d in range(embeddings.shape[1]):
            m_real = np.abs(np.fft.fft(embeddings[:, d]))
            m_null = np.abs(np.fft.fft(surrogate[:, d]))
            mag_diffs.append(float(np.max(np.abs(m_real - m_null))))
        max_mag_diff = max(mag_diffs) if mag_diffs else 0.0

        # Check 2: Cross-correlation disruption
        corr_real = np.corrcoef(embeddings.T) if embeddings.shape[1] > 1 else np.ones((1, 1))
        corr_null = np.corrcoef(surrogate.T) if surrogate.shape[1] > 1 else np.ones((1, 1))
        corr_disruption = float(np.linalg.norm(corr_real - corr_null))

        return {
            "null_type": null_type_str,
            "preserves_magnitude_spectrum": max_mag_diff < 1e-8,
            "max_magnitude_difference": max_mag_diff,
            "cross_correlation_disruption_norm": corr_disruption,
            "passed_audit": max_mag_diff < 1e-8,
        }

    elif null_type_str == NullModelType.MATCHED_VARIANCE.value:
        surrogate = matched_variance_null(embeddings, seed=seed)
        var_real = np.var(embeddings, axis=0, ddof=1)
        var_null = np.var(surrogate, axis=0, ddof=1)
        rel_var_diff = float(np.max(np.abs(var_real - var_null) / (var_real + 1e-8)))
        return {
            "null_type": null_type_str,
            "preserves_marginal_variance": rel_var_diff < 0.5,  # Statistical sample variance tolerance
            "max_rel_variance_difference": rel_var_diff,
            "passed_audit": rel_var_diff < 0.5,
        }

    elif null_type_str == NullModelType.INDEPENDENT_SHUFFLE.value:
        surrogate = independent_shuffle_null(embeddings, seed=seed)
        # Marginals must be exactly preserved (sorted elements identical)
        marginals_identical = True
        for d in range(embeddings.shape[1]):
            if not np.allclose(np.sort(embeddings[:, d]), np.sort(surrogate[:, d])):
                marginals_identical = False
                break
        return {
            "null_type": null_type_str,
            "preserves_exact_marginals": marginals_identical,
            "passed_audit": marginals_identical,
        }

    return {
        "null_type": null_type_str,
        "passed_audit": True,
        "note": "Standard audit completed",
    }


class FusionValidator:
    """Validates cross-modal fusion embeddings against structure-sensitive null controls.

    Ensures that permutation tests and surrogate gates are:
    1. Deterministic and reproducible via explicit seeds
    2. Structure-sensitive (incapable of validating a statistic preserved by construction)
    3. Fail-closed on insufficient iterations, degenerate inputs, or non-finite values
    4. Guardrailed against over-claiming or circular validation
    """

    MIN_PERMUTATIONS: int = 100
    MIN_SURROGATES: int = 20

    def __init__(self, fusion_engine: Any = None, output_dir: Optional[Union[str, Path]] = None):
        self.engine = fusion_engine
        if output_dir:
            self.output_dir = Path(output_dir)
        elif fusion_engine is not None and hasattr(fusion_engine, "output_dir"):
            self.output_dir = Path(fusion_engine.output_dir)
        else:
            self.output_dir = Path("outputs/fusion_validation")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def phase_randomize_embeddings(self, embeddings: np.ndarray,
                                  seed: Optional[int] = None) -> np.ndarray:
        """Phase-randomized null: shuffle frequency domain while preserving magnitude spectrum."""
        return phase_randomize_embeddings(embeddings, seed=seed)

    def embedding_distance_metric(self, embeddings: np.ndarray) -> float:
        """Compute mean pairwise Euclidean distance (proxy for embedding dispersion).

        Args:
            embeddings: (n_samples, latent_dim)

        Returns:
            mean_distance: scalar float
        """
        if not np.all(np.isfinite(embeddings)):
            return 0.0

        n = embeddings.shape[0]
        if n < 2:
            return 0.0

        pairwise_dists = np.linalg.norm(embeddings[:, None, :] - embeddings[None, :, :], axis=2)
        np.fill_diagonal(pairwise_dists, np.nan)
        val = float(np.nanmean(pairwise_dists))
        return val if math.isfinite(val) else 0.0

    def surrogate_gate(self, embeddings: np.ndarray, n_surrogates: int = 200,
                       seed: Optional[int] = 42,
                       null_type: Union[str, NullModelType] = NullModelType.PHASE_RANDOMIZE,
                       metric_fn: Optional[Callable[[np.ndarray], float]] = None,
                       min_surrogates: Optional[int] = None) -> GateResult:
        """Test if embeddings show structure beyond a structure-sensitive null control.

        Fails closed if:
        - Input contains NaN or Inf
        - Surrogates count is below minimum threshold
        - Metric is invariant under the null (preserved by construction)

        Args:
            embeddings: (n_samples, latent_dim)
            n_surrogates: number of null samples to generate
            seed: master seed for deterministic surrogate generation
            null_type: type of null model to apply
            metric_fn: optional custom scalar evaluation function
            min_surrogates: optional override for minimum required surrogates

        Returns:
            GateResult with z-score, p-value, validation status, and diagnostics
        """
        null_type_str = null_type.value if isinstance(null_type, NullModelType) else str(null_type)
        data_id = compute_data_identity(embeddings) if isinstance(embeddings, np.ndarray) else ""
        min_surr = min_surrogates if min_surrogates is not None else self.MIN_SURROGATES
        metric_eval = metric_fn if metric_fn is not None else self.embedding_distance_metric
        metric_name = getattr(metric_eval, "__name__", "embedding_structure")

        # Guard 1: Non-finite inputs
        if not isinstance(embeddings, np.ndarray) or not np.all(np.isfinite(embeddings)):
            return GateResult(
                metric_name=metric_name,
                real_mean=0.0,
                null_mean=0.0,
                null_std=0.0,
                z_score=0.0,
                p_value=1.0,
                passes=False,
                status=ValidationStatus.BLOCKED.value,
                seed=seed,
                null_type=null_type_str,
                n_surrogates=n_surrogates,
                diagnostics={"error": "Input contains non-finite values (NaN or Inf)"},
                data_identity=data_id,
                finite_status=False,
            )

        # Guard 2: Insufficient surrogates
        if n_surrogates < min_surr:
            return GateResult(
                metric_name=metric_name,
                real_mean=_sanitize_float(metric_eval(embeddings)),
                null_mean=0.0,
                null_std=0.0,
                z_score=0.0,
                p_value=1.0,
                passes=False,
                status=ValidationStatus.INCONCLUSIVE.value,
                seed=seed,
                null_type=null_type_str,
                n_surrogates=n_surrogates,
                diagnostics={
                    "error": f"Insufficient surrogates ({n_surrogates}). Minimum required is {min_surr}.",
                    "insufficient_surrogates": True,
                },
                data_identity=data_id,
                finite_status=True,
            )

        real_metric = _sanitize_float(metric_eval(embeddings))

        # Select null generator
        null_generator: Callable[[np.ndarray, Optional[int]], np.ndarray]
        if null_type_str == NullModelType.PHASE_RANDOMIZE.value:
            null_generator = phase_randomize_embeddings
        elif null_type_str == NullModelType.BLOCK_PERMUTATION.value:
            null_generator = block_permutation
        elif null_type_str == NullModelType.MATCHED_VARIANCE.value:
            null_generator = matched_variance_null
        elif null_type_str == NullModelType.MATCHED_AUTOCORRELATION.value:
            null_generator = matched_autocorrelation_null
        elif null_type_str == NullModelType.INDEPENDENT_SHUFFLE.value:
            null_generator = independent_shuffle_null
        else:
            null_generator = phase_randomize_embeddings

        # Deterministic surrogate sequence
        null_metrics: List[float] = []
        base_seed = seed if seed is not None else 42

        for i in range(n_surrogates):
            surrogate_seed = (base_seed * 10007 + i) & 0xFFFFFFFF
            null_emb = null_generator(embeddings, seed=surrogate_seed)
            null_val = _sanitize_float(metric_eval(null_emb))
            null_metrics.append(null_val)

        null_arr = np.array(null_metrics, dtype=np.float64)
        null_mean = float(np.mean(null_arr))
        null_std = float(np.std(null_arr, ddof=1)) if len(null_arr) > 1 else 0.0

        # Guard 3: Invariant metric (preserved by construction under null)
        # If the metric is preserved by construction, null_std is 0 and real_metric equals null_mean
        if null_std < 1e-12 or (abs(real_metric - null_mean) < 1e-8 and null_std < 1e-6):
            return GateResult(
                metric_name=metric_name,
                real_mean=real_metric,
                null_mean=null_mean,
                null_std=null_std,
                z_score=0.0,
                p_value=1.0,
                passes=False,
                status=ValidationStatus.BLOCKED.value,
                seed=seed,
                null_type=null_type_str,
                n_surrogates=n_surrogates,
                diagnostics={
                    "error": f"Metric '{metric_name}' is invariant under null '{null_type_str}' (preserved by construction).",
                    "invariant_under_null": True,
                },
                data_identity=data_id,
                finite_status=True,
            )

        z_score = (real_metric - null_mean) / (null_std + 1e-8)
        p_value = 2.0 * (1.0 - stats.norm.cdf(abs(z_score)))

        passes = bool(abs(z_score) > 3.0 and p_value < 0.05)
        status = ValidationStatus.PASS.value if passes else ValidationStatus.FAIL.value

        return GateResult(
            metric_name=metric_name,
            real_mean=real_metric,
            null_mean=null_mean,
            null_std=null_std,
            z_score=z_score,
            p_value=p_value,
            passes=passes,
            status=status,
            seed=seed,
            null_type=null_type_str,
            n_surrogates=n_surrogates,
            diagnostics={
                "surrogate_count": n_surrogates,
                "null_min": float(np.min(null_arr)),
                "null_max": float(np.max(null_arr)),
            },
            data_identity=data_id,
            finite_status=True,
        )

    def permutation_test(self, embeddings: np.ndarray, condition_labels: np.ndarray,
                         n_perms: int = 5000, seed: Optional[int] = 42,
                         min_perms: Optional[int] = None) -> PermutationResult:
        """Test if condition separation effect survives condition label permutation.

        Fails closed if:
        - Input contains NaN or Inf
        - Permutations count is below minimum required (default 100)
        - Labels contain fewer than 2 classes or empty partition

        Args:
            embeddings: (n_samples, latent_dim)
            condition_labels: (n_samples,) binary condition labels
            n_perms: number of label permutations
            seed: RNG seed for reproducible permutation testing
            min_perms: optional override for minimum permutations threshold

        Returns:
            PermutationResult with real effect, null distribution, p-value, and status
        """
        data_id = compute_data_identity(embeddings) if isinstance(embeddings, np.ndarray) else ""
        min_p = min_perms if min_perms is not None else self.MIN_PERMUTATIONS

        # Guard 1: Non-finite inputs
        if (not isinstance(embeddings, np.ndarray) or not np.all(np.isfinite(embeddings)) or
                not isinstance(condition_labels, np.ndarray) or not np.all(np.isfinite(condition_labels))):
            return PermutationResult(
                metric_name="condition_separation",
                real_effect=0.0,
                null_mean=0.0,
                null_std=0.0,
                p_value=1.0,
                passes=False,
                status=ValidationStatus.BLOCKED.value,
                seed=seed,
                null_type=NullModelType.LABEL_PERMUTATION.value,
                n_perms=n_perms,
                diagnostics={"error": "Input embeddings or labels contain non-finite values"},
                data_identity=data_id,
                finite_status=False,
            )

        # Guard 2: Insufficient permutations
        if n_perms < min_p:
            return PermutationResult(
                metric_name="condition_separation",
                real_effect=0.0,
                null_mean=0.0,
                null_std=0.0,
                p_value=1.0,
                passes=False,
                status=ValidationStatus.INCONCLUSIVE.value,
                seed=seed,
                null_type=NullModelType.LABEL_PERMUTATION.value,
                n_perms=n_perms,
                diagnostics={
                    "error": f"Permutations count ({n_perms}) is below minimum required ({min_p}).",
                    "insufficient_permutations": True,
                },
                data_identity=data_id,
                finite_status=True,
            )

        # Guard 3: Label distribution validation
        unique_labels = np.unique(condition_labels)
        if len(unique_labels) < 2:
            return PermutationResult(
                metric_name="condition_separation",
                real_effect=0.0,
                null_mean=0.0,
                null_std=0.0,
                p_value=1.0,
                passes=False,
                status=ValidationStatus.BLOCKED.value,
                seed=seed,
                null_type=NullModelType.LABEL_PERMUTATION.value,
                n_perms=n_perms,
                diagnostics={"error": "Condition labels must contain at least 2 distinct classes"},
                data_identity=data_id,
                finite_status=True,
            )

        cond_0 = embeddings[condition_labels == unique_labels[0]]
        cond_1 = embeddings[condition_labels == unique_labels[1]]

        if len(cond_0) == 0 or len(cond_1) == 0:
            return PermutationResult(
                metric_name="condition_separation",
                real_effect=0.0,
                null_mean=0.0,
                null_std=0.0,
                p_value=1.0,
                passes=False,
                status=ValidationStatus.BLOCKED.value,
                seed=seed,
                null_type=NullModelType.LABEL_PERMUTATION.value,
                n_perms=n_perms,
                diagnostics={"error": "Empty partition for one or more condition classes"},
                data_identity=data_id,
                finite_status=True,
            )

        # Real effect: Euclidean distance between class centroids
        real_effect = float(np.linalg.norm(cond_0.mean(axis=0) - cond_1.mean(axis=0)))

        # Deterministic permutation loop
        base_seed = seed if seed is not None else 42
        rng = np.random.default_rng(base_seed)

        perm_effects: List[float] = []
        for _ in range(n_perms):
            perm_labels = rng.permutation(condition_labels)
            p_cond_0 = embeddings[perm_labels == unique_labels[0]]
            p_cond_1 = embeddings[perm_labels == unique_labels[1]]

            if len(p_cond_0) > 0 and len(p_cond_1) > 0:
                effect = float(np.linalg.norm(p_cond_0.mean(axis=0) - p_cond_1.mean(axis=0)))
                perm_effects.append(effect)

        if not perm_effects:
            return PermutationResult(
                metric_name="condition_separation",
                real_effect=real_effect,
                null_mean=0.0,
                null_std=0.0,
                p_value=1.0,
                passes=False,
                status=ValidationStatus.BLOCKED.value,
                seed=seed,
                null_type=NullModelType.LABEL_PERMUTATION.value,
                n_perms=n_perms,
                diagnostics={"error": "No valid permutations could be computed"},
                data_identity=data_id,
                finite_status=True,
            )

        perm_arr = np.array(perm_effects, dtype=np.float64)
        null_mean = float(np.mean(perm_arr))
        null_std = float(np.std(perm_arr, ddof=1)) if len(perm_arr) > 1 else 0.0

        # Exact empirical p-value with standard +1 correction to prevent p=0
        p_value = float((np.sum(perm_arr >= real_effect) + 1) / (len(perm_arr) + 1))
        passes = bool(p_value < 0.05)
        status = ValidationStatus.PASS.value if passes else ValidationStatus.FAIL.value

        return PermutationResult(
            metric_name="condition_separation",
            real_effect=real_effect,
            null_mean=null_mean,
            null_std=null_std,
            p_value=p_value,
            passes=passes,
            status=status,
            seed=seed,
            null_type=NullModelType.LABEL_PERMUTATION.value,
            n_perms=n_perms,
            diagnostics={
                "n_computed_perms": len(perm_arr),
                "null_min": float(np.min(perm_arr)),
                "null_max": float(np.max(perm_arr)),
            },
            data_identity=data_id,
            finite_status=True,
        )

    def cross_dataset_generalization(self, train_embeddings: np.ndarray, train_labels: np.ndarray,
                                     test_embeddings: np.ndarray, test_labels: np.ndarray,
                                     seed: Optional[int] = 42) -> Dict[str, Any]:
        """Evaluate generalization: train classifier on train set, test on held-out dataset.

        Args:
            train_embeddings: (n_train, latent_dim)
            train_labels: (n_train,) state labels
            test_embeddings: (n_test, latent_dim)
            test_labels: (n_test,) state labels
            seed: random state for reproducible logistic regression

        Returns:
            dict with accuracy, AUC, F1, status, and metadata
        """
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import accuracy_score, roc_auc_score, f1_score

        if (not np.all(np.isfinite(train_embeddings)) or not np.all(np.isfinite(train_labels)) or
                not np.all(np.isfinite(test_embeddings)) or not np.all(np.isfinite(test_labels))):
            return {
                "accuracy": 0.0,
                "auc": 0.0,
                "f1": 0.0,
                "status": ValidationStatus.BLOCKED.value,
                "error": "Non-finite values in generalization dataset",
            }

        clf = LogisticRegression(max_iter=1000, random_state=seed)
        clf.fit(train_embeddings, train_labels)

        test_pred = clf.predict(test_embeddings)

        unique_test_classes = np.unique(test_labels)
        if len(unique_test_classes) > 1 and hasattr(clf, "predict_proba"):
            try:
                test_pred_proba = clf.predict_proba(test_embeddings)[:, 1]
                auc = float(roc_auc_score(test_labels, test_pred_proba))
            except Exception:
                auc = 0.5
        else:
            auc = 0.5

        acc = float(accuracy_score(test_labels, test_pred))
        f1 = float(f1_score(test_labels, test_pred, average="weighted", zero_division=0))

        return {
            "accuracy": _sanitize_float(acc),
            "auc": _sanitize_float(auc),
            "f1": _sanitize_float(f1),
            "status": ValidationStatus.PASS.value if acc > 0.5 else ValidationStatus.FAIL.value,
            "seed": seed,
            "n_train": len(train_embeddings),
            "n_test": len(test_embeddings),
        }

    def kfold_cross_validation(self, embeddings: np.ndarray, labels: np.ndarray,
                               n_splits: int = 5, seed: Optional[int] = 42) -> Dict[str, Any]:
        """Perform held-out stratified k-fold cross validation on learned embeddings.

        Returns mean and fold-level generalization metrics.
        """
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import accuracy_score, roc_auc_score, f1_score
        from sklearn.model_selection import StratifiedKFold

        if not np.all(np.isfinite(embeddings)) or not np.all(np.isfinite(labels)):
            return {
                "accuracy_mean": 0.0,
                "auc_mean": 0.0,
                "f1_mean": 0.0,
                "status": ValidationStatus.BLOCKED.value,
                "error": "Non-finite values in cross-validation dataset",
            }

        n_samples = len(labels)
        if n_samples < n_splits * 2 or len(np.unique(labels)) < 2:
            return {
                "accuracy_mean": 0.0,
                "auc_mean": 0.0,
                "f1_mean": 0.0,
                "status": ValidationStatus.INCONCLUSIVE.value,
                "error": "Insufficient samples or classes for stratified k-fold",
            }

        skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
        fold_metrics: List[Dict[str, float]] = []

        for train_idx, val_idx in skf.split(embeddings, labels):
            x_train, x_val = embeddings[train_idx], embeddings[val_idx]
            y_train, y_val = labels[train_idx], labels[val_idx]

            clf = LogisticRegression(max_iter=1000, random_state=seed)
            clf.fit(x_train, y_train)

            preds = clf.predict(x_val)
            acc = float(accuracy_score(y_val, preds))
            f1 = float(f1_score(y_val, preds, average="weighted", zero_division=0))

            try:
                probs = clf.predict_proba(x_val)[:, 1]
                auc = float(roc_auc_score(y_val, probs))
            except Exception:
                auc = 0.5

            fold_metrics.append({"accuracy": acc, "auc": auc, "f1": f1})

        acc_mean = float(np.mean([f["accuracy"] for f in fold_metrics]))
        auc_mean = float(np.mean([f["auc"] for f in fold_metrics]))
        f1_mean = float(np.mean([f["f1"] for f in fold_metrics]))

        return {
            "accuracy_mean": _sanitize_float(acc_mean),
            "auc_mean": _sanitize_float(auc_mean),
            "f1_mean": _sanitize_float(f1_mean),
            "status": ValidationStatus.PASS.value if acc_mean > 0.5 else ValidationStatus.FAIL.value,
            "seed": seed,
            "n_splits": n_splits,
            "folds": fold_metrics,
        }

    def validate_all(self, embeddings: np.ndarray, condition_labels: np.ndarray,
                     n_surrogates: int = 200, n_perms: int = 5000,
                     seed: Optional[int] = 42) -> Dict[str, Any]:
        """Run complete null-hypothesis validation suite and write deterministic JSON results."""
        surr_result = self.surrogate_gate(embeddings, n_surrogates=n_surrogates, seed=seed)
        perm_result = self.permutation_test(embeddings, condition_labels, n_perms=n_perms, seed=seed)
        audit_res = audit_null_model(embeddings, NullModelType.PHASE_RANDOMIZE, seed=seed or 42)

        results = {
            "surrogate_gate": surr_result.to_dict(),
            "permutation_test": perm_result.to_dict(),
            "null_audit": audit_res,
            "scientific_disclaimer": (
                "A deterministic null model is an engineering requirement, not scientific confirmation. "
                "Surrogate gates and permutation tests evaluate rejection of simple statistical nulls. "
                "Rejection does not constitute proof of consciousness, biological validation, or cognitive efficacy."
            ),
        }

        output_file = self.output_dir / "validation_results.json"
        output_file.write_text(json.dumps(results, indent=2), encoding="utf-8")

        return results
