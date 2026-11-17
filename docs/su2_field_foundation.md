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

### Numerical failure contract

The constrained runner preflights the derived binary64 energy and analytic-gradient coefficients before constructing fields. Both must be finite and nonzero in binary64; this is an intentional, conservative coupling-domain limit applied before grid-volume scaling, so some couplings whose combined grid-scaled coefficient could be representable may still be rejected. The gradient assembly applies cell-volume, derivative, and transpose-spacing factors before the coupling coefficient in the stencil to avoid premature underflow in tested anisotropic-grid cases. It rejects couplings whose supported coefficients overflow or underflow to zero rather than clipping them. Numeric failures in initial diagnostics, optimization, or post-optimization evaluation are returned as per-run `NUMERICAL_FAILURE` records with `failure_class`, a stage-specific `termination`, and `null` for unavailable metrics; the top-level final comparison is withheld. Only numerical exception classes are converted this way. Input and programming errors such as `ValueError` and `TypeError` continue to propagate.

The initial pair-minus-isolated value is a direct arithmetic comparison of the initial fields and may remain available when those three initial energies are finite, even if a later solve fails. It is not a relaxed-energy result. The final value is emitted only when all three runs satisfy the declared convergence and constraint checks and the subtraction remains finite. Failure records remain inside the v1 result envelope; consumers should branch on status and treat unavailable numerical fields as nullable. Canonical serialization rejects NaN and infinity and rechecks the result hash.
