# Oriented Integer Phase Winding

**Status:** HOLD / SYNTHETIC_ONLY  
**Production path:** `neurotopology_sim/experimental/topology/winding.py`

Algebraic sensor-space descriptor on an oriented 2-complex. Not evidence of
cortical propagation, biological vortices, or clinical claims.

## API

```python
from neurotopology_sim.experimental.topology import phase_winding

result = phase_winding(
    vertex_phase,  # shape (|V|,), finite radians
    d0,            # integer |E|×|V|, entries in {-1,0,+1}
    d1,            # integer |F|×|E|, entries in {-1,0,+1}
    wrap_interval="[-pi,pi)",
    tie_tol=1e-12,
)
```

Requires exact cochain identity `d1 @ d0 == 0`.

## Convention

| Quantity | Definition |
|---|---|
| raw | `d0 @ theta` |
| branch index | `n = floor((raw + π) / (2π))` (int64) |
| omega | `raw - 2π n` in `[-π, π)` |
| face charge | `q = -d1 @ n` (int64) |
| identity | `d1 @ omega = -2π (d1 @ n)` |

Exact `+π` maps to `-π`; exact `-π` stays `-π`. Edges within `tie_tol` of
either wrap discontinuity are flagged in `tie_edge_mask`.

**Sign check (standard triangle):** CCW `θ=[0, 2π/3, 4π/3]` → `q=+1`;
CW `θ=[0, -2π/3, 2π/3]` → `q=-1`.

## Moments

`signed_first_moment(q, face_coordinates)` uses caller coordinate units.
Origin shift: `p_q(a) = p_q(0) - Q_net * a` with `r' = r - a`.
`charge_moments` returns undefined separation (NaN + `defined=False`) when
either sign is absent — not biological origin invariance.

## Limitations

- Near-zero amplitude / ill-defined Arg is not handled.
- Only `wrap_interval="[-pi,pi)"` is supported.
- Numpy only; no dataset or live API access.
