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
