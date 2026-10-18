# Four-shell EEG forward model (`physics/eeg_forward/four_sphere.py`)

Status: **HOLD / SYNTHETIC_ONLY**. Experimental. Engineering model of a dipole in an idealised,
concentric, piecewise-homogeneous head. It is not individual anatomy, has not been validated against
recordings, and supports no biological, clinical, or diagnostic claim. Nothing here uses participant
data, EEG datasets, or dataset downloads.

## What is established

| Level | Status |
|---|---|
| Implemented | `physics/eeg_forward/four_sphere.py`, NumPy only |
| Unit-tested | `tests/physics/eeg_forward/test_four_sphere.py`: 60 offline tests pass, 1 skipped (see the oracle section) |
| Cross-checked against an independent oracle | Done out of tree, against the Hermes Agent A oracle on PR #409 (branch `batch1/hermes-a-shell-bvp-oracle`). Agreement at round-off. Not imported into the repository |
| Integration-tested | Not applicable. No pipeline or CLI consumes this module |
| Live-validated | **No.** No recording, no measured potential, no published benchmark was used |

## Geometry and conventions

- Concentric shells centred on the origin, innermost first: brain `0 <= r < r1` (sigma1), CSF
  `r1 < r < r2` (sigma2), skull `r2 < r < r3` (sigma3), scalp `r3 < r < r4` (sigma4).
- `radii_m = (r1, r2, r3, r4)` in metres, strictly increasing, `r4 <= 1 m`.
  `conductivities_sm = (sigma1, sigma2, sigma3, sigma4)` in S/m, each in `[1e-4, 10]`.
  Both bounds fail closed to catch unit errors.
- Sensors lie on the outer surface `r = r4` (within relative tolerance `1e-9`).
- Source position `r_s` lies in the brain: `d = |r_s| < r1`. Source direction `e_s = r_s / d`.
  For `d = 0` the axis is taken as `z = (0, 0, 1)`; only the degree-1 term survives.
- Dipole moment `q` in A·m, global Cartesian frame. Radial component `q_r = q · e_s`.
  Tangential component `q_t = q - q_r e_s`.
- Sensor direction `e` = sensor position / `r4`. `mu = e_s · e`. `q_t · e = q · e - q_r mu`.
- Potential in volts. Positive on the side the dipole points towards.
- Average reference: the degree-0 term is zero, so the mean over the scalp sphere is zero.
  No infinity reference is used.
- Units. Output scales as `q / (sigma1 r4^2)`: A·m / (S/m · m²) = V. Transfer ratios `T_l` are
  dimensionless and depend only on radius and conductivity ratios.

## Equations

Let `rho_k = r_k / r4`, `t = d / r4`, and let `P_l`, `P_l'` be the Legendre polynomial and its
derivative in `mu`.

