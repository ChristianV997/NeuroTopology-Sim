# Synthetic EEG Forward-Model Contract and Verification Specification

## 1. Executive Summary

This document specifies the synthetic EEG forward-model contract and verification fixture implemented in `dual_engine/forward_model_contract.py` for `NeuroTopology-Sim`.

The contract defines a rigorous, type-safe interface around synthetic forward solutions used in the dual-engine pipeline (`dual_engine/source_space_tda_pipeline.py` and `dual_engine/data_adapters.py`). It enforces strict physical units, coordinate frame alignment, conductor geometry invariants, reference projection invariants, conditioning diagnostics, and non-promotional guardrails.

---

## 2. Guardrails and Epistemic Scope

> [!IMPORTANT]
> **Strict Engineering & Synthetic Scope**
> All forward solutions generated or audited by this module are classified as `SYNTHETIC_ONLY` or `ENGINEERING_ONLY`. They are synthetic approximations designed exclusively for:
> - Verification of source-space pipeline execution and data structures.
> - Automated testing of coordinate-frame alignment and dimensional invariants.
> - Numerical conditioning diagnostics and regression safety fixtures.

### Explicit Prohibitions and Guardrails

1. **No Anatomical Promotion**: A spherical head model (1-shell or 3-shell concentric spheres) is an idealized mathematical surrogate. It is **not** an individual anatomical reconstruction and cannot replace individual MRI segmentation, Boundary Element Models (BEM), or Finite Element Models (FEM).
2. **No Biological Truth Claims**: Synthetic forward solutions and resulting inverse projections (e.g., eLORETA) do not constitute biological ground truth, direct cortical recordings, or causal neurophysiological evidence.
3. **No Consciousness Claims**: No topology, phase winding, or source-space metric computed over synthetic forward models validates or proves theories of consciousness.
4. **No Clinical Claims**: Outputs from this forward contract are unsuitable for clinical diagnostics, presurgical localization, or treatment planning.
5. **Fail-Closed Geometry**: Ambiguous units (e.g. coordinates in millimeters instead of meters), mismatched coordinate frames, permuted channel lists, or sources placed outside the brain conductor shell fail closed immediately with descriptive exceptions.

---

## 3. Mathematical and Physical Specification

### 3.1 Conductor Geometry

The canonical synthetic forward engine implements an analytic 3-shell concentric spherical conductor model:

| Layer | Compartment | Default Radius ($r$) | Default Conductivity ($\sigma$) | Range Invariant |
| :--- | :--- | :--- | :--- | :--- |
| Layer 1 | Brain | $0.080\text{ m}$ ($8.0\text{ cm}$) | $0.33\text{ S/m}$ | $0 < r_1 < r_2$ |
| Layer 2 | Skull | $0.085\text{ m}$ ($8.5\text{ cm}$) | $0.0042\text{ S/m}$ (1:80 ratio) | $r_1 < r_2 < r_3$ |
| Layer 3 | Scalp | $0.090\text{ m}$ ($9.0\text{ cm}$) | $0.33\text{ S/m}$ | $0.04\text{ m} \le r_3 \le 0.20\text{ m}$ |

#### Invariants:
- **Monotonicity**: $0 < r_{\text{brain}} < r_{\text{skull}} < r_{\text{scalp}}$.
- **Positive Conductivity**: $\sigma_i > 0$ for all layers $i \in \{1, 2, 3\}$.
- **Source Containment**: All dipole sources $\mathbf{r}_s$ must lie strictly within the innermost shell:
  $$\|\mathbf{r}_s - \mathbf{r}_0\| < r_{\text{brain}}$$
  Any source placed at or outside $r_{\text{brain}}$ raises `SourceOutOfBoundsError`.

---

### 3.2 Closed-Form Analytic Dipole Potential

For a homogeneous sphere of radius $R$ and conductivity $\sigma$, the electric potential $V(\mathbf{r}_e)$ at surface position $\mathbf{r}_e$ ($\|\mathbf{r}_e\| = R$) due to a current dipole $\mathbf{q}$ at position $\mathbf{r}_s$ ($r_s = \|\mathbf{r}_s\| < R$) is evaluated via the Legendre polynomial series expansion:

1. **Center Dipole Limit** ($r_s \to 0$):
   $$V(\mathbf{r}_e) = \frac{3 (\mathbf{q} \cdot \mathbf{r}_e)}{4 \pi \sigma R^3}$$

