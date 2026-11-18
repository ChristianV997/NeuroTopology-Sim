# Bounded SU(2) direction scan

## Purpose and boundary

\`field_theory.su2.direction_scan.scan_local_skyrme_principal_symbol_directions\`
runs the existing continuum one-point local-symbol analyzer at a deterministic
finite set of unit spatial covectors. It is a **discovery scan**, not a test that
can certify strong hyperbolicity, real roots in every direction, well-posedness
of the PDE, or stability of the lattice evolution.

Each sample retains the analyzer's root classification, roots, classification
tolerance, and eigenvector-condition telemetry. A sampled robust nonreal root is
evidence against real characteristics at that sampled 1-jet and direction.
Unresolved samples remain unresolved. A result with no sampled nonreal roots
means only that no counterexample was found among the directions actually
evaluated.

## Mesh and resource bounds

The scan starts from a fixed 12-vertex, 20-face icosahedron. It refines only
triangles touching a sample classified as nonreal, numerically unresolved, or
carrying the analyzer's eigenvector-condition warning. Refinement bisects each
selected face at normalized edge midpoints. Edge insertion and sample ordering
are deterministic; shared edges within a refinement wave share one midpoint.
Unselected faces remain coarse, so the mesh is a sampling guide and not a
conforming PDE discretization.

The public API requires \`12 <= max_directions <= 4096\` and
\`0 <= max_refinement_levels <= 12\`. It refuses an entire next refinement wave
when that wave would exceed the direction cap; it never silently truncates a
wave or drops an evaluation. Every point runs the canonical one-direction
analyzer. With fixed-size 3-by-3 coefficient blocks and a 6-by-6 eigensolve,
the work and retained sample storage are O(N) in the number N of evaluated
directions, with N at most 4096. Mesh bookkeeping is linear in the sampled
vertices and faces.

The result reports:
- \`nonreal_roots_sampled\` if at least one analyzed direction has that status;
- otherwise \`numerically_unresolved_samples\` if any analyzed direction is unresolved;
- otherwise \`no_nonreal_roots_sampled\`.

\`termination_reason\` separately reports whether refinement stopped because no
suspicious faces remained, the configured level limit was reached, or the next
wave exceeded the direction budget. All analyzer input/evaluation exceptions
propagate; failed directions are not omitted from a nominal result.

## Reproducibility and interpretation

The mesh has no random seed and uses no optional geometry package. Repeated
calls with equal inputs and budgets visit the same directions in the same order.
The scan reuses the analyzer's float64 validation, local root tolerances, and
conditioning warnings; it introduces no alternate root classifier.

Adaptive sampling can miss a narrow nonreal or defective region when none of
the initial or subsequently sampled points signals refinement. A finite scan
cannot establish a uniform eigenbasis or strong hyperbolicity, even if all
sampled roots are real and well-conditioned. It does not alter the Lorentzian
evolution solver, infer physical calibration, or establish any biological,
consciousness, or clinical claim.

The focused tests are run by \`.github/workflows/su2-lorentzian.yml\` alongside
the existing local-principal-symbol and Lorentzian tests. No test result is
claimed until that workflow runs on the exact candidate head.
