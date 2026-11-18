# General SU(2) field foundation

`field_theory.su2` is a synthetic, static, three-dimensional field representation.
It uses unit four-vectors `n` and the convention `U = n0 I + i sum(na sigma_a)`.
The three leading array axes are spatial; a time axis is not accepted. Grid spacing
and length units are explicit metadata. The `fixed_vacuum` boundary label records
the intended model boundary; the general field constructor does not enforce the
field value on a boundary. The hedgehog initializer does have vacuum-valued faces.

The compact C1 radial profile used by `hedgehog` is an initial configuration, not a
numerical solution of the Skyrme equations. No energy, topological charge, neural
interpretation or evidence of consciousness is calculated by this package.

Run: `python -m pytest tests/test_su2_field_foundation.py -q`.



## Constrained pair-relaxation prototype

`field_theory.su2.constrained_interaction` provides a bounded synthetic comparison between a two-hedgehog product field and the two corresponding isolated fields. All three use the same fixed-vacuum grid, forward-link objective, couplings, line-search settings, and per-run iteration budget. Small local anchor balls are frozen with exact Dirichlet values; anchors must be separated from one another, the opposite soliton support, and the box boundary by a stencil margin. Anchor pion vectors must span at least two non-collinear directions.

The versioned JSON result records input and result checksums, code revision, numerical status, energy and approximate-charge histories, constraint checks, weighted SO(3) anchor-patch fits, and work limits. Final pair-minus-isolated energy is withheld unless all three runs reach the declared first-order gradient tolerance and satisfy the anchor checks. This is only a **finite-grid, finite-box excess energy conditional on the specified frozen anchor patches**. The fixed patches do not establish a fixed-separation/fixed-isorotation collective-coordinate minimum; first-order stationarity and the bounded curvature screen do not certify a minimum.

Approximate per-core charge is a grid-anchor Voronoi partition diagnostic, not an integer-sector proof. The serialized charge_drift_status only reports whether observed drift is within the caller-declared screen; it is not confidence that an integer topological sector is preserved. Multistart runs, grid refinement, and anchor-size/placement sensitivity are still required before interpreting a negative excess as binding-like. The output is not a force, free-pair potential, physical energy, or physical time evolution. It is synthetic engineering evidence only.


The serializer verifies the canonical SHA-256 of the input record and the result payload before serialization. The result hash scope excludes only the \`result_sha256\` field itself. These hashes detect accidental inconsistency; they do not authenticate the source, protect against a caller recomputing hashes, or establish scientific validity.


Pair-to-isolated initial anchor values are matched with a recorded maximum absolute tolerance of 1e-12 in unit-field components. This accommodates floating-point roundoff from the SU(2) product/conjugation operations; larger discrepancies are rejected before relaxation. Each run then freezes its own matched anchor values exactly.

### Mesh-aware stationarity diagnostics

The constrained optimizer emits schema-v2 input and result records. The opt-in `continuum_l2` stationarity residual is `||g_free||_2 / sqrt(V_c)`, where `g` is the derivative of the volume-weighted lattice objective and `V_c = h_x h_y h_z`. It also records the lumped free-site measure `V_free = N_free V_c` as `active_l2_measure` and the per-volume RMS residual `rms = continuum_l2_residual / sqrt(V_free)`. These are finite-grid diagnostics over free sites; the cell-volume formulas assume a uniform-cell Cartesian mesh and do not establish continuum convergence. The v2 serializer does not accept prior v1 records, so consumers must branch on `schema_version` and migrate if they used the earlier experimental contract.
## Constrained-relaxation grid and anchor sensitivity

`field_theory.su2.constrained_interaction_sweep` adds a deterministic sweep
around the constrained pair-versus-isolated relaxation. It is separate from
`interaction_sweep.py`: that module evaluates a static product ansatz, while
this module runs the pair and both isolated controls through the optimizer for
each point.

The recommended first design fixes the model box extent at (14,14,14), the core
radius at 2.5, separation at (6.5,0,0), relative isorotation at identity,
and f_pi=e=1. It crosses three meshes—(15,15,15) at h=1, (21,21,21) at
h=0.7, and (29,29,29) at h=0.5—with anchor radii 1.5 and 2.0. Every
level has the same extent because (n-1)h=14. Both stationarity and descent
metrics are explicitly set to `continuum_l2`; solver settings are held fixed.

The primary value at a point is

[
Delta E_{h,a}=E^{mathrm{pair}}_{h,a}
-E^{mathrm{isolated,A}}_{h,a}
-E^{mathrm{isolated,B}}_{h,a},
]

conditional on the chosen frozen anchor patches. Compare mesh levels at each
fixed anchor radius, and report the across-anchor spread at each mesh only when
at least two anchor radii have available comparisons. With one anchor radius,
spread is not assessed (null), not reported as zero. A spread is a sensitivity
diagnostic, not an uncertainty interval. No Richardson extrapolation or
continuum limit is inferred. Multistart and independent anchor-placement
sensitivity are intentionally still outstanding.

The code-defined work estimate is
`3*N*(1 + iterations*(backtracks + 2) + 40)` per point. The six-point design
estimates 97,968,150 node-visits in aggregate; the largest point estimates
32,266,647, below the existing 75,000,000 per-call limit. The sweep also caps
aggregate estimated work at 100,000,000 and executes cases serially. This is a
workload heuristic, not a wall-time or peak-memory guarantee. The full
six-point design is not run in normal CI.

The result preserves each validated single-run v2 record, nullable comparison,
preflight failure, and checksum. Known anchor-identifiability rejections are
recorded as input-preflight rejections; unexpected `ValueError` and programming
errors still propagate. Geometry and budget are checked sweep-wide before any
case runs, while sampled-anchor identifiability and pair/isolated matching are
checked by the underlying runner for each case immediately before that case's
relaxations. A later case can therefore be rejected after earlier cases have
completed; its row is retained and the overall comparison is marked incomplete.
Plot data and optional Agg rendering live in the
separate `constrained_interaction_visualization.py` module. Withheld comparisons
appear as statuses, never as zero-valued energy observations.

Example:

```python
from field_theory.su2.constrained_interaction_sweep import (
    recommended_constrained_sensitivity_spec,
    run_constrained_interaction_sensitivity_sweep,
)
from field_theory.su2.constrained_interaction_visualization import (
    render_constrained_sensitivity_png,
)

