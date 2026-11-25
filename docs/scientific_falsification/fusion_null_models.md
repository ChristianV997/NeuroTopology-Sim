# Structure-Sensitive Null Models and Fusion Validation

## 1. Executive Summary and Epistemic Boundaries

> **Scientific Disclaimer**  
> *A deterministic null model is an engineering requirement, not scientific confirmation.*  
> Surrogate gates, label permutations, and cross-validation procedures evaluate the rejection of simple statistical null hypotheses. Rejection of a statistical null hypothesis does not constitute proof of consciousness, biological validation, causal efficacy, or ontology promotion. All statistical inferences in this layer serve solely as descriptive falsification gates.

The `dual_engine.fusion_validation` module provides a structure-sensitive, fail-closed validation framework for cross-modal latent embeddings. It replaces unseeded global permutations and naive distance metrics with:
1. **Deterministic RNG**: Strict adherence to `numpy.random.default_rng(seed)` across all null generators, permutation loops, and classifiers.
2. **Structure-Sensitive Null Models**: A taxonomy of six distinct surrogate generators that selectively preserve declared nuisance properties while disrupting specific hypothesized dependencies.
3. **Invariance Detection (Preserved by Construction)**: Automated detection of degenerate or circular test statistics that the null preserves by construction, preventing false-positive validation claims.
4. **Fail-Closed Semantics**: Explicit `PASS`, `FAIL`, `INCONCLUSIVE`, and `BLOCKED` status codes for insufficient permutation counts ($N < 100$), degenerate condition labels, or non-finite inputs ($NaN$, $\pm\infty$).
5. **Held-Out Generalization**: Cross-dataset evaluation and stratified $K$-fold cross-validation with deterministic seed guarantees.

---

## 2. Scientific Motivation

Previous implementations relied on global random states (`np.random.permutation`), lacked structural controls, and evaluated scalar metrics without verifying whether the metric was invariant under the surrogate generator. 

A permutation or surrogate test is invalid if the chosen test statistic measures a mathematical property that the surrogate generator preserves by construction. For example:
- Testing feature variance against a Gaussian surrogate matched to sample variance will yield a trivial $z \approx 0$.
- Testing spectral power against a phase-randomized surrogate that exactly preserves the Fourier magnitude spectrum produces an invariant test with zero null variance.

The refactored framework enforces rigorous decoupling between nuisance properties (which the null preserves) and target structures (which the null destroys), backed by automated invariance detection.

---

## 3. Null Model Taxonomy and Mathematical Formulations

### 3.1. Spectral Phase Randomization (`phase_randomize`)
Phase randomization creates a spectrally-matched surrogate by preserving the Fourier magnitude spectrum while randomizing phase angles under Hermitian symmetry.

Given a univariate or single-dimension feature sequence $x \in \mathbb{R}^N$:
$$\tilde{X}[k] = \text{FFT}(x)[k] = |X[k]| e^{i \theta[k]}$$

We generate independent uniform random phases $\phi[k] \sim \mathcal{U}[0, 2\pi)$ for positive frequency bins $k \in \{1, \dots, \lfloor (N-1)/2 \rfloor\}$. To guarantee that the reconstructed inverse Fourier transform is strictly real-valued, Hermitian symmetry is enforced:
$$\Phi[k] = \begin{cases} 0 & k = 0 \text{ (DC component)} \\ \phi[k] & 1 \le k \le \lfloor(N-1)/2\rfloor \\ 0 & k = N/2 \text{ (if $N$ is even, Nyquist bin)} \\ -\phi[N - k] & \lfloor(N-1)/2\rfloor < k < N \end{cases}$$

Reconstruction via the inverse discrete Fourier transform:
$$x_{\text{null}} = \text{Re}\left(\text{IFFT}\left(|X[k]| e^{i \Phi[k]}\right)\right)$$

- **Preserves**: Exact empirical magnitude spectrum $|X[k]|$, power spectral density, linear temporal autocorrelation, and marginal sample variance.
- **Disrupts**: Cross-channel phase alignment, cross-feature covariance, non-linear trajectories, and sample ordering.

### 3.2. Condition Label Permutation (`label_permutation`)
Tests whether condition separation in latent space exceeds what would be observed under exchangeable assignment of condition labels.

Given embeddings $Z \in \mathbb{R}^{N \times D}$ and condition labels $y \in \{0, 1\}^N$:
$$y_{\text{null}} = \pi(y), \quad \pi \in \mathcal{S}_N$$
where $\pi$ is drawn uniformly from the symmetric group $\mathcal{S}_N$ via `rng.permutation`.

