# Four-shell EEG forward model (`physics/eeg_forward/four_sphere.py`)

Status: **HOLD / SYNTHETIC_ONLY**. Experimental. Engineering model of a dipole in an idealised,
concentric, piecewise-homogeneous head. It is not individual anatomy, has not been validated against
recordings, and supports no biological, clinical, or diagnostic claim. Nothing here uses participant
data, EEG datasets, or dataset downloads.

## What is established

| Level | Status |
|---|---|
| Implemented | `physics/eeg_forward/four_sphere.py`, NumPy only |
| Unit-tested | `tests/physics/eeg_forward/test_four_sphere.py`: 90 offline tests pass, 1 skipped (the oracle test, by design; see the oracle section). Counts are from the head commit, so re-run to confirm. |
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

Nodal sensors. Sensors at the ten roots of P_10 (found by a sign scan and bisection, independent of the
production code) are tested with a radial dipole. The degree-10 term is exactly zero there, so a rule that
stopped on a vanishing term would end the sum early. The tail estimate still bounds the actual error against
a degree-512 reference, and a 10-term cut is measurably wrong at those sensors.

Estimator attack, scratch. Across K = 20, 40, 80; depths 0 to 0.95 r1; radial, tangential, and 45-degree
dipoles; P_10 nodal sensors; and L = 32, 64, 128, 256, the estimate was never below the actual error against a
degree-512 reference. The smallest estimate-to-actual ratio was 5.5. This is evidence for the tested family,
not a proof.

**Certification status: uncertified.** Every bound above is conditional on `|T_l|` remaining comparable beyond
`L`, which is not proven. No certified maximum degree is claimed.

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

### Oracle cross-check (combined worktree, not a repository test)

The Hermes Agent A oracle (PR #409, `tools/experimental_audits/four_shell_bvp_oracle.py`) was run from a
disposable combined worktree: the candidate head `330f8f6` merged with oracle head `7ccc59a`, merge base
`19c3203`. Neither lane's files were edited. The oracle's own 17 unit tests pass in that tree, and the
candidate's 72 pass with 1 skipped. Both implementations were imported from that tree. The oracle's
`solve_four_shell_mode` and `project_dipole_oracle` supplied all expectations.

Table 1 preset, K = 20, 40, 80 (brief values), 96 cases in total:

| Sweep | Max rel diff |
|---|---|
| `T_l`, l <= 48 | 1.5e-15 |
| Sensor potentials, L = 256; depths 0 to 0.95 r1; radial, tangential, 45-degree dipoles; sensors at P_10 nodal angles and random points | 2.9e-15 |

The agreement is between two implementations that use the same brief values and share the convention
choices: the `V_inf` normalisation, the sign, and the placement of the factor `l` on the radial term. It is
**not** validation against the paper, whose Table 1 and equations were not readable in this session. It
does not validate a recording either.

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
- A tangential dipole queried only at the poles has exactly zero potential. The tail envelope uses `|q_t|`
  rather than the sensor-specific `|q_t . e|`, so the call is refused as "truncation tail estimate inf"
  instead of returning zero. The refusal is fail-closed. Changing it would change the envelope, which other
  test lanes check against.
- Unresolved provenance question. The task brief gives CSF conductivity 1.65 S/m and skull 0.33/K. A
  search-result snippet, not the paper, describes CSF equal to the brain value (0.33 S/m) and skull equal to
  brain/K. The paper could not be read, so neither reading is verified. The two readings change T_1 by about
  9% at K = 40 (2.437 vs 2.654) and sensor potentials by about 9%. The owner must resolve this from the
  paper's Table 1 before any result is tied to the literature.
- No scientific or biological validation is claimed. Synthetic checks support numerical correctness of
  the model only.