2. **General Dipole Position** ($0 < r_s < R$):
   Let $a = r_s / R$, $\cos \theta = \hat{\mathbf{r}}_s \cdot \hat{\mathbf{r}}_e$, $q_r = \mathbf{q} \cdot \hat{\mathbf{r}}_s$, and $\mathbf{q}_t = \mathbf{q} - q_r \hat{\mathbf{r}}_s$:
   $$V(\mathbf{r}_e) = \frac{1}{4 \pi \sigma R^2} \left[ \sum_{n=1}^\infty \frac{2n+1}{n} a^{n-1} P_n(\cos \theta) q_r - \sum_{n=1}^\infty \frac{2n+1}{n(n+1)} a^{n-1} P'_n(\cos \theta) (\mathbf{q} \cdot \hat{\mathbf{r}}_e - \cos \theta q_r) \right]$$

3. **3-Shell Berg-Scherg Approximation**:
   In concentric 3-shell spheres, the scalp potential is represented as a weighted sum of equivalent homogeneous spheres:
   $$V_{3\text{-shell}}(\mathbf{r}_e, \mathbf{r}_s, \mathbf{q}) = \sum_{k=1}^3 \lambda_k V_{\text{hom}}(\mathbf{r}_e, \mu_k \mathbf{r}_s, \mathbf{q}; R_{\text{scalp}}, \sigma_{\text{scalp}})$$
   where $\boldsymbol{\lambda} = (0.08, 0.36, 0.56)$ and $\boldsymbol{\mu} = (0.63, 0.88, 0.99)$ for standard head dimensions.

4. **Linear Superposition Invariant**:
   For any dipole moments $\mathbf{q}_1, \mathbf{q}_2$:
   $$V(\mathbf{r}_e; \mathbf{q}_1 + \mathbf{q}_2) = V(\mathbf{r}_e; \mathbf{q}_1) + V(\mathbf{r}_e; \mathbf{q}_2)$$
   Verified numerically to machine precision ($\Delta < 10^{-18}\text{ V}$).

---

### 3.3 Coordinate Frame and Unit Standards

The contract strictly enforces standard SI units and MNE canonical coordinate frames:

| Dimension | Physical Unit | Symbol | Enforcement Rule | Violation Action |
| :--- | :--- | :--- | :--- | :--- |
| **Length / Position** | Meter | $\text{m}$ | Any norm $> 1.0\text{ m}$ flags millimeter input | Raises `CoordinateUnitMismatchError` |
| **Potential** | Volt | $\text{V}$ | Scalp potentials simulated in Volts ($\mu\text{V} = 10^{-6}\text{V}$) | Dimension check |
| **Dipole Moment** | Ampere-meter | $\text{A}\cdot\text{m}$ | Standard current dipole moment | Dimension check |
| **Conductivity** | Siemens per meter | $\text{S/m}$ | Strict positive values ($0.33, 0.0042$) | Raises `ConductorGeometryError` |
| **Angle** | Radian | $\text{rad}$ | Converted from degrees internally | Validated |
| **Coordinate Frame** | HEAD Frame | `FIFFV_COORD_HEAD` (4) | X: LPA $\to$ RPA, Y: Nasion, Z: Up/Vertex | Raises `CoordinateFrameMismatchError` |

---

### 3.4 Leadfield Dimensions and Orientation Modes

The leadfield matrix $L$ maps dipole source activities $\mathbf{q}$ to scalp sensor potentials $\mathbf{v}$:
$$\mathbf{v} = L \mathbf{q}$$

The dimensions of $L$ are strictly constrained by the orientation mode:

1. **Free Orientation (`OrientationType.FREE`)**:
   - Each source dipole location has 3 orthogonal degrees of freedom: $(q_x, q_y, q_z)$.
   - Dimensions: $M \times 3N$, where $M$ is the number of channels and $N$ is the number of sources.
   - Column index mapping: source $j$ occupies columns $3j, 3j+1, 3j+2$.

2. **Fixed Orientation (`OrientationType.FIXED`)**:
   - Each source dipole is constrained to a fixed unit vector $\mathbf{u}_j$ ($\|\mathbf{u}_j\| = 1.0 \pm 10^{-4}$), typically normal to the cortical surface or radial.
   - Dimensions: $M \times N$.
   - Column index mapping: source $j$ occupies column $j$.

---

### 3.5 Average Reference Projection Invariants

Scalp EEG potentials are non-invasive potential differences relative to a reference. In source modeling, an average reference projection operator $P_{\text{avg}}$ is applied to eliminate reference bias:

$$P_{\text{avg}} = I_M - \frac{1}{M} \mathbf{1}_M \mathbf{1}_M^T$$
$$L_{\text{avg}} = P_{\text{avg}} L$$

#### Mandatory Mathematical Invariants:
1. **Zero-Sum Column Invariant**:
   $$\sum_{i=1}^M (L_{\text{avg}})_{i, j} = 0 \quad \forall j \in \{0, \dots, K-1\}$$
   Verified with tolerance $\epsilon \le 10^{-10}$.
2. **Idempotence**:
   $$P_{\text{avg}}^2 = P_{\text{avg}}$$
3. **Symmetry**:
   $$P_{\text{avg}}^T = P_{\text{avg}}$$
4. **Rank Deduction**:
   Because $\mathbf{1}_M$ is in the null space of $P_{\text{avg}}$, the numerical rank of $L_{\text{avg}}$ is reduced by at least 1:
   $$\mathrm{rank}(L_{\text{avg}}) \le M - 1$$

---

## 4. Numerical Conditioning and Quality Diagnostics

The contract computes a comprehensive suite of numerical diagnostics via Gram matrix eigendecomposition ($C = L L^T \in \mathbb{R}^{M \times M}$):

- **Singular Value Spectrum**: $\sigma_i = \sqrt{\max(0, \lambda_i(L L^T))}$, sorted in descending order.
- **Numerical Rank**: Number of singular values exceeding tolerance $\tau = \max(M, K) \cdot 10^{-7} \cdot \sigma_1$.
- **Condition Number**: $\kappa(L) = \sigma_1 / \sigma_r$, where $r = \mathrm{rank}(L)$. In average-reference space, the trivial zero singular value is excluded.
- **Channel Frobenius Norms**: $\|L_{i, :}\|_2$ for each channel $i$. Flags disconnected or flat channels.
- **Crosstalk / Collinearity Index**: Mean pairwise correlation of normalized leadfield columns across spatial sources.
- **Well-Conditioned Flag**: Set to `True` if $\kappa(L) < 10^6$ and minimum channel norm exceeds $10^{-12}$.

---

## 5. MNE Forward Solution Auditor

Function `audit_mne_forward_solution(fwd, info=None, expected_conductor=None)` provides an automated audit protocol for MNE Forward solutions generated in the pipeline:

```python
from dual_engine.forward_model_contract import audit_mne_forward_solution

# Audit an existing MNE Forward object
contract_result = audit_mne_forward_solution(fwd, info=raw.info)

assert contract_result.is_valid
assert contract_result.status == ContractStatus.ENGINEERING_ONLY
assert contract_result.diagnostics.numerical_rank == raw.info["nchan"] - 1
```

### Audit Checklist:
- [x] **Coordinate Frame**: Validates `fwd['coord_frame'] == 4` (`FIFFV_COORD_HEAD`).
- [x] **Units**: Verifies source vertex positions `fwd['src'][k]['rr']` have norm $\le 0.15\text{ m}$.
- [x] **Channel Order**: Verifies leadfield `row_names` match `info['ch_names']` without permutation.
- [x] **Leadfield Dimensions**: Checks $(M, 3N)$ or $(M, N)$ dimensions against `nsource`.
- [x] **Reference Projection**: Verifies average reference column sums $\approx 0$.
- [x] **Metadata & Status**: Marks result `ENGINEERING_ONLY` with full disclaimer.

---

## 6. Canonical Synthetic Fixtures

The module provides zero-dependency, deterministic synthetic fixtures:

1. `make_standard_1020_synthetic_sensors(radius_m=0.090)`:
   Generates 19 standard 10-20 spherical electrodes (Fp1, Fp2, F7, F3, Fz, F4, F8, T7, C3, Cz, C4, T8, P7, P3, Pz, P4, P8, O1, O2) with exact 3D coordinates on a $9.0\text{ cm}$ sphere.
2. `make_synthetic_source_grid(n_sources=16, max_radius_m=0.065, is_fixed_orientation=False)`:
   Generates a deterministic Fibonacci spherical lattice of dipole source locations bounded strictly inside the brain shell ($r \le 6.5\text{ cm} < 8.0\text{ cm}$).
3. `build_synthetic_forward_contract(...)`:
   High-level factory that synthesizes sensors, sources, concentric 3-shell conductor, leadfield matrix, average reference projection, diagnostics, and returns `ForwardModelContractResult`.

---

## 7. Verification Results

The test suite in `tests/forward_model_contract/test_forward_model_contract.py` executes 27 unit tests validating:

- Rejection of millimeter units in conductor, sensors, and sources.
- Rejection of unknown coordinate frames.
- Rejection of non-monotonic or unphysical conductor layers.
- Rejection of out-of-bounds sources.
- Non-unit fixed orientation vector rejection.
- Exact dipole potential linearity and superposition ($\Delta < 10^{-18}\text{ V}$).
- Dimensional consistency for free $(19, 48)$ and fixed $(19, 16)$ leadfield matrices.
- Average reference column zero-sum invariant ($\Delta < 10^{-11}$) and idempotency.
- Rank deduction in average reference space ($18 = 19 - 1$).
- Channel ordering and permutation consistency.
- Finite, bounded SVD diagnostics and condition numbers.
- Scalp potential simulation ($V = L \mathbf{q}$).
- Deterministic replay bit-for-bit.
- Strict non-promotional guardrails and disclaimer presence.
- MNE forward auditor mock execution and validation.
- Finite JSON serialization without `NaN` or `Inf`.
