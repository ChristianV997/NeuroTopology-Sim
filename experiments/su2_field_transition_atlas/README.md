# SU(2) bounded mode-following probe (Field Transition Atlas)

Synthetic lattice probe only. Compares geodesic evolution along a **declared**
tangent direction versus an **L2-orthogonal control** on the production
forward-link nearest-neighbor Skyrme energy.

## What this shows

- Relative energy change under equal geodesic step budgets.
- Active-site gradient residual along the probe.
- Finite-difference directional curvature
  \(\kappa(v)=[E(e^{+sv})+E(e^{-sv})-2E]/s^{2}\) using the production geodesic map.
- Mode overlap of the reprojected tangent with the initial declared direction.
- Wall time and `ru_maxrss` resource snapshots per series.

## What this does **not** show

- A converged transition path, NEB/string path, or branch-continuation solution.
- A metastable barrier height or lifetime.
- A physical frequency or Lorentzian spectrum.
- A soliton / topological certificate.
- Analytic Riemannian Hessian eigenmodes (HVP unavailable on `origin/main` at
  the intended base; dependency is reported in the result payload).

## Usage

```bash
# from repo root with numpy available
python -m experiments.su2_field_transition_atlas \
  --config experiments/su2_field_transition_atlas/configs/fta_checkerboard.json \
  --output /tmp/fta_mode_follow.json

python -m pytest tests/test_su2_fta_mode_follow.py -q
```

## Objective / metric contract

| Item | Source |
|---|---|
| Energy / gradient | `field_theory.su2.nearest_neighbor` forward-link |
| Active sites | production `_active_mask` (fixed-vacuum faces inactive) |
| Geodesic step | production `_geodesic_perturbation` |
| Curvature | `finite_difference_directional_curvature` in this package |

Research simulator only: no consciousness, clinical, or ontology claims.
