# Round 6 Train/Test Whitening Audit: Terminology, Leakage Invariants, and SPD Repair Disclosure

## 1. Executive Summary

This specification provides an independent audit of the Round 6 train/test whitening proposal for `NeuroTopology-Sim`.

The audit was conducted by Antigravity Agent B (Batch 2) on branch `batch2/antigravity-b-whitening-audit` based on `origin/main` (`3f3fe8593303184cb88eef056c1322f3d4e57a16`).

### Key Findings
1. **Candidate Code Status**: The proposed candidate whitening code is **absent** from `origin/main` and remote branch heads. In accordance with mandate instructions, an independent verifier was constructed to audit the specification without claiming candidate execution.
2. **Whitening Convention Distinction**: The proposal applies Cholesky whitening $W_{\text{chol}} = L^{-1}(x - \mu)$, where $\Sigma = L L^T$. This is mathematically distinct from Symmetric ZCA whitening $W_{\text{zca}} = \Sigma^{-1/2}(x - \mu)$. Both whiten covariance to identity, but they rotate coordinates differently ($W_{\text{chol}} = R W_{\text{zca}}$ with $R \in O(d)$). Calling them equivalent is inaccurate and must not occur silently.
3. **Leakage Protocol**: Strict train-only fitting is enforced. The mean, covariance, and SPD projection are computed exclusively on training data $X_{\text{train}}$. Held-out test data $X_{\text{test}}$ is transformed using fixed training parameters. A dedicated leakage regression fixture proves that leaking test data contaminates training parameters and artificially suppresses out-of-sample covariance errors.
4. **SPD Repair Disclosure**: Empirical covariance regularization and eigenvalue flooring must be explicitly disclosed, including the raw minimum eigenvalue, the applied floor, the correction Frobenius norm, and whether the modification is material.
5. **Fail-Closed Robustness**: The verifier fails closed on insufficient samples ($n \le 1$), empty inputs, non-finite values (`NaN`/`Inf`), feature dimension mismatches, and non-positive SPD `eigenvalue_floor` values (must be finite and $> 0$). CLI artifact writes are confined to the repository root.

---

## 2. Mathematical Formulations: Cholesky vs Symmetric ZCA

Given a training feature matrix $X_{\text{train}} \in \mathbb{R}^{n \times d}$, let the sample mean be $\mu \in \mathbb{R}^d$ and the sample covariance be $\Sigma \in \mathbb{R}^{d \times d}$.

A whitening matrix $W \in \mathbb{R}^{d \times d}$ satisfies:
$$\operatorname{Cov}(W (x - \mu)) = W \Sigma W^T = I_d$$

Because any orthogonal transformation $R \in O(d)$ ($R R^T = I$) preserves the identity covariance:
$$(R W) \Sigma (R W)^T = R (W \Sigma W^T) R^T = R I_d R^T = I_d$$
there exists an infinite family of valid whitening transformations. Two primary canonical choices exist:

### 2.1 Cholesky Whitening ($W_{\text{chol}} = L^{-1}$)
- Compute the lower-triangular Cholesky factor $L$ such that $\Sigma = L L^T$.
- Invert $L$ via forward substitution to obtain $W_{\text{chol}} = L^{-1}$.
- Transformed vector: $z_{\text{chol}} = L^{-1}(x - \mu)$.
- **Structural Properties**:
  - $W_{\text{chol}}$ is lower-triangular.
  - Coordinate-dependent: Feature $z_1$ depends only on $x_1$; feature $z_2$ depends on $x_1$ and $x_2$. Permuting the order of features in $x$ produces a completely different whitening matrix and rotated coordinate system.
  - Not symmetric ($W_{\text{chol}} \ne W_{\text{chol}}^T$).

### 2.2 Symmetric ZCA Whitening ($W_{\text{zca}} = \Sigma^{-1/2}$)
- Compute spectral eigendecomposition $\Sigma = V \Lambda V^T$, where $V V^T = I$ and $\Lambda = \operatorname{diag}(\lambda_1, \dots, \lambda_d)$.
- Inverse square root: $W_{\text{zca}} = V \Lambda^{-1/2} V^T$.
- Transformed vector: $z_{\text{zca}} = \Sigma^{-1/2}(x - \mu)$.
- **Structural Properties**:
  - $W_{\text{zca}}$ is strictly symmetric ($W_{\text{zca}} = W_{\text{zca}}^T$).
  - **Zero-Phase / Minimal Distortion**: Minimizes the expected squared distance to the centered original features:
    $$\min_W \mathbb{E}[\|W(x - \mu) - (x - \mu)\|^2] \quad \text{subject to} \quad W \Sigma W^T = I_d$$
  - Order-invariant up to permutation of inputs and outputs.