- **Preserves**: Marginal class priors $P(y=0), P(y=1)$, latent embedding geometry $Z$.
- **Disrupts**: Association between latent coordinates $Z_i$ and condition label $y_i$.

### 3.3. Block Permutation (`block_permutation`)
Preserves contiguous temporal autocorrelation within observation blocks while disrupting long-range sequences.

The $N$ observations are divided into $M = \lceil N / B \rceil$ blocks of length $B$:
$$\mathcal{B}_m = Z[m B : \min((m+1)B, N)], \quad m \in \{0, \dots, M-1\}$$
Blocks are concatenated according to a permuted block sequence $\sigma \in \mathcal{S}_M$:
$$Z_{\text{null}} = \left[ \mathcal{B}_{\sigma(0)} \,\|\, \mathcal{B}_{\sigma(1)} \,\|\, \dots \,\|\, \mathcal{B}_{\sigma(M-1)} \right]$$

- **Preserves**: Intra-block temporal dynamics, short-lag autocorrelation ($lag < B$).
- **Disrupts**: Inter-block sequence continuity, long-lag dependencies ($lag \ge B$).

### 3.4. Matched-Variance Gaussian Surrogates (`matched_variance`)
Constructs uncorrelated Gaussian noise matched to the first and second marginal sample moments of each feature dimension.

For each feature dimension $d \in \{1, \dots, D\}$:
$$\mu_d = \frac{1}{N} \sum_{i=1}^N Z_{i, d}, \quad \sigma_d^2 = \frac{1}{N-1} \sum_{i=1}^N (Z_{i, d} - \mu_d)^2$$
$$Z_{\text{null}, i, d} = \mu_d + \sigma_d \cdot \epsilon_{i, d}, \quad \epsilon_{i, d} \sim \mathcal{N}(0, 1)$$

- **Preserves**: Marginal mean $\mu_d$ and marginal variance $\sigma_d^2$.
- **Disrupts**: Multivariate covariance matrix $\Sigma$, cross-feature correlations, temporal sequence ordering, and higher-order moments.

### 3.5. Matched-Autocorrelation AR(1) Surrogates (`matched_autocorrelation`)
Generates stationary first-order autoregressive processes matching the empirical lag-1 sample autocorrelation $r_1$ and variance per dimension.

For centered signal $\tilde{z}_{t, d} = Z_{t, d} - \mu_d$:
$$r_1 = \frac{\sum_{t=1}^{N-1} \tilde{z}_{t, d} \tilde{z}_{t+1, d}}{\sum_{t=1}^N \tilde{z}_{t, d}^2}, \quad r_1 \in [-0.999, 0.999]$$
$$y_{t, d} = r_1 y_{t-1, d} + \sqrt{1 - r_1^2} \, \xi_{t, d}, \quad \xi_{t, d} \sim \mathcal{N}(0, 1)$$
$$Z_{\text{null}, t, d} = \mu_d + \frac{\sigma_d}{\text{std}(y_d)} y_{t, d}$$

- **Preserves**: Marginal mean, variance, and lag-1 autocorrelation $r_1$.
- **Disrupts**: Cross-channel multivariate covariance, non-linear dynamics, and higher-order lag dependencies.

### 3.6. Independent Feature Shuffling (`independent_shuffle`)
Permutes the sample ordering of each feature dimension independently.

$$Z_{\text{null}, i, d} = Z_{\pi_d(i), d}, \quad \pi_d \sim \mathcal{S}_N \text{ independently for each } d$$

- **Preserves**: Exact empirical 1D marginal distributions (all sorted values are identical).
- **Disrupts**: Multivariate joint distributions and all inter-feature correlations.

---

## 4. Nuisance Preservation vs. Structure Disruption Matrix

| Null Model | Preserved Nuisance Properties | Disrupted Target Structures | Valid Test Statistics | Invariant / Invalid Statistics |
| :--- | :--- | :--- | :--- | :--- |
| **Phase Randomization** | Fourier magnitude spectrum, power spectrum, autocorrelation | Cross-channel phase alignment, non-linear trajectories | Cross-modal correlation, topological persistence, pairwise dispersion | Power spectral density, total frequency energy |
| **Label Permutation** | Latent geometry, class prior distribution | Feature-label contingency $P(Y \mid X)$ | Centroid separation distance, classifier AUC / accuracy | Unsupervised cluster dispersion, latent variance |
| **Block Permutation** | Intra-block trajectories ($lag < B$) | Macro sequence ordering, long-range drift | Long-range transition graph, global winding | Local differential step-size within blocks |
| **Matched-Variance** | Feature means and sample variances | Multivariate covariance, temporal autocorrelation | Covariance Frobenius norm, pairwise Euclidean distances | Feature-wise sample mean, feature-wise sample variance |
| **Matched-Autocorrelation** | Feature mean, variance, lag-1 autocorrelation | Cross-feature correlation, non-linear dynamics | Multi-channel synchrony, cross-correlation matrix | Lag-1 autocorrelation coefficient |
| **Independent Shuffle** | Exact 1D empirical marginal distributions | Cross-feature joint distribution $\prod P(X_d) \neq P(X)$ | Multivariate mutual information, principal component weights | Univariate histogram, quantile metrics, median |

