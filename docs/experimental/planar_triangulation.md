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
`edge_incidences`, structured `failure_kind`, and **separate** diagnostics for:

1. `abstract_chain` — `D1 @ D0 == 0` (incidence only; never certifies geometric validity)
2. `planar_hull_triangulation` — planar straight-line embedding of the convex hull
3. `delaunay_empty_circle` — empty-circumcircle property (optional)

`failure_kind` values: `none` | `malformed_input` | `invalid_planar_embedding` | `delaunay_policy_failure`.

## Degeneracy policy and claim separation

| Policy | Behavior |
|---|---|
| `reject` | Always reject duplicates / global collinearity; reject represented cocircularity **only when Delaunay is required** |
| `lexicographic_tiebreak` | With Delaunay required, allow weak Delaunay (points may lie on circumcircles); no coordinate perturbation |

`require_delaunay=False` / `check_delaunay=False` must accept a valid planar triangulation of a cocircular set. `D1 @ D0 == 0` is an incidence identity only and does **not** rule out crossings or overlaps — planar embedding is a separate diagnostic.

Finite jitter is **not** Simulation of Simplicity. Floats use a **represented-input exact-sign** policy (`Fraction.from_float`); this is not Shewchuk adaptive expansions and not a fixed epsilon predicate.

## Sources

- Shewchuk, J. R. Adaptive Precision Floating-Point Arithmetic and Fast Robust Geometric Predicates. https://people.eecs.berkeley.edu/~jrs/papers/robustr.pdf
- CGAL `Triangulation_2` / `Delaunay_triangulation_2` manuals (hull subdivision vs empty-circle)

Shewchuk’s adaptive C kernel is **not** copied.

## Ownership

Sole production writer path for Batch 2 Cursor Agent A: `planar_triangulation.py`.  
Adversarial geometry tests are owned by Antigravity Agent A (do not edit that suite here).
