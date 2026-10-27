# Sheaf → scalar readout benchmark

Minimal NumPy testbed for cellular-sheaf coboundaries and edgewise linear
readouts Λ_e : R^k → R.

## Quick start

```bash
python -m tools.sheaf_scalar_readout
pytest tests/test_sheaf_scalar_readout.py -q
```

## Canonical triangle

Oriented edges `1→2`, `2→3`, `3→1`; stalks R²; all restrictions identity except
`ρ_{1≤e31}=R_{π/2}`. With `z₁=(1,1)`, `z₂=z₃=0`, and Λ = first coordinate:

| Edge | (B₀^F z)_e | Λ(·) |
|------|------------|------|
| e12 | (−1,−1) | −1 |
| e23 | (0,0) | 0 |
| e31 | (−1,1) | −1 |

Sheaf cochain exact; scalar cycle sum −2 ≠ 0 (incompatible readout).

## Claim boundary

See `CLAIM_BOUNDARY.md`. Not a neural model. Exactness, CTMC affinity, and
physical EMF/work remain distinct; the physical bridge (work-per-mismatch units
+ rate/EMF justification) is explicitly missing.
