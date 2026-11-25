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

### Planar vs Delaunay (names and defaults)

| Entry point | Planar embedding | Empty-circle / cocircular policy |
|---|---|---|
| `triangulate_2d(..., require_delaunay=...)` | Always constructed/validated as a planar hull triangulation | **Default `True`**: also require Delaunay layer + apply `degeneracy_policy` to cocircularity |
| `validate_planar_mesh(..., check_delaunay=...)` | Always validates planar hull triangulation of a *supplied* mesh | **Default `False`**: Delaunay layer skipped unless explicitly enabled |

These flags are intentionally separate. Disabling Delaunay must not reject an otherwise valid planar triangulation of a cocircular point set. Enabling Delaunay applies the documented degeneracy policy without weakening planar checks.

Coordinates may be sequences or NumPy arrays of shape `(N, 2)` with finite values. Simplex indices must be actual integers (not `bool`, not float — including integral-valued floats such as `1.0`); repeated / negative / OOB indices are rejected before coordinate dereference (no `IndexError`, no negative wrap).

`PlanarTriangulationResult` includes `simplices`, ordered `hull_cycle` / `hull_boundary_cycle`,
`edge_incidences`, structured `failure_kind`, and **separate** diagnostics for:

1. `abstract_chain` — `D1 @ D0 == 0` (incidence only; never certifies geometric validity)
2. `planar_hull_triangulation` — planar straight-line embedding of the convex hull (orientation, incidences, hull-boundary cycle, nonincident crossings/overlaps, vertex-on-edge)
3. `delaunay_empty_circle` — empty-circumcircle property (optional)

`failure_kind` values: `none` | `malformed_input` | `invalid_planar_embedding` | `delaunay_policy_failure`.

Positive triangle areas, Euler counts, `D1 @ D0 == 0`, and area-sum equality are **not** sufficient proofs of a valid planar embedding.

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