---

## 5. Invariant Metric Detection (Preserved by Construction)

To prevent circular reasoning, `FusionValidator.surrogate_gate` evaluates whether a test statistic is invariant under the applied null transform:

$$\sigma_{\text{null}} = \text{std}\left(\{ M(Z_{\text{null}}^{(j)}) \}_{j=1}^J\right)$$
$$\text{If } \sigma_{\text{null}} < 10^{-12} \quad \text{or} \quad \left(|M(Z) - \bar{M}_{\text{null}}| < 10^{-8} \text{ and } \sigma_{\text{null}} < 10^{-6}\right)$$

When invariance is detected:
- `status`: Set to `"BLOCKED"`.
- `passes`: Set to `False`.
- `z_score`: Clamped to `0.0`.
- `p_value`: Clamped to `1.0`.
- `diagnostics["invariant_under_null"]`: Set to `True`.
- `diagnostics["error"]`: Records that the metric is invariant under the null by construction.

---

## 6. Deterministic Seeding Policy

All random number generation is strictly isolated from Python's global `random` and NumPy's global `np.random.*`:
- Each validator method accepts an optional `seed: int | None = 42`.
- When `seed` is provided, surrogate sequences derive sub-seeds deterministically:
  $$\text{seed}_j = (\text{seed}_{\text{base}} \times 10007 + j) \pmod{2^{32}}$$
- Identical seeds produce bit-for-bit identical results across repeated runs.
- Distinct seeds produce statistically divergent surrogate sets.
- `cross_dataset_generalization` and `kfold_cross_validation` explicitly pass `random_state=seed` to `LogisticRegression` and `StratifiedKFold`.

---

## 7. Fail-Closed Semantics and Minimum Thresholds

The framework strictly fails closed when minimum inferential standards are not met:

| Condition | Threshold | Resulting Status | Passes | Diagnostic Flag |
| :--- | :--- | :--- | :--- | :--- |
| **Permutation Count** | $N_{\text{perms}} < 100$ | `INCONCLUSIVE` | `False` | `insufficient_permutations: True` |
| **Surrogate Count** | $N_{\text{surr}} < 20$ | `INCONCLUSIVE` | `False` | `insufficient_surrogates: True` |
| **Non-Finite Inputs** | Any $\text{NaN}$ or $\pm\infty$ | `BLOCKED` | `False` | `finite_status: False` |
| **Degenerate Labels** | Class count $< 2$ or empty partition | `BLOCKED` | `False` | `error: "Condition labels must contain at least 2 distinct classes"` |
| **Invariant Metric** | $\sigma_{\text{null}} < 10^{-12}$ | `BLOCKED` | `False` | `invariant_under_null: True` |

### Validation Status Values
- **`PASS`**: Statistically significant effect ($|z| > 3$ and $p < 0.05$ for gates; $p < 0.05$ for permutations) under valid, non-degenerate null controls.
- **`FAIL`**: Evaluation completed successfully, but the observed effect does not separate from the null distribution.
- **`INCONCLUSIVE`**: Iteration count (permutations or surrogates) is insufficient to compute an empirically reliable $p$-value.
- **`BLOCKED`**: Execution aborted due to corrupted input, invariant test statistic, or degenerate experimental design.

---

## 8. Finite JSON Serialization

All validator outputs (`GateResult`, `PermutationResult`, `validate_all`) are guaranteed to produce finite JSON:
- All floating-point outputs are sanitized through `math.isfinite`.
- Non-finite values ($\text{NaN}$, $\pm\infty$) are safely mapped to `0.0` or flagged via `finite_status = False`.
- Results include a deterministic SHA-256 data identity hash (`data_identity`) computed from array shape and data bytes.
- The standard output artifact `validation_results.json` includes the full gate results, permutation results, null audit diagnostics, and mandatory scientific disclaimers.
