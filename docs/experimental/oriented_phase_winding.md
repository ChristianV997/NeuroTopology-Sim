# Oriented Integer Phase Winding — Contract

**Status:** HOLD / SYNTHETIC_ONLY  
**Production path:** `neurotopology_sim/experimental/topology/winding.py`
**PR:** #413 (Cursor Agent B / Batch 2)

Algebraic sensor-space descriptor on an oriented 2-complex. **Not** evidence of
cortical propagation, a biological singularity, consciousness, or any ontology
claim. Passing unit tests does **not** establish physical topology.

No production callers outside this package yet; consumers pass dense incidence
and phases explicitly. Hodge (#423) accepts a separate edge 1-cochain `omega`
via `hodge_decompose(...)` — integration is compose-only (do not merge
modules).

---

## API (stable)

```python
from neurotopology_sim.experimental.topology.winding import (
    phase_winding,          # primary
    branch_index_floor,
    signed_first_moment,
    origin_shifted_moment,
    charge_moments,
    WindingResult,
    ChargeMomentResult,
    WindingError,
    SUPPORTED_WRAP_INTERVALS,  # ("[-pi,pi)",)
    DEFAULT_TIE_TOL,           # 1e-12
)

result = phase_winding(
    vertex_phase,   # shape (|V|,), finite float radians
    d0,             # dense |E|×|V|
    d1,             # dense |F|×|E|
    *,
    wrap_interval="[-pi,pi)",
    tie_tol=1e-12,
)
```

### Shapes and dtypes

| Object | Shape | dtype / domain |
|---|---|---|
| `vertex_phase` | `(|V|,)` | finite float |
| `d0` | `(|E|, |V|)` | dense numeric, integer-valued in `{-1,0,+1}` → stored `int64` |
| `d1` | `(|F|, |E|)` | dense numeric, integer-valued in `{-1,0,+1}` → stored `int64` |
| `branch_index` (`n`) | `(|E|,)` | `int64` |
| `omega` | `(|E|,)` | float in `[-π, π)` |
| `face_charge` (`q`) | `(|F|,)` | `int64` |
| `tie_edge_mask` | `(|E|,)` | `bool` |

Empty faces (`|F|=0`) are allowed when `d1.shape == (0, |E|)`.

### Orientation

Caller-supplied. Documented fixture convention for the unit triangle with edges
`(0,1),(1,2),(0,2)`:

- `(D0 θ)_e = θ_v − θ_u` for oriented edge `(u,v)`
- `(D1 ω)_t = ω_01 + ω_12 − ω_02`

CCW `θ=[0, 2π/3, 4π/3]` → `q=+1`; CW `θ=[0, −2π/3, 2π/3]` → `q=−1`.

### Wrap interval and branch index

Only `wrap_interval="[-pi,pi)"` is supported.

```text
raw   = D0 @ θ
n     = floor((raw + π) / (2π))     # int64
omega = raw − 2π n                  # ∈ [-π, π)
```

Exact `+π` maps to `−π`; exact `−π` stays `−π`. No jitter is applied to break
ties.

### Tie tolerance

`tie_tol` (default `1e-12`, finite, ≥ 0): edges with `omega` within `tie_tol` of
either discontinuity endpoint `±π` are flagged in `tie_edge_mask`. Ties are
reported, not silently resolved.

### Sparse / dense

**Dense only.** SciPy sparse matrices and sparse-like duck types (`tocsr` /
`nnz`+`format`) are rejected with `WindingError`. Object-dtype arrays rejected.

### Invalid-input behavior

Raises `WindingError` (subclass of `ValueError`) for:

- non-1-D / non-finite phases
- wrong `|V|` or edge-dimension mismatch between `d0` and `d1`
- non-dense / non-integer / out-of-`{-1,0,+1}` incidence
- `d1 @ d0 != 0` (exact integer identity required)
- unsupported `wrap_interval` or negative/non-finite `tie_tol`

### Incidence vs embedding

`D1 @ D0 == 0` is a **cochain / incidence** identity. It does **not** certify a
valid planar geometric mesh. Geometric validation belongs to the geometry module.

### Discrete identity and integer winding

When `D1 @ D0 == 0`:

```text
D1 @ omega = −2π (D1 @ n)
q          = −D1 @ n          # int64, core path stays integer
```

`identity_residual_max_abs` reports `max|D1@omega + 2π(D1@n)|`.

---

## Moments (optional helpers)

Coordinates are **sensor-coordinate units**: caller Euclidean embedding for face
barycenters (e.g. montage mm). Not anatomical unless the caller supplies such
embedding.

**Origin-shift convention (derived):** define `p_q(0) = Σ_t q_t r_t`. Moving the
origin by vector `a` means new coordinates `r' = r − a`. Then

```text
p_q(a) = Σ q_t (r_t − a) = p_q(0) − (Σ q_t) a = p_q(0) − Q_net · a
```

The minus sign follows from `r' = r − a`. The translation form
`m(r+v)=m(r)+Q_net·v` is equivalent with `a = −v`.

`charge_moments`: charge separation is `||r_+ − r_-||` when both signs exist;
otherwise `charge_separation=NaN` and `charge_separation_defined=False`
(**never** substitute `0.0`). Not biological origin invariance.

---

## Limitations

- Near-zero amplitude / ill-defined Arg is not handled upstream of this module.
- Only `[-pi,pi)` wrap interval.
- Numpy dense only; no dataset or live API access.
- Required CI `core-tests` allow-list does **not** currently execute this suite
  (workflow edits out of ownership).
