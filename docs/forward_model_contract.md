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
5. **Fail-Closed Geometry and Numerics**: Ambiguous units (e.g. coordinates in millimeters instead of meters), mismatched coordinate frames, permuted channel lists, sources placed outside the brain conductor shell, electrodes that are not on the outer conductor surface, non-finite radii/conductivities/coordinates/moments, numeric strings or `None` in numeric fields, a non-member `model_type` or `coordinate_frame`, a non-bool `is_fixed_orientation`, ragged or non-finite leadfield matrices, invalid fixed orientations (before or after a coordinate transform), and any computation whose result would not be finite fail closed immediately with `ForwardModelContractError` subclasses. They never surface as a bare `AttributeError`, `TypeError`, `IndexError`, `OverflowError`, or a silent `NaN`, `inf`, or `0.0`.
6. **Synthetic Contract ≠ Validated Physics / Measured EEG**: Analytic concentric-sphere leadfields and closed-form oracles in this module are **unit-verification fixtures**. They are not a validated physical head model, not a claim of agreement with measured scalp EEG, and not evidence that an inverse solution recovers biological sources. Synthetic fixtures and analytic oracles are not measured EEG, validated physics, or scientific evidence.

### Boundary Versus Neighboring PRs (Do Not Duplicate)

| Surface | Owner | Role | Not this contract |
| :--- | :--- | :--- | :--- |
| `dual_engine/forward_model_contract.py` (this PR, #388) | Forward-model contract | Synthetic **source → sensor** leadfield / potential under concentric spheres; SI geometry; referencing; diagnostics | Not a sensor-space Laplacian / CSD operator |
| `neurotopology_sim/experimental/preprocessing/spherical_csd.py` (#414) | Spherical CSD production | Sensor-space spherical-spline **CSD** (`compute_spherical_csd_transform` / `apply_spherical_csd`) over electrode positions | Not a volume conductor forward model; does not emit leadfields |
| `tools/mne_csd_reference_audit/*` (#402) | MNE CSD reference audit | Independent NumPy transcription / pin / KKT / Legendre parity vs pinned MNE CSD | Not a forward solver; does not replace or audit #388 leadfields |

Interface comparison (documentation only; #414/#402 code is out of scope here):
- **#388 inputs**: conductor shells `(radii_m, sigmas_sm)`, source positions/orientations, sensor montage → **leadfield** \(L\) and \(V = Lq\) in volts.
- **#414 inputs**: electrode positions (+ CSD config) and sensor time series → **CSD transform** / spatially filtered voltages (V/m² scaling under SI assumptions).
- **#402 inputs**: the same CSD mathematical surface as the MNE pin, for audit/parity—not dual-engine forward construction.

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
  Any source placed at or outside $r_{\text{brain}}$ raises `SourceOutOfBoundsError`. The public potential functions enforce this themselves (the multi-shell series is derived for a source in the innermost shell), not only `SourceSpace.validate`.
- **Surface Electrodes**: The engines return the *surface* potential, which depends only on the electrode direction. Every electrode must therefore satisfy $\bigl|\,\|\mathbf{r}_e - \mathbf{r}_0\| - R\,\bigr| \le 1\,\mu\text{m}$ ($R$ the outer radius, $\mathbf{r}_0$ the conductor origin, `ELECTRODE_SURFACE_TOLERANCE_M`). Electrodes inside or outside the head raise `ConductorGeometryError`; a distance above $1.0\text{ m}$ raises `CoordinateUnitMismatchError`. `build_synthetic_forward_contract` applies the same rule to a whole montage relative to `conductor.origin_m`. `SensorGeometry.validate()` alone is origin-agnostic and only bounds the absolute distance to a plausible head size.

---

### 3.2 Closed-Form and Multi-Shell Analytic Spherical Forward Engine

For concentric spherical conductors with $K$ layers (radii $r_1 < r_2 < \dots < r_K = R_{\text{scalp}}$ and conductivities $\sigma_1, \dots, \sigma_K$), the surface potential $V(\mathbf{r}_e)$ at surface position $\mathbf{r}_e$ ($\|\mathbf{r}_e\| = R$) due to a current dipole $\mathbf{q}$ at position $\mathbf{r}_s$ ($r_s = \|\mathbf{r}_s\| < r_1$) is evaluated via spherical harmonics and radial transfer matrices:

1. **Center Dipole Limit** ($r_s \to 0$):
   $$V(\mathbf{r}_e) = c_1 \frac{3 (\mathbf{q} \cdot \mathbf{r}_e)}{4 \pi \sigma_K R_K^3}$$
   where $c_1 = 1.0$ for a single homogeneous sphere, and for concentric multi-shell conductors, $c_1$ is evaluated directly from the interface transfer matrix.

2. **General Dipole Position** ($0 < r_s < r_1$):
   Let $a = r_s / R_K$, $\cos \theta = \hat{\mathbf{r}}_s \cdot \hat{\mathbf{r}}_e$, $q_r = \mathbf{q} \cdot \hat{\mathbf{r}}_s$, and $\mathbf{q}_t = \mathbf{q} - q_r \hat{\mathbf{r}}_s$:
   $$V(\mathbf{r}_e) = \frac{1}{4 \pi \sigma_K R_K^2} \sum_{n=1}^\infty c_n a^{n-1} \left[ \frac{2n+1}{n} P_n(\cos \theta) q_r - \frac{2n+1}{n(n+1)} P'_n(\cos \theta) (\mathbf{q} \cdot \hat{\mathbf{r}}_e - \cos \theta q_r) \right]$$

3. **Multi-Shell Layer Coefficient $c_n$ (stable inward recursion)**:
   In layer $j$ the order-$n$ potential is $B_j r^{-(n+1)}\bigl(1 + v\,(r/r_j)^{2n+1}\bigr)$ with $v = A_j r_j^{2n+1}/B_j$. The scalp is current-free, so $v_K = (n+1)/n$ at $R_K$. Continuity of the potential and of $\sigma\,\partial V/\partial r$ at interface $j$, with $h(v) = \dfrac{n v - (n+1)}{v + 1}$, gives
   $$v_j^{\text{in}} = v_{j+1}\left(\frac{r_j}{r_{j+1}}\right)^{2n+1}, \qquad h(v_j) = \frac{\sigma_{j+1}}{\sigma_j}\,h(v_j^{\text{in}}), \qquad v_j = \frac{n+1+h(v_j)}{n-h(v_j)}, \qquad c_n = \frac{\sigma_K}{\sigma_1}\prod_{j=1}^{K-1}\frac{v_j + 1}{v_j^{\text{in}} + 1}.$$
   The recursion runs inward from the scalp. Every factor applied is a power of $r_j / r_{j+1} < 1$ and every $v + 1$ is positive, so no intermediate quantity grows.
   - When $K=1$ (`SPHERICAL_1SHELL`), $c_n \equiv 1.0$ identically, and with equal conductivities every $c_n = 1$ exactly.
   - This equals the classic outward transfer-matrix product $M_n = T_{K-1,n}\cdots T_{1,n}$ with $c_n = \frac{n}{n+1}\frac{\sigma_K}{\sigma_1}\bigl(m_{11}A_1 + m_{12}\bigr)$, $A_1 = \frac{(n+1)m_{22} - n m_{12}}{n m_{11} - (n+1) m_{21}}$. The tests check the float implementation against that product evaluated in **exact rational arithmetic** (agreement better than $10^{-12}$ for brain radii from $1\text{ mm}$ to $8\text{ cm}$ and for conductivity ratios of $10^{4}$ in either direction).
   - Why not the outward product: it multiplies powers of $(R_K/r_1)^{2n+1}$ and cancels terms of that size. For $c_n$ at $n \le 60$ its worst relative error was $1\times10^{-7}$ for the default $8\text{ cm}$ brain, but $1.5$ at $7\text{ cm}$ and $4\times10^{16}$ at $5\text{ cm}$. For a $1\,\mu\text{m}$ brain it returned exactly $0.0$ for a centred $1\text{ A}\cdot\text{m}$ dipole, and for a $0.1\text{ mm}$ brain with the source at half its radius it returned about $3.5\times10^{9}\text{ V}$, where the correct value is about $28.6\text{ V}$. The recursion removes the cancellation.
   - Sensitivity: altering the skull conductivity $\sigma_2$ or brain radius $r_1$ changes $c_n$ and the computed surface potential. The tests assert this as a **sensitivity property of the implementation** (no layer is silently dropped); it is not evidence that the numbers match a real head.
   - Series length: both engines default to `DEFAULT_SERIES_TERMS = 60` terms, so a one-shell concentric model reproduces the homogeneous engine. The truncation error scales roughly as $(r_s/R_K)^{n_{\max}}$: negligible for the default source grid ($r_s \le 6.5\text{ cm}$, about $10^{-9}$) but up to about $10^{-3}$ for a source just inside the default brain shell.

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
| **Electrode position** | Meter | $\text{m}$ | On the outer surface, measured from the conductor origin, within $1\,\mu\text{m}$ | Raises `ConductorGeometryError`; `CoordinateUnitMismatchError` above $1.0\text{ m}$ |
| **Numeric fields** | Real number | – | Finite `int`/`float` only: no `bool`, no numeric strings, no `None` | Raises the field's contract error (never `TypeError`) |
| **Computed potential** | Volt | $\text{V}$ | Must be finite; overflow is not returned as `inf`/`NaN` | Raises `ForwardModelContractError` |
| **Coordinate Frame** | `CoordinateFrame.HEAD` / `CoordinateFrame.MNI` | `FIFFV_COORD_HEAD` (4) | Member enum only. Plain strings are not coerced. Mismatched sensor/source frames require a validated 4x4 transform. `UNKNOWN` is rejected | Raises `CoordinateFrameMismatchError` |

#### Coordinate Transformation Contract
When sensors and sources reside in differing coordinate frames (e.g. sensors in `HEAD` and sources in `MNI`), the contract requires an explicit $4 \times 4$ homogeneous affine transformation matrix $T$:
$$\mathbf{r}_{\text{sensor}} = R \mathbf{r}_{\text{source}} + \mathbf{t}$$
The bottom row must equal `[0, 0, 0, 1]`, all matrix elements must be finite, and the $3 \times 3$ linear block must be non-singular ($|\det| \ge 10^{-12}$). Unaligned cross-frame forward models fail closed immediately.

Source positions and, for fixed-orientation sources, orientation vectors are validated **before** the transform (finite, unit norm within $10^{-4}$). A zero, non-finite, or non-unit orientation therefore raises `ForwardModelContractError` exactly as it does without a transform; it is never renormalised or replaced by an invented direction. After the transform, fixed orientations are renormalised to unit length (a rotation or scaling changes the length, not the direction) and re-validated. Orientation vectors of free-orientation sources are not used by the engine and are only transformed linearly.

---

### 3.4 Leadfield Dimensions and Orientation Modes

The leadfield matrix $L$ maps dipole source activities $\mathbf{q}$ to scalp sensor potentials $\mathbf{v}$:
$$\mathbf{v} = L \mathbf{q}$$

The dimensions of $L$ are strictly constrained by the orientation mode:

Every helper that takes a leadfield (`apply_average_reference`, `apply_channel_reference`, `verify_*_reference_invariant`, `compute_leadfield_diagnostics`) requires a non-empty, **rectangular**, finite matrix. A ragged or empty-row matrix raises `LeadfieldDimensionMismatchError` (it is never truncated silently and never surfaces as `IndexError`); a non-finite entry raises `ForwardModelContractError`. `apply_channel_reference` also requires one channel name per row.

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
   - Reference channel row is identically zero: $\|L_{\text{ref\_idx}, :}\|_\infty \le 10^{-12}$ (the tolerance used by `verify_channel_reference_invariant`).
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

### 3.7 Malformed-Argument and Resource Bounds

Public helpers fail closed with a `ForwardModelContractError` subclass (never a bare `TypeError`/`OverflowError`/`AttributeError`) for non-sequence matrices, channel names, or affine transforms, for non-finite, negative, or non-numeric comparison tolerances, and for a conductor that fails its own validation when it is used to bound a source space. Loop-driving inputs are capped: `n_max_terms <= MAX_SERIES_TERMS` (10,000) and synthetic grid `n_sources <= MAX_SYNTHETIC_SOURCES` (100,000). Leadfield diagnostics raise `ForwardModelContractError` when channel norms overflow double precision, rather than returning `inf`/`nan` metrics or an `OverflowError`. These are input-hygiene guarantees on synthetic fixtures; they say nothing about physical accuracy.

### 3.8 Enum domains on the validate / build path

`validate()` rejects a value that is not an instance of the field's enum or bool. A plain string is not coerced, even when it equals a member's value (`"head"`, `"spherical_3shell"`, `"free"`). Case and whitespace variants are the same kind of non-member. `build_synthetic_forward_contract` runs these checks before any `.value` access, so a bad label does not surface later as `AttributeError: 'str' object has no attribute 'value'`.

No production caller and no `from_dict` round-trip in this repository passes those strings. The MNE auditor's separate `coord_frame` check (integer `4`, the string `"head"`, or `CoordinateFrame.HEAD`) is unchanged.

| Field | What passes `validate()` | Existing rejection that still runs | Error |
| :--- | :--- | :--- | :--- |
| `ConductorModel.model_type` | `ConductorModelType.SPHERICAL_3SHELL` (`spherical_3shell`), `ConductorModelType.SPHERICAL_1SHELL` (`spherical_1shell`) | `ConductorModelType.ANATOMICAL_BEM` | `ConductorGeometryError`. The message names `model_type` and the accepted values `spherical_3shell, spherical_1shell`; it does not echo the rejected input. The anatomical member keeps the message that anatomical BEM is not supported. |
| `SensorGeometry.coordinate_frame` | `CoordinateFrame.HEAD` (`head`), `CoordinateFrame.MNI` (`mni`) | `CoordinateFrame.UNKNOWN` | `CoordinateFrameMismatchError`. The message names `sensor_geometry.coordinate_frame` and the accepted values `head, mni`; it does not echo the rejected input. The `UNKNOWN` member keeps the message that UNKNOWN is rejected and the frame must be HEAD or MNI. |
| `SourceSpace.coordinate_frame` | `CoordinateFrame.HEAD`, `CoordinateFrame.MNI` | `CoordinateFrame.UNKNOWN` | `CoordinateFrameMismatchError`, same rule, field name `source_space.coordinate_frame`. |
| `SourceSpace.is_fixed_orientation` | Built-in `True` (fixed, one column per source) or `False` (free, three columns per source) | — | `ForwardModelContractError`. Accepted values are `True, False`; `numpy.bool_` is not coerced. |
| `SourceSpace.orientations` | `None`, or a Python sequence of length-3 vectors. Free mode does not require unit length. Fixed mode still requires one unit vector per source | a `str`, `bytes`, or other non-sequence, including a top-level `numpy.ndarray` | `ForwardModelContractError`. |

`OrientationType` (`free`, `fixed`) documents those two modes. It is not a field on `SourceSpace`, and neither member is accepted in place of the bool. A truthy string such as `"free"` used to be treated as fixed orientation and could build a one-column leadfield; that path now fails in `validate()`.

`None`, `int`, `bytes`, and a member of a different enum (`CoordinateFrame` passed as `model_type`, `ConductorModelType` or `OrientationType` passed as `coordinate_frame`) are non-members and fail the same way. Synthetic fixtures and analytic oracles are not measured EEG, validated physics, or scientific evidence.

This boundary performs no implicit NumPy conversion: a top-level `numpy.ndarray` orientation table and `numpy.bool_` orientation flag are intentionally rejected. Convert these explicitly to a Python sequence and built-in `bool` before constructing `SourceSpace`. Enum, bool, and orientation-shape/component validation errors identify the field or component index and accepted domain without calling or echoing rejected input representations; custom representations can be unsafe or disclose caller data.

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
- [x] **Units**: Verifies source vertex positions `fwd['src'][k]['rr']` and sensor `loc` have norm $\le 1.0\text{ m}$ (larger values indicate millimetres and raise `CoordinateUnitMismatchError`). Values are not otherwise checked against a head model.
- [x] **Channel Order**: Verifies leadfield `row_names` match `info['ch_names']` without permutation.
- [x] **Sensor positions by channel name**: positions are taken from `info['chs']` and matched to leadfield rows **by `ch_name`**, whatever the order of `chs`. If any channel has no usable `loc`, no position is used for any channel.
- [x] **Placeholders are labelled**: if sensor positions (or source vertices) are unavailable, the result keeps its structure with identical placeholder positions (sensors on the default scalp sphere, sources at the origin) but adds a warning and records `provenance['sensor_positions'] == 'placeholder'` (respectively `provenance['source_positions']`). Placeholders are never electrode or source locations; measured positions are reported as `'info_chs'` and `'mne_src'`. Likewise `provenance['conductor_model']` is `'expected_conductor'` when one was supplied and `'default_placeholder'` (with a warning) otherwise.
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
   - **Closed-Form Center Dipole Limit**: Regression-checked against $V = c_1 \frac{3(\mathbf{q} \cdot \mathbf{r}_e)}{4 \pi \sigma R^3}$ with zero series truncation ($\Delta < 10^{-15}\text{ V}$).
   - **On-axis benchmark value**: Regression-checked against the stored value $V = 1.465475850798419 \times 10^{-7}\text{ V}$ ($\Delta < 10^{-14}\text{ V}$) for an on-axis dipole in a homogeneous sphere (Frank 1952 setting). This detects accidental changes of the implementation; it does not independently establish that the series is the correct physical solution.
   - **Exact-rational multi-shell oracle**: the multi-shell coefficients and potentials are compared with the classic transfer-matrix formula evaluated in exact rational arithmetic. This certifies numerical stability of the implementation, not the physics of the formula.

---

## 7. Verification Results

The test suite in `tests/forward_model_contract/test_forward_model_contract.py` validates:

- Rejection of millimeter units in conductor, sensors, and sources.
- Rejection of unknown coordinate frames and unaligned cross-frame configurations without transform.
- Rejection of non-member `model_type` and `coordinate_frame` values (plain strings, including strings equal to a member value, case or whitespace variants, `None`, `int`, `bytes`, and the wrong enum) with `ConductorGeometryError` or `CoordinateFrameMismatchError` at `validate()`, before `build_synthetic_forward_contract` touches `.value`.
- `ConductorModelType.SPHERICAL_3SHELL` and `SPHERICAL_1SHELL` still validate and build. `ANATOMICAL_BEM` stays rejected. `CoordinateFrame.HEAD` and `MNI` still validate and build. `UNKNOWN` stays rejected.
- `is_fixed_orientation` accepts only `True` or `False`. `OrientationType` and the strings `"free"` / `"fixed"` are not coerced. `orientations` must be `None` or a sequence of vectors, not a bare string or scalar.
- Affine coordinate transformation of source spaces into sensor frames.
- Rejection of non-monotonic, non-positive, non-finite, or unphysical conductor layers.
- Multi-shell inner-layer sensitivity: changing the skull conductivity $\sigma_{\text{skull}}$ or the brain radius $r_{\text{brain}}$ changes the computed potential, so no layer is silently dropped. This is a regression property of the implementation, not validation against data.
- Rejection of out-of-bounds sources (in `SourceSpace.validate` and in the public potential functions) and non-finite source/orientation coordinates.
- Non-unit fixed orientation vector rejection, including before a coordinate transform.
- Fail-closed zero-norm electrode, boolean rejection (`True`/`False` rejected in all numeric fields), rejection of numeric strings, `None`, and non-sized vectors, and non-finite dipole-moment handling (no `ZeroDivisionError`, no `TypeError`).
- Electrodes must lie on the outer surface relative to the conductor origin (inside, outside, and millimetre-scale electrodes are rejected); a shifted-origin montage reproduces the unshifted leadfield.
- `n_max_terms` must be a positive integer.
- No non-finite potential is returned: overflowing moments raise instead of producing `inf`/`NaN`, in both the analytic functions and `simulate_scalp_potentials`.
- Numerical stability of the multi-shell coefficients against an exact-rational oracle for brain radii from $1\text{ mm}$ to $8\text{ cm}$, a continuity check for a very small brain (no silent `0.0`), and reduction to the homogeneous sphere for a single shell and for equal conductivities.
- Conductor origin (`origin_m`) 3D finite meter validation and exact shift invariance across containment and concentric-sphere potential evaluation.
- Rejection of singular $4 \times 4$ affine coordinate transforms ($|\det(A)| < 10^{-12}$).
- Finite validation on MNE forward-solution leadfield matrices, active source coordinates (`rr`), and sensor locations (`loc`).
- Exact dipole potential linearity and superposition ($\Delta < 10^{-18}\text{ V}$).
- Dimensional consistency for free $(19, 48)$ and fixed $(19, 16)$ leadfield matrices.
- Average reference column zero-sum invariant ($\Delta < 10^{-11}$) and idempotency.
- Unipolar channel referencing: verified zero row, zero simulated reference potential, and conflicting policy rejection.
- Explicit `UNAVAILABLE` uncertainty semantics and JSON serialization.
- Closed-form center-dipole check, stored on-axis benchmark value (regression only), and the exact-rational multi-shell oracle (numerical stability only).
- Ragged, empty-row, and non-finite leadfield matrices raise `LeadfieldDimensionMismatchError` / `ForwardModelContractError` in every leadfield helper.
- Finite, bounded SVD diagnostics and condition numbers.
- Deterministic replay bit-for-bit.
- Strict non-promotional guardrails and disclaimer presence; a guard test fails if the docs or module describe the sensitivity checks as physical verification or describe the truncated series as an exact solution.
- MNE forward auditor mock execution and validation, sensor positions matched to rows by channel name, and labelled placeholders when positions are unavailable.

### Source / Math Limits (HOLD / SYNTHETIC_ONLY)

- Series truncations (`n_max_terms`) are numerical cutoffs for the synthetic fixture, not claims of infinite-series physical completeness.
- Default conductivities and radii are literature-typical engineering defaults for concentric spheres, not subject-specific tissue estimates.
- Analytic oracles certify **internal consistency** of this synthetic solver against closed-form limits; they do not certify biological validity or measured-EEG agreement.
- Truncation error grows as $(r_s/R)^{n_{\max}}$; for sources near the brain boundary it is not negligible at the default 60 terms (about $10^{-3}$ relative just inside the default brain shell). `n_max_terms` is caller-controlled; there is no automatic convergence estimate.
- The inner-shell radii are only required to be positive and increasing (the plausibility band applies to the outer radius and to channel distances). Extreme inner radii are handled numerically but are not anatomically meaningful.
- The auditor does not check that an MNE forward solution was computed with the `expected_conductor` model; `expected_conductor` is recorded, not compared. When it is omitted, `conductor_model` is a labelled default placeholder (`provenance['conductor_model'] == 'default_placeholder'`), not the model that produced the audited solution. Its status is `ENGINEERING_ONLY`, not a statement about the accuracy of the audited forward model.
- `SensorGeometry.validate()` judges sensors by their distance from the coordinate origin, not from the conductor origin. A conductor origin shifted by more than a few centimetres can therefore be rejected by its plausibility band even though the geometry relative to the conductor is valid; the engines themselves are origin-relative.
