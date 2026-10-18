# Planar triangulation (experimental production)

**Module:** `neurotopology_sim/experimental/geometry/planar_triangulation.py`  
**Schema:** `neurotopology_sim.planar_triangulation.v1`  
**Posture:** HOLD / SYNTHETIC_ONLY — discrete geometry only; not cortical topology or scientific PASS.

## API

```python
from neurotopology_sim.experimental.geometry import triangulate_2d, validate_planar_mesh

result = triangulate_2d(coords, degeneracy_policy="reject", require_delaunay=True)
report = validate_planar_mesh(coords, simplices, check_delaunay=False)
```

`PlanarTriangulationResult` includes `simplices`, ordered `hull_cycle` / `hull_boundary_cycle`,
`edge_incidences`, and **separate** diagnostics for:

1. `abstract_chain` — `D1 @ D0 == 0`
2. `planar_hull_triangulation` — planar straight-line embedding of the convex hull
3. `delaunay_empty_circle` — empty-circumcircle property (optional)

## Degeneracy policy

| Policy | Behavior |
|---|---|
| `reject` | Reject duplicates, global collinearity, and exact cocircularity when Delaunay is required |
| `lexicographic_tiebreak` | Allow weak Delaunay (points may lie on circumcircles); no coordinate perturbation |

Finite jitter is **not** Simulation of Simplicity. Floats are interpreted as exact IEEE binary values via `Fraction.from_float`.

## Sources

- Shewchuk, J. R. Adaptive Precision Floating-Point Arithmetic and Fast Robust Geometric Predicates. https://people.eecs.berkeley.edu/~jrs/papers/robustr.pdf
- CGAL `Triangulation_2` / `Delaunay_triangulation_2` manuals (hull subdivision vs empty-circle)

Shewchuk’s adaptive C kernel is **not** copied; this module uses exact rational signs on represented inputs.

## Ownership

Sole production writer path for Batch 2 Cursor Agent A: `planar_triangulation.py`.  
Adversarial geometry tests are owned by Antigravity Agent A (do not edit that suite here).