Free-space dipole expansion (verified to about 1e-14 against the closed form):

    V_inf,l(r4) = (1 / (4 pi sigma1 r4^2)) t^(l-1) [ l q_r P_l(mu) + P_l'(mu) (q · e - q_r mu) ]

The radial term carries the factor `l`. The tangential term does not. With the Condon-Shortley
phase `P_l^1(mu) = -sin(theta) P_l'(mu)` and the unit tangent `rho_hat = (e - mu e_s) / sin(theta)`,
the tangential term is `P_l'(mu) (q_t . e) = -P_l^1(mu) (q_t . rho_hat)`. The code evaluates
`P_l'(mu) (q · e - mu q_r)` and never divides by `sin(theta)`. The term is therefore finite and zero at
both poles, where `e - mu e_s = 0`. Both orientations share the
same degree-`l` radial functions in the brain, so the layered transfer ratio is orientation-free:

    T_l = V_scalp,l / V_inf,l(r4)                       (dimensionless)
    V(sensor) = sum_{l=1..L} T_l V_inf,l(r4)

Shell state. For each degree `l` the state `(Phi, sigma Phi')` is propagated from the scalp inward.
In a homogeneous shell with conductivity `sigma`, let

    Psi(rho) = [[ rho^l,          rho^-(l+1)         ],
                [ sigma l rho^(l-1), -sigma (l+1) rho^-(l+2) ]]

so that the shell map from outer to inner state is `M = Psi(rho_inner) Psi(rho_outer)^-1`. With
`x = rho_inner / rho_outer <= 1`, the closed form is

    m11 = ((l+1) x^l + l x^-(l+1)) / (2l+1)
    m12 = -rho_outer (x^-(l+1) - x^l) / (sigma (2l+1))
    m21 = -sigma l (l+1) (x^-(l+2) - x^(l-1)) / (rho_outer (2l+1))
    m22 = (l x^(l-1) + (l+1) x^-(l+2)) / (2l+1)

Scalp state `(1, 0)` (unit potential, zero radial current) is propagated through shells 4, 3, 2 to
the brain interface. Writing the brain solution as `alpha r^l + beta r^-(l+1)`, the brain match gives

    T_l = 1 / beta_1          (per unit scalp potential, in normalised units with r4 = 1)

Homogeneous limit (all sigma equal, closed form): `T_l = (2l+1)/l`. The resulting potential has
closed forms with generating functions `D = 1 - 2 t mu + t^2`:

    radial:      sum_l (2l+1)   t^(l-1) P_l(mu)    = ((1 - t^2) D^(-3/2) - 1) / t
    tangential:  sum_l (2l+1)/l t^(l-1) P_l'(mu)  = 2 D^(-3/2) + ((t - mu)/sqrt(D) + mu) / (t (1 - mu^2))

so `V = (q_r A + (q · e - q_r mu) B) / (4 pi sigma r4^2)` in the homogeneous case.

Numerical method. The propagation avoids the global 7x7 linear solve, which is ill-conditioned at
large degree (condition number grows roughly as `rho^(-2l)`). The off-diagonal entries `m12` and
`m21` are differences of two powers. Their absolute rounding error is near machine epsilon times the
matrix scale, and their relative error grows for very thin shells. Against the independent 7x7 solve,
`T_l` agrees to `5e-15` for shells as thin as `1e-9` of the radius.

## Quality gates (fail closed)

Results are withheld, never silently regularised. The gates are:

- **Interface potential and current residuals.** Each shell's own Euler representation, evaluated at
  its inner interface, is compared with the propagated state. Also checked: the brain representation
  against the closed-form `beta_1`. Limit: `residual_tol` (default `1e-9`).
- **Scalp zero-current residual.** The outer-boundary radial current from the shell-4 representation of
  `(1, 0)`, normalised by its scale. Limit: `residual_tol`.
- **Truncation tail.** Every degree has an envelope `|T_l| t^(l-1) (l |q_r| + l(l+1)/2 |q_t|) / (4 pi sigma1 r4^2)`.
  It bounds that degree's term at every sensor, using `|P_l| <= 1` and `|P_l'| <= l(l+1)/2` on `[-1, 1]`
  and `|q_t . e| <= |q_t|`. The dropped tail is estimated by extrapolating the last consecutive envelope
  ratio `r` as `env_L r / (1 - r)`, then compared with the largest sensor potential. Limit: `tail_tol`
  (default `1e-10`). The estimate is not a proven bound (see Limitations).
- **Non-finite values.** NaN compares false against any tolerance, so non-finite transfer ratios or
  residuals are rejected explicitly. Overflow for extreme radius ratios is reported as a quality error.

`shell_condition_number` in the diagnostics is informational only. The condition number of the raw
`Psi` matrices grows without bound with degree, so it is not gated.

Errors:

- `FourSphereInputError` (a `ValueError`): invalid geometry, source, sensor, degree, or tolerance.
- `FourSphereQualityError` (a `ValueError`): a quality gate failed. The message names the limit.

## Truncation

`max_degree` defaults to 256 (maximum 512). The tail check above decides whether the sum has
converged. The declared convergence range is `d / r4 <= 0.8` for the tested layered geometry: `L = 128`
and `L = 256` agree to `1e-9` relative, and the tail at 256 is below `1e-10`.

Non-convergence is reported, not hidden. A source at `d / r4 = 0.87` with a radial moment fails at
`L = 16` with a truncation-tail error. The tail decays roughly as `(d / r4)^(L-1)`, so depths near
`r1 / r4 ≈ 0.88` need larger `L`.

## Orientation

- `q_r` and `q_t` are defined relative to `e_s`. Rotating the source, moment, and sensors together
  leaves the potentials unchanged (tested to `1e-12`).
- Near-axis sensors (`mu → ±1`) are finite and match the homogeneous closed forms at sensor angles of
  `1e-3` and `1e-6` rad, to `1e-7` relative. Exact axis sensors are finite and agree with the `1e-6` rad
  limit to `1e-6`. Legendre values and derivatives use recurrences that avoid division by `1 - mu^2`.
- The closed-form tangential term has `1 / (1 - mu^2)` and loses accuracy near the axis. The `1e-7`
  tolerance in the near-axis test reflects the closed form's own rounding, not the production model's.
  The production code does not evaluate that expression.

## Regression: a common 1/l attenuation is detected

A variant that multiplies both orientation terms by `1/l` (equivalently, `T_l -> T_l / l`) is wrong.
The radial homogeneous coefficient must be `(2l+1)`, not `(2l+1)/l`. The test
`test_one_over_l_attenuation_applied_to_both_terms_is_detected` requires the production model to match the
closed form to `1e-11` and the variant to miss by more than `1e-2`, for both radial-only and
tangential-only dipoles.

## Verification evidence

Commands (run from the repository root):

    python -m pytest tests/physics/eeg_forward -q
    python -m compileall -q physics/eeg_forward tests/physics/eeg_forward

Acceptance categories and tests:

| Requirement | Test(s) |
|---|---|
| Homogeneous closed forms, radial and tangential | `test_homogeneous_forward_matches_closed_radial_and_tangential_forms`, `test_radial_only_*`, `test_tangential_only_*`, `test_homogeneous_transfer_ratio_is_2l_plus_1_over_l` |
| Layered interface and scalp residuals across degrees | `test_interface_and_scalp_residuals_stay_at_round_off_to_degree_256`, `test_quality_gate_rejects_residuals_above_tolerance` |
| Layered transfer ratios vs independent solve | `test_layered_transfer_ratio_matches_independent_global_solve`, `test_thin_shell_transfer_matches_independent_global_solve` |
| Source depth and orientation, near-axis, d = 0 | `test_near_axis_and_exact_axis_*`, `test_depth_zero_*`, `test_rotation_*`, `test_potential_is_linear_*` |
| Truncation convergence and non-convergence | `test_truncation_converges_for_declared_depth_range`, `test_truncation_non_convergence_is_reported_not_hidden` |
| 1/l regression | `test_one_over_l_attenuation_applied_to_both_terms_is_detected` |
| Average reference | `test_average_reference_gives_zero_mean_over_scalp` |
| Input validation | `test_invalid_*` |
| Reproducibility | `test_repeated_calls_are_bitwise_identical` |
| Finite output | `test_outputs_are_finite_over_geometry_and_depth_grid` |
| Clean import, numpy only | `test_package_import_is_clean_and_numpy_only` |
| Oracle cross-check | Out of tree (see below). The in-repository test is skipped with a stated reason |

The layered T_l reference is an independent seven-unknown linear solve written in the test file. It
shares no code with the production propagation.

### Oracle cross-check (out of tree)

The Hermes Agent A oracle (PR #409, `tools/experimental_audits/four_shell_bvp_oracle.py`) was fetched into
a scratch directory, not into the repository. It solves its own seven-equation system and projects
dipoles with its own mapping. Results on identical inputs:

| Geometry (r1, r2, r3, r4; sigma) | max rel diff, T_l, l <= 32 | max rel diff, sensor potentials (12 sensors, L = 128) |
|---|---|---|
| (0.079, 0.080, 0.085, 0.090); (0.33, 1.79, 0.0042, 0.33) | 1.5e-15 | 8e-16 |
| (0.078, 0.080, 0.086, 0.095); (0.33, 1.79, 0.0042, 0.33) (oracle default) | 1.4e-15 | 1.2e-15 |

The agreement is between two independent derivations. It is **not** validation against a physical
reference. The two implementations share the convention choices: the `V_inf` normalisation, the sign,
and the placement of the factor `l` on the radial term. Those choices are checked against the free-space
closed form and the homogeneous limit, not against a recording.

## Attribution

Næss et al. (2017), *Corrected Four-Sphere Head Model for EEG Signals*, Frontiers in Human
Neuroscience 11:490, doi:10.3389/fnhum.2017.00490. The citation is as recorded in the audit session.
The full author list and DOI were not re-checked against the publisher.

The model targets the four-sphere literature setting described in that paper. **The publisher host was refused by network policy (HTTP 403 at CONNECT), so the paper could not be
read.** The Table 1 values are as specified in the task brief and are unverified. `naess2017_table1_geometry(K)`
uses them. Its
correction details have not been checked. The equations here were derived independently and checked
numerically. They were not transcribed from the paper, and no paper result is reproduced as a
validation target.

## Licensing and provenance

- The Neuroinflab four-sphere code (repository README: GPL-3.0) was **not read, copied, adapted,
  imported, executed, or packaged**. No GPL code is a test dependency, and no GPL fixture is used.
  Its LICENSE file was not retrievable at the raw URL used (HTTP 404).
- The module, tests, and this document are new work. Licensing questions are flagged for human review.
  This is not legal advice.
- The oracle used for the cross-check is a sibling-agent file on another branch. It was run from a scratch
  copy and is not part of this change.

## Limitations

- Concentric spheres only. No gyri, sulci, skull foramina, anisotropy, electrode-cap geometry, or
  individual head shape.
- Isotropic, piecewise-homogeneous, quasi-static conduction. No capacitive or dispersive effects.
- Sensors are on the outer surface only. Source is a single point dipole in the brain shell.
- Truncation is controlled by a per-degree envelope and a geometric tail estimate. In the tested cases the
  estimate is at least the actual truncation error (checked against degree-512 references), but it is not a
  proven bound. It assumes `|T_l|` stays comparable beyond `L`, and that is not proven for layered geometries.
  A rigorous bound would also need `|T_l|` bounded for all `l`.
- Accuracy is established against closed forms, an independent 7x7 solve, and one out-of-tree oracle.
  It is not established against measured potentials.
- No scientific or biological validation is claimed. Synthetic checks support numerical correctness of
  the model only.