# Replace this with the full SHA of the revision being evaluated.
spec = recommended_constrained_sensitivity_spec(
    code_revision="9e950316e031ae60d05e21626231c47bd785ac1f"
)
result = run_constrained_interaction_sensitivity_sweep(spec)
render_constrained_sensitivity_png(result, "artifacts/su2-sensitivity.png")
```

This remains synthetic finite-grid optimization output: it is not a force,
binding energy, physical energy, physical-time evolution, or evidence about
biology, consciousness, or rebirth.

### Numerical failure contract

The constrained runner preflights the derived binary64 energy and analytic-gradient coefficients before constructing fields. Both must be finite and nonzero in binary64; this is an intentional, conservative coupling-domain limit applied before grid-volume scaling, so some couplings whose combined grid-scaled coefficient could be representable may still be rejected. Binary64 scale factors are combined in exponent space for grid-volume, energy-square, and transpose-gradient products, avoiding avoidable intermediate overflow/underflow; for energy evaluation, a whole nonzero sigma or quartic term that collapses entirely to zero raises a numerical failure; sigma products and transpose-gradient scaling use exponent-space arithmetic. Quartic-gradient cubic intermediates retry in exponent space if the fast binary64 polynomial overflows or underflows. Fixed-vacuum wrap differences are zeroed before spacing division, and quartic energy and gradient terms are evaluated only on included links. Exactly equal or opposite included link vectors are recognized as zero wedges before products are formed. Other included-link quartic minor products that trigger binary64 overflow or underflow fail explicitly; near-canceling finite products still use ordinary binary64 arithmetic, so this is not an exact or arbitrary-precision determinant implementation. Individual components below binary64's subnormal range follow IEEE-754 rounding. Cell volume is formed with order-independent exponent scaling and must be finite and nonzero. Both the constrained runner and static interaction evaluator preflight this before constructing fields. The optimizer uses a scale-safe Euclidean norm so tiny gradient components are not mistaken for zero. Numeric failures in initial diagnostics, optimization, or post-optimization evaluation are returned as per-run `NUMERICAL_FAILURE` records with `failure_class`, a stage-specific `termination`, and `null` for unavailable metrics; the top-level final comparison is withheld. Numerical exceptions during derived-geometry calculation, initial field construction, or anchor fitting are raised as `NumericalPreflightError` (a `ValueError` subclass) with the stage and original numeric exception class/cause; no partial result is emitted before valid initial fields exist. Ordinary input and programming errors such as `ValueError` and `TypeError` continue to propagate unchanged.

The initial pair-minus-isolated value is a direct arithmetic comparison of the initial fields and may remain available when those three initial energies are finite, even if a later solve fails. It is not a relaxed-energy result. The final value is emitted only when all three runs satisfy the declared convergence and constraint checks and the subtraction remains finite. Failure records remain inside the v2 result envelope; consumers should branch on status and treat unavailable numerical fields as nullable. Canonical serialization rejects NaN and infinity and rechecks the result hash.


