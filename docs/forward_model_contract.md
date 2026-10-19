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

### 3.2 Closed-Form and Multi-Shell Analytic Spherical Forward Engine

For concentric spherical conductors with $K$ layers (radii $r_1 < r_2 < \dots < r_K = R_{\text{scalp}}$ and conductivities $\sigma_1, \dots, \sigma_K$), the surface potential $V(\mathbf{r}_e)$ at surface position $\mathbf{r}_e$ ($\|\mathbf{r}_e\| = R$) due to a current dipole $\mathbf{q}$ at position $\mathbf{r}_s$ ($r_s = \|\mathbf{r}_s\| < r_1$) is evaluated via spherical harmonics and radial transfer matrices:

1. **Center Dipole Limit** ($r_s \to 0$):
   $$V(\mathbf{r}_e) = c_1 \frac{3 (\mathbf{q} \cdot \mathbf{r}_e)}{4 \pi \sigma_K R_K^3}$$
   where $c_1 = 1.0$ for a single homogeneous sphere, and for concentric multi-shell conductors, $c_1$ is evaluated directly from the interface transfer matrix.

2. **General Dipole Position** ($0 < r_s < r_1$):
   Let $a = r_s / R_K$, $\cos \theta = \hat{\mathbf{r}}_s \cdot \hat{\mathbf{r}}_e$, $q_r = \mathbf{q} \cdot \hat{\mathbf{r}}_s$, and $\mathbf{q}_t = \mathbf{q} - q_r \hat{\mathbf{r}}_s$:
   $$V(\mathbf{r}_e) = \frac{1}{4 \pi \sigma_K R_K^2} \sum_{n=1}^\infty c_n a^{n-1} \left[ \frac{2n+1}{n} P_n(\cos \theta) q_r - \frac{2n+1}{n(n+1)} P'_n(\cos \theta) (\mathbf{q} \cdot \hat{\mathbf{r}}_e - \cos \theta q_r) \right]$$

3. **Multi-Shell Radial Boundary-Value Transfer Matrix**:
   To ensure every declared layer's radius $r_k$ and conductivity $\sigma_k$ exerts a physical effect on the scalp potential (preventing silent layer dropping), the degree-$n$ transfer matrix across shell interface $k$ is computed using scaled coordinates:
   $$T_{k, n} = \frac{1}{2n+1} \begin{pmatrix} (n+1) + n \frac{\sigma_k}{\sigma_{k+1}} & (n+1)\left(1 - \frac{\sigma_k}{\sigma_{k+1}}\right) \left(\frac{R_K}{r_k}\right)^{2n+1} \\ n \left(1 - \frac{\sigma_k}{\sigma_{k+1}}\right) \left(\frac{r_k}{R_K}\right)^{2n+1} & n + (n+1) \frac{\sigma_k}{\sigma_{k+1}} \end{pmatrix}$$
   The product matrix $M_n = T_{K-1, n} \cdots T_{1, n}$ directly determines $c_n$:
   $$c_n = \frac{n}{n+1} \frac{\sigma_K}{\sigma_1} \left( m_{11} \frac{(n+1) m_{22} - n m_{12}}{n m_{11} - (n+1) m_{21}} + m_{12} \right)$$
   - When $K=1$ (`SPHERICAL_1SHELL`), $c_n \equiv 1.0$ identically.
   - When $K=3$ (`SPHERICAL_3SHELL`), altering skull conductivity $\sigma_2$ or brain radius $r_1$ alters $c_n$ and surface potential physically.

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
| **Coordinate Frame** | HEAD / MNI | `FIFFV_COORD_HEAD` (4) | Mismatched sensor/source frames require validated 4x4 transform | Raises `CoordinateFrameMismatchError` |

#### Coordinate Transformation Contract
When sensors and sources reside in differing coordinate frames (e.g. sensors in `HEAD` and sources in `MNI`), the contract requires an explicit $4 \times 4$ homogeneous affine transformation matrix $T$:
$$\mathbf{r}_{\text{sensor}} = R \mathbf{r}_{\text{source}} + \mathbf{t}$$
The bottom row must equal `[0, 0, 0, 1]`, and all matrix elements must be finite. Unaligned cross-frame forward models fail closed immediately.

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

### 3.5 Referencing Policies: Average vs Unipolar Channel Reference

Scalp EEG potentials are non-invasive potential differences relative to a reference electrode. The contract enforces unambiguous, mutually exclusive referencing policies:

1. **Average Reference Projection (`apply_avg_ref=True`, `reference_channel=None`)**:
   $$P_{\text{avg}} = I_M - \frac{1}{M} \mathbf{1}_M \mathbf{1}_M^T, \quad L_{\text{avg}} = P_{\text{avg}} L$$
   - Zero-sum column invariant: $\sum_{i=1}^M (L_{\text{avg}})_{i, j} = 0 \quad \forall j$.
   - Idempotence: $P_{\text{avg}}^2 = P_{\text{avg}}$.
   - Rank deduction: $\mathrm{rank}(L_{\text{avg}}) \le M - 1$.

2. **Unipolar Channel Reference (`reference_channel='Cz'`, `apply_avg_ref=False`)**:
   $$L_{\text{ref}, i, j} = L_{i, j} - L_{\text{ref\_idx}, j}$$
   - Reference channel row is identically zero: $\|L_{\text{ref\_idx}, :}\|_\infty \le 10^{-14}$.
   - Simulated potential at reference channel is identically zero: $V(\text{ref\_channel}) \equiv 0$.
   - Declared reference channel must be present in `channel_names`; missing reference channels fail closed.

3. **Conflicting Referencing Policy Rejection**:
   Requesting both `apply_avg_ref=True` and `reference_channel` simultaneously fails closed immediately with `ForwardModelContractError`.

---

### 3.6 Uncertainty Semantics and Guardrails

> [!CAUTION]
> **No Implied Calibration or False Zero-Error Claims**
> Synthetic forward models carry unquantified physical errors (idealized spherical geometry, homogeneous tissue assumption, simplified skull resistivity). Unless uncertainty bounds are explicitly quantified via stochastic perturbations or empirical error models, uncertainty status MUST remain `UNAVAILABLE`.
> Defaulting uncertainty to zero or omitting uncertainty metadata while claiming calibrated confidence is strictly prohibited.

The contract reports structured uncertainty metadata:
- `uncertainty.status`: `UncertaintyStatus.UNAVAILABLE`
- `uncertainty.relative_field_uncertainty`: `None`
- `uncertainty.disclaimer`: Explicit warning that forward uncertainty is unquantified.

---

## 4. Numerical Conditioning and Quality Diagnostics

The contract computes a comprehensive suite of numerical diagnostics via Gram matrix eigendecomposition ($C = L L^T \in \mathbb{R}^{M \times M}$):

- **Singular Value Spectrum**: $\sigma_i = \sqrt{\max(0, \lambda_i(L L^T))}$, sorted in descending order.
- **Numerical Rank**: Number of singular values exceeding tolerance $\tau = \max(M, K) \cdot 10^{-7} \cdot \sigma_1$.
- **Condition Number**: $\kappa(L) = \sigma_1 / \sigma_r$, where $r = \mathrm{rank}(L)$. The trivial zero singular value from average or channel referencing is excluded.
- **Channel Frobenius Norms**: $\|L_{i, :}\|_2$ for each channel $i$.
- **Crosstalk / Collinearity Index**: Mean pairwise correlation of normalized leadfield columns across spatial sources.
- **Well-Conditioned Flag**: Set to `True` if $\kappa(L) < 10^6$ and active channel norm exceeds $10^{-12}$.

---

## 5. MNE Forward Solution Auditor

Function `audit_mne_forward_solution(fwd, info=None, expected_conductor=None)` provides an automated audit protocol for MNE Forward solutions generated in the pipeline:

```python
from dual_engine.forward_model_contract import audit_mne_forward_solution, ContractStatus

# Audit an existing MNE Forward object
contract_result = audit_mne_forward_solution(fwd, info=raw.info)

assert contract_result.is_valid
assert contract_result.status == ContractStatus.ENGINEERING_ONLY
assert contract_result.diagnostics.numerical_rank == raw.info["nchan"] - 1
assert contract_result.uncertainty.status.value == "UNAVAILABLE"
```

### Audit Checklist:
- [x] **Coordinate Frame**: Validates `fwd['coord_frame'] == 4` (`FIFFV_COORD_HEAD`).
- [x] **Units**: Verifies source vertex positions `fwd['src'][k]['rr']` have norm $\le 0.15\text{ m}$.
- [x] **Channel Order**: Verifies leadfield `row_names` match `info['ch_names']` without permutation.
- [x] **Leadfield Dimensions**: Checks $(M, 3N)$ or $(M, N)$ dimensions against `nsource`.
- [x] **Reference Projection**: Verifies reference column sums $\approx 0$.
- [x] **Uncertainty & Status**: Discloses `UNAVAILABLE` uncertainty and marks result `ENGINEERING_ONLY`.

---

## 6. Canonical Synthetic Fixtures & Independent Numerical Oracles

The module provides zero-dependency, deterministic synthetic fixtures and independent numerical oracles:

1. `make_standard_1020_synthetic_sensors(radius_m=0.090)`:
   Generates 19 standard 10-20 spherical electrodes with exact 3D coordinates on a $9.0\text{ cm}$ sphere.
2. `make_synthetic_source_grid(n_sources=16, max_radius_m=0.065, is_fixed_orientation=False)`:
   Generates a deterministic Fibonacci spherical lattice of dipole source locations bounded strictly inside the brain shell ($r \le 6.5\text{ cm} < 8.0\text{ cm}$).
3. `build_synthetic_forward_contract(...)`:
   High-level factory that synthesizes sensors, sources, concentric multi-shell conductor, leadfield matrix, referencing, diagnostics, and returns `ForwardModelContractResult`.
4. **Independent Numerical Oracles**:
   - **Closed-Form Center Dipole Limit**: Validated against $V = c_1 \frac{3(\mathbf{q} \cdot \mathbf{r}_e)}{4 \pi \sigma R^3}$ with zero series truncation ($\Delta < 10^{-15}\text{ V}$).
   - **Frank (1952) On-Axis Benchmark**: Validated against pre-computed analytic benchmark $V = 1.465475850798419 \times 10^{-7}\text{ V}$ ($\Delta < 10^{-14}\text{ V}$).

---

## 7. Verification Results

The test suite in `tests/forward_model_contract/test_forward_model_contract.py` executes 56 unit tests validating:

- Rejection of millimeter units in conductor, sensors, and sources.
- Rejection of unknown coordinate frames and unaligned cross-frame configurations without transform.
- Affine coordinate transformation of source spaces into sensor frames.
- Rejection of non-monotonic, non-positive, or unphysical conductor layers.
- Multi-shell inner layer sensitivity: verified physical effect of skull conductivity $\sigma_{\text{skull}}$ and brain radius $r_{\text{brain}}$.
- Rejection of out-of-bounds sources.
- Non-unit fixed orientation vector rejection.
- Exact dipole potential linearity and superposition ($\Delta < 10^{-18}\text{ V}$).
- Dimensional consistency for free $(19, 48)$ and fixed $(19, 16)$ leadfield matrices.
- Average reference column zero-sum invariant ($\Delta < 10^{-11}$) and idempotency.
- Unipolar channel referencing: verified zero row, zero simulated reference potential, and conflicting policy rejection.
- Explicit `UNAVAILABLE` uncertainty semantics and JSON serialization.
- Independent numerical oracle and Frank (1952) closed-form benchmark validation.
- Finite, bounded SVD diagnostics and condition numbers.
- Deterministic replay bit-for-bit.
- Strict non-promotional guardrails and disclaimer presence.
- MNE forward auditor mock execution and validation.