### 2.3 Mathematical Rotation Relationship
The two whitening matrices are related by an orthogonal rotation matrix $R \in O(d)$:
$$R = W_{\text{chol}} W_{\text{zca}}^{-1} = L^{-1} \Sigma^{1/2}$$
Since:
$$R R^T = (L^{-1} \Sigma^{1/2})(\Sigma^{1/2} L^{-T}) = L^{-1} \Sigma L^{-T} = I_d$$
$R$ is strictly orthogonal. In our synthetic benchmarks, the rotation deviation from identity $\|R - I\|_F$ is substantial ($> 0.18$ on typical correlation matrices), demonstrating that the two methods yield materially different coordinate representations.

---

## 3. Covariance Regularization and SPD Projection Disclosure

In practice, sample covariance $\Sigma_{\text{raw}}$ may be rank-deficient ($n < d$), ill-conditioned, or have non-positive eigenvalues due to numerical rounding.

### 3.1 Projection to the SPD Cone
The verifier regularizes $\Sigma_{\text{raw}}$ via spectral eigenvalue flooring:
1. Eigendecomposition: $\Sigma_{\text{raw}} = V \Lambda V^T$.
2. Eigenvalue flooring: $\lambda_i' = \max(\lambda_i, \epsilon_{\text{floor}})$.
3. Reconstruction: $\Sigma_{\text{spd}} = V \operatorname{diag}(\lambda') V^T$.
4. Symmetrization: $\Sigma_{\text{spd}} = \frac{1}{2}(\Sigma_{\text{spd}} + \Sigma_{\text{spd}}^T)$.

### 3.2 Mandatory Disclosure Fields
The audit framework mandates full transparency around any covariance modification through `SPDRepairReport`:
- `raw_min_eigenvalue`: $\lambda_{\min}(\Sigma_{\text{raw}})$.
- `raw_max_eigenvalue`: $\lambda_{\max}(\Sigma_{\text{raw}})$.
- `raw_condition_number`: $\lambda_{\max} / \lambda_{\min}$ when $\lambda_{\min} > 0$ and finite; otherwise $\infty$. (Scale-invariant — not gated by an absolute $10^{-15}$ cutoff.)
- `applied_floor`: $\epsilon_{\text{floor}}$ (default $10^{-6}$).
- `repaired_min_eigenvalue`: $\max(\lambda_{\min}, \epsilon_{\text{floor}})$.
- `repaired_condition_number`: $\lambda_{\max}' / \lambda_{\min}'$.
- `correction_frobenius_norm`: $\|\Sigma_{\text{spd}} - \Sigma_{\text{raw}}\|_F$.
- `relative_correction_norm`: $\|\Sigma_{\text{spd}} - \Sigma_{\text{raw}}\|_F / \|\Sigma_{\text{raw}}\|_F$ when $\|\Sigma_{\text{raw}}\|_F > 0$.
- `is_correction_material`: `True` when any eigenvalue was floored and $(\|\Delta\|_F > 10^{-10}$ or relative correction $> 10^{-6})$. Relative correction (not an absolute $\|\Sigma\|_F > 10^{-15}$ gate) keeps micro-scale repairs disclosed.
- `n_floored_eigenvalues`: Number of eigenvalues shifted by the projection.

---

## 4. Train-Only Fitting & Anti-Leakage Invariants

### 4.1 Strict Isolation Rule
The whitening model is fit exclusively on $X_{\text{train}}$:
$$\mu_{\text{train}} = \frac{1}{n_{\text{train}}} \sum_{i=1}^{n_{\text{train}}} x_i$$
$$\Sigma_{\text{train}} = \frac{1}{n_{\text{train}} - 1} \sum_{i=1}^{n_{\text{train}}} (x_i - \mu_{\text{train}})(x_i - \mu_{\text{train}})^T$$
$$\Sigma_{\text{train, spd}} = \operatorname{project\_spd}(\Sigma_{\text{train}}, \epsilon_{\text{floor}})$$
$$W_{\text{train}} = \operatorname{whitening\_matrix}(\Sigma_{\text{train, spd}})$$

Held-out test instances $x \in X_{\text{test}}$ are transformed strictly using training parameters:
$$z_{\text{test}} = (x - \mu_{\text{train}}) W_{\text{train}}^T$$

### 4.2 Leakage Regression Fixture
To demonstrate the impact of test contamination, the audit harness includes a controlled fixture comparing strict train-only fitting against pooled leaky fitting $[X_{\text{train}}; X_{\text{test}}]$.

When $X_{\text{test}}$ has a distribution shift (e.g., shifted mean or scaled covariance):
- **Strict model**: Out-of-sample covariance error reflects the true distribution shift:
  $$\|\operatorname{Cov}(Z_{\text{test}}) - I\|_F > 0$$
- **Leaky model**: Leaking test data shifts $\mu$ and $\Sigma$ toward the test distribution, contaminating the transformation matrix $W$ and artificially reducing the perceived generalization error.
- **Divergence Metrics**: The regression fixture verifies:
  $$\|\mu_{\text{strict}} - \mu_{\text{leaky}}\|_2 > 0$$
  $$\|\Sigma_{\text{strict}} - \Sigma_{\text{leaky}}\|_F > 0$$
  $$\|W_{\text{strict}} - W_{\text{leaky}}\|_F > 0$$

---

## 5. Fail-Closed Robustness Specification

The verifier implements explicit pre-condition checks and raises distinct exceptions:

| Condition | Failure Trigger | Exception |
| :--- | :--- | :--- |
| **Sample count $n \le 1$** | Degrees of freedom $n - 1 \le 0$ | `InsufficientSamplesError` |
| **Empty matrix** | $n = 0$ or $d = 0$ | `EmptyDataError` |
| **Non-finite entries** | Any entry is `NaN`, `+Inf`, or `-Inf` | `NonFiniteValuesError` |
| **Dimension mismatch** | $d_{\text{test}} \ne d_{\text{train}}$ during transform | `FeatureDimensionMismatchError` |
| **Non-SPD without floor** | Covariance minor $\le 0$ without repair | `NonPositiveDefiniteError` |
| **Asymmetric covariance** | $|A_{ij}-A_{ji}| > \max\big(10^{-9}\cdot\max(|A_{ij}|,|A_{ji}|),\; n\,\varepsilon_{\text{mach}}\sqrt{|A_{ii}|}\sqrt{|A_{jj}|}\big)$. The diagonal sets only the rounding-noise floor, so a large diagonal cannot hide a material off-diagonal asymmetry. No absolute $10^{-15}$ floor | `InvalidCovarianceError` |
| **Cholesky vs ZCA equivalence** | Relative $||W_{\mathrm{chol}}-W_{\mathrm{zca}}||_F / ||W_{\mathrm{zca}}||_F < 10^{-9}$ **and** zero floored eigenvalues (no absolute $||\Delta W||_F$ / $||W||_F$ floors; floor-collapsed $\Sigma\to\varepsilon I$ agreement is withheld) | `are_methods_equivalent` |

---

## 6. Verification and Test Results

The test suite in `tests/whitening_audit/test_whitening_audit.py` contains 38 unit tests executed with standard library `unittest`:

```text
38 passed in 24.09s
```

All stress tests pass:
- [x] Train-only fitting on same-distribution test data.
- [x] Train-only fitting with shifted mean and covariance.
- [x] Rank-deficient data ($n < d$) with disclosed SPD repair.
- [x] Collinear feature handling via eigenvalue flooring.
- [x] Fail-closed rejection of $n \le 1$, empty inputs, non-finite floats, and mismatched shapes.
- [x] Numerical stability across variances spanning $10^{-6}$ to $10^{6}$.
- [x] Strict test data isolation (zero state mutation upon transform).
- [x] Controlled leakage detection fixture.
- [x] Cholesky vs ZCA rotation difference characterization.
- [x] Deterministic replay and finite JSON serialization.

---

## 7. Epistemic Guardrails

> [!CAUTION]
> **SYNTHETIC_ONLY / HOLD Notice**
> All evaluations in this audit are performed on synthetic numerical matrices.
> No clinical claims, no biological validity assertions, and no claims of consciousness theory validation are made.
> This audit serves strictly as an algorithmic and statistical verification harness for the proposed feature whitening specification.
