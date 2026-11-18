# Bounded constrained relaxation and cold Lorentzian release

This additive engineering API composes the existing public nearest-neighbor
relaxer with the existing full Lorentzian SU(2) solver:

    field_theory.su2.relaxation_release.run_relaxation_then_cold_release

It accepts one dimensionless SU2GridField, an optional interior fixed-site
mask, shared model couplings, bounded optimizer settings, and a bounded
Lorentzian time grid. The optimizer's returned field object is passed directly
to the Lorentzian solver; the relaxation is not repeated and no serialized
field record is used as an intermediate.

## Anchor and velocity semantics

The optimizer's gradient-descent path does not define physical Lorentzian
velocity. The composition starts evolution at rest with an explicitly
zero-valued velocity array.

anchor_policy="cold_release" applies the supplied interior mask during
relaxation, then omits that mask from Lorentzian evolution. Only those interior
constraints are released. The solver continues to clamp every outer face for
a fixed_vacuum field. anchor_policy="retain" passes the same interior mask
to both stages. Masks that include outer boundary sites are rejected.

A completed relaxation means only that the optimizer terminated at its
declared first-order gradient tolerance under its active constraints. It is
not a minimum, stability, or soliton certificate. If the optimizer does not
meet that termination and stationarity contract, the default result is
NOT_CONVERGED and contains no Lorentzian history. Setting
allow_nonconverged=True permits an explicitly labeled
NOT_CONVERGED_EXPLORATORY_CONTINUATION; it does not relabel the relaxation
as stationary.

## Numerical record and bounded work

The result contains finite JSON histories for potential energy, kinetic energy,
total energy, cumulative dissipation, energy-balance residual, and approximate
lattice charge. It records optimizer termination/stationarity, trajectory
termination, field checksums, anchor policy, shared couplings, grid metadata,
and limitations. Field and velocity snapshots are discarded; output contains
no trajectory arrays.

At the zero-velocity initial snapshot, the Lorentzian total energy must equal
the nearest-neighbor static objective exactly at the reported binary64 level,
because both use the same finite-grid potential diagnostic and matching
couplings, spacing, and boundary. A mismatch fails closed.

Preflight uses Python integer products before either solver runs. It bounds
grid nodes, estimated relaxation node visits, RK stage/site evaluations, saved
snapshots, and snapshot bytes. The Lorentzian solver retains its own checks as
a second boundary.

## Interpretation limits

These are synthetic, dimensionless finite-grid diagnostics. Approximate
topological charge is never rounded to an integer, and no charge conservation
is asserted. Trajectories are not persistence or localization measures. No
pair-minus-isolated energy is computed; even an energy difference would not
be binding energy or a physical force. Fixed outer faces can reflect waves, so
any later observable should be evaluated before boundary-return effects and
then checked under larger-box refinement.

The API does not establish a stable soliton, continuum PDE stability, physical
calibration, or any biological, clinical, consciousness, enlightenment, psi,
or rebirth claim.
