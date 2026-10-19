# Spherical-spline CSD (NumPy production surface)

**Status:** HOLD / SYNTHETIC_ONLY
**Module:** `neurotopology_sim.experimental.preprocessing.spherical_csd`
**Owner:** Batch 2 / Cursor Agent C (sole production writer for this path)

## Scope

Sensor-space spherical-spline surface Laplacian / current source density (CSD).
Not anatomical source localization. Not a clinical or ontology claim.

## Pinned MNE

| Field | Value |
|---|---|
| Version | 1.13.2 |
| Tag | v1.13.2 |
| Commit | `bf67729b805865b5bb0f2f97621e416278efd1b2` |
| License | BSD-3-Clause |
| Sources | `mne/preprocessing/_csd.py`, `mne/channels/interpolation.py` |
| Defaults | `lambda2=1e-5`, `stiffness=4`, `n_legendre_terms=50` |

Mathematical source: Perrin et al. spherical splines (1987, 1989), as
implemented in the pinned MNE release.

## API

```python
from neurotopology_sim.experimental.preprocessing import (
    SphericalCSDConfig,
    compute_spherical_csd_transform,
    apply_spherical_csd,
)

cfg = SphericalCSDConfig(sphere=(0.0, 0.0, 0.0, 0.095))  # meters; no "auto"
result = compute_spherical_csd_transform(positions_m, cfg, channel_names=names)
csd = apply_spherical_csd(result.transform, data_volts)  # -> V/m^2
```

- Full N×N matrix; channel order is the row order of `positions`.
- Rejects non-finite / zero coordinates, sphere `"auto"`, nearly coincident
  sensors, and ill-conditioned `G + λ²I`.
- Average-reference null: `||M @ 1||_∞` checked fail-closed.
- Scaling: `1/R²` with R in meters → output unit `V/m²` for volt inputs.

## Relation to other surfaces

| Surface | Role |
|---|---|
| This module | NumPy operator (matrix + apply) |
| `adapters/mne_csd` (PR #378) | Thin wrapper around MNE instance API |
| `tools/mne_csd_reference_audit` (PR #402) | Independent audit reference (not production) |
| Antigravity Agent C | Independent conformance tests/fixtures (do not edit here) |

## Tests

Owned production tests:

```bash
python -m pytest tests/neurotopology_sim/experimental/preprocessing/test_spherical_csd.py -q
```

Antigravity Agent C owns independent parity tests/fixtures (PR #419;
`tests/experimental/test_spherical_csd_parity.py`). Do not edit that lane.

### Transform (from this implementation)

With unit vectors \(u_i\) after subtracting sphere center, cosine matrix
\(X=uu^\top\), Legendre kernels \(G=g_m(X)\), \(H=h_m(X)\) (MNE `_calc_g` /
`_calc_h`, stiffness \(m\), truncation \(N\)):

1. \(G_{\mathrm{reg}}=G+\lambda^2 I\) (diagonal add, MNE `_prepare_G`)
2. \(G_i=G_{\mathrm{reg}}^{-1}\), \(t_c=\mathbf{1}^\top G_i\), \(s_{gi}=\mathbf{1}^\top G_i\mathbf{1}\)
3. \(Z=I-\frac{1}{n}\mathbf{1}\mathbf{1}^\top\), \(C=G_i Z - t_c^\top\otimes(\mathrm{sum}(G_i Z)/s_{gi})\)
4. \(M=(C^\top H)^\top / R^2\)

Positions and \(R\) are meters; for volt inputs, \(M\) maps to **V/m²**.
Radius scaling: \(M\propto 1/R^2\) (verified exact for \(R\to 2R\) on the
octahedron). This is a sensor-space transform — not inverse localization and
not a claim that volume conduction is eliminated.

### Full-matrix conformance vs #419 @ `fa8f0f7`

Refreshed against live fixture provenance (not a stale summary): identity
\(X=I_N\) through **live** MNE-Python **1.13.2** commit
`bf67729b805865b5bb0f2f97621e416278efd1b2` via
`compute_current_source_density` (BSD-3-Clause); defaults `m=4`, `N=50`,
`λ²=1e-5`, meters → `V/m²`. Montages: tetrahedron_4, octahedron_6,
asymmetric_cap_8, synthetic_cap_12, **cap_20**, **cap_64**.

| Montage | prod vs fixture rel Frobenius | prod gate `1e-9` |
|---|---|---|
| tetrahedron_4 | 1.16e-14 | PASS |
| octahedron_6 | 3.19e-16 | PASS |
| asymmetric_cap_8 | 5.72e-14 | PASS |
| synthetic_cap_12 | 3.24e-13 | PASS |
| cap_20 | 1.88e-13 | PASS |
| cap_64 | 1.35e-12 | PASS |

Also: `‖M@1‖_∞` ≤ ~5e-10 (cap_64); channel-permutation rel ≤ ~1e-12; `1/R²`
exact. Malformed NaN/Inf/zero/coincident/bad-radius → `SphericalCSDError`.

### Diagnosis of #419 suite failures (not production)

Combined worktree (`#414` @ `7c59ada` + `#419` @ `fa8f0f7`, merge-base
`19c3203`) reports oracle↔fixture fails at **rtol/atol `1e-12`** on
asymmetric_cap_8 / synthetic_cap_12 / cap_20 / cap_64. Independent
reproduction:

- Fixture provenance: live MNE **1.13.2** / `bf67729…` identity → full N×N
  (not corrupted; production matches fixtures with worst rel Frobenius
  **1.347e-12** on cap_64, gate `1e-9` PASS).
- Algorithm: production follows MNE `_prepare_G` / `_compute_csd` with
  `TC = Gi.sum(0)`.
- #419 oracle uses `TC = Gi @ 1`. Under float64, `inv(G+λ²I)` is not exactly
  symmetric (`‖Gi−Giᵀ‖_∞` grows with N; ~8e-8 on cap_64), so `Gi@1` and
  `Gi.sum(0)` diverge (`‖ΔTC‖_∞` ~2e-8 on cap_64).
- Both oracle and production sit ~1.35e-12 rel Frobenius from the MNE
  fixtures — **above** the oracle’s strict `< 1e-12` gate and **below** the
  production `1e-9` gate. Classification: **oracle tolerance / TC definition
  under float64 inv asymmetry**, not a production defect and not bad fixture
  provenance. Do not widen tolerances from this lane; #419 owns the oracle fix
  (align `TC` to `Gi.sum(0)` and/or justify a looser oracle-only gate).

Optional live-MNE parity in owned tests skips when MNE is not installed (no
unauthorized install).

### CI note (discovery live on main @ `02520d4`)

`.github/workflows/round6_experimental_tests.py` (merged via #425) selects
component `spherical_csd` when this leaf changes and **requires** both:

1. `tests/neurotopology_sim/experimental/preprocessing/test_spherical_csd.py`
2. `tests/experimental/test_spherical_csd_parity.py` (#419-owned)

Hosted Required Checks after rebase onto `02520d4`
([run 39223928979](https://github.com/ChristianV997/NeuroTopology-Sim/actions/runs/39223928979)):
`spherical_csd` **BLOCKED** — `missing_required_tests:
tests/experimental/test_spherical_csd_parity.py`;
`candidate_test_executions: 0` (no #419 path executed). Surrogate canary
`NOT_APPLICABLE` is not CSD evidence. Pairing / stack of #419 is an
integration blocker; this lane does not edit workflows or #419 paths.
Shared package `__init__.py` files are no longer part of this PR diff
(main’s versions retained at rebase).
