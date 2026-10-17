# Round 6 Four-Shell BVP: Independent Equation Oracle

**Disposition: HOLD / SYNTHETIC_ONLY.** This is an equation-level engineering audit. It does not establish a scientific result, validate a head model against data, or test the unavailable Gemini implementation.

## Source and scope audit

The verified base is `origin/main` at `3f3fe8593303184cb88eef056c1322f3d4e57a16`. A repository search found no `forward_project_dipoles_four_shell`, four-shell implementation, or supplied radii/conductivity tuple in that base. The initial pre-creation open-PR check found 34 PRs and no owned-path conflict. A concurrent recheck found 44 open PRs, including PR #399, which adds `tools/experimental_audits/__init__.py` and `tests/experimental_audits/__init__.py`. This artifact deliberately does not add either shared `__init__.py`; its module, test, and report paths are distinct from PR #399. The latest path scan found no exact filename overlap under `tools/experimental_audits/`, `tests/experimental_audits/`, or `docs/research/batch1/`.

Relevant accessible material was not the missing implementation:

- `batch3/grok-chat-a-round6-claim-audit` at `c483aa3ea6fdca3f736c901f8867dc40cf6fe292` contains a Round 6 claim-audit document and claim-auditor test, not a forward-model module. It cites Næss et al. as a source to consult and explicitly leaves the homogeneous normalization for verification.
- Open PR #397 changes `docs/audits/batch2_round6_chain_complex_audit.md`; it is a finite chain-complex audit, not the spherical forward model.
- Open PR #388 adds a separate three-shell synthetic contract. It does not contain the stated four-shell function or parameters.
- The rechecked open-PR patches contain no `forward_project_dipoles_four_shell` symbol or complete four-radius tuple. Incidental single radius-like values occur in unrelated audits and are not evidence of this model.

The oracle below derives only from the basis and boundary conditions in the assignment plus the point-dipole Green-function expansion. It neither copies nor executes third-party code. No claim is made about how the missing proposed module maps sources, sensors, orientations, or signs.

## Boundary system and the 7×7 / 8×8 discrepancy

For degree `l >= 1`, define

\[
f_l(r)=(r/r_4)^l,\qquad g_l(r)=(r_1/r)^{l+1},
\]
\[
f'_l(r)=\frac{l}{r}f_l(r),\qquad g'_l(r)=-\frac{l+1}{r}g_l(r).
\]

Shell `k` has `Phi_k = a_k f_l + b_k g_l`. With `b1=1` fixed, the stated unknown vector is exactly

\[
x=(a_1,a_2,b_2,a_3,b_3,a_4,b_4)^T.
\]

At each of `r1`, `r2`, and `r3`, impose one potential-continuity row and one current-continuity row:

\[
\Phi_k(r_k)-\Phi_{k+1}(r_k)=0,\qquad
\sigma_k\Phi'_k(r_k)-\sigma_{k+1}\Phi'_{k+1}(r_k)=0.
\]

The seventh row is the outer zero-current condition `sigma4 * Phi4'(r4)=0`. This is six interface rows plus one outer row for seven unknowns: **the system is 7×7 when `b1` is fixed**. An 8×8 system is possible only if `b1` is added as an eighth unknown and the normalization `b1=1` is added as an eighth equation. Calling the fixed-`b1`, seven-unknown formulation “8×8” is inconsistent.

The oracle records absolute residuals and dimensionless row-scaled residuals separately for potential, current, and outer flux. The normalized basis is dimensionless; thus `sigma * dPhi/dr` is reported in normalized `S/m^2` units. Row scaling divides by the sum of magnitudes of the terms in that same equation.

## Homogeneous limit derivation

When all four conductivities are equal, interface continuity gives the same radial coefficients in every shell. Let

\[
q_l=(r_1/r_4)^{l+1}=\Phi_\infty(r_4).
\]

The outer condition gives `l*a4 - (l+1)*q_l = 0`, so `a4=((l+1)/l)q_l`. Therefore

\[
\Phi_4(r_4)=a_4+q_l=\frac{2l+1}{l}q_l,
\qquad
\frac{\Phi_4(r_4)}{\Phi_\infty(r_4)}=\frac{2l+1}{l}.
\]

This ratio is undefined at `l=0`; the dipole expansion and oracle therefore require integer `l >= 1`.

## Independently derived dipole mapping and reference

Using the sign convention

\[
V_\infty(\mathbf r)=\frac{\mathbf q\cdot(\mathbf r-\mathbf r_s)}{4\pi\sigma_1|\mathbf r-\mathbf r_s|^3}
=\frac{1}{4\pi\sigma_1}\mathbf q\cdot\nabla_{\mathbf r_s}\frac{1}{|\mathbf r-\mathbf r_s|},
\]

expand `1/|r-rs| = sum_l (rs^l/r^(l+1)) P_l(mu)` for `r > rs`. With `n_s=rs/|rs|`, `e=r/|r|`, `mu=n_s dot e`, `q_r=q dot n_s`, and `q_t=q-q_r*n_s`, differentiation with respect to the source gives the degree-`l` numerator

\[
r_s^{l-1}\left[l q_r P_l(\mu)+P'_l(\mu)(\mathbf q_t\cdot\mathbf e)\right].
\]

Let `T_l` be the shell BVP transfer ratio computed from the fixed-`b1` solution. The independently derived truncated outer-surface oracle is

\[
V_4(r_4\mathbf e)=\frac{1}{4\pi\sigma_1}
\sum_{l=1}^{L} T_l\frac{r_s^{l-1}}{r_4^{l+1}}
\left[l q_r P_l(\mu)+P'_l(\mu)(\mathbf q_t\cdot\mathbf e)\right].
\]

This source-radius and orientation mapping is the oracle's own derivation, **not a reconstruction of the missing candidate function**. The center-source limit is handled explicitly by its `l=1` value.

For the independent homogeneous reference, the known homogeneous transfer `T_l=(2l+1)/l` is summed in closed form using the Legendre generating function. With `t=rs/R` and `D=1-2*t*mu+t^2`, define

\[
A(t,\mu)=\sum_{l\ge1}(2l+1)t^{l-1}P_l(\mu),\quad
B(t,\mu)=\sum_{l\ge1}\frac{2l+1}{l}t^{l-1}P'_l(\mu).
\]

For non-endpoint `mu`,

\[
A=\frac{2t(\mu-t)D^{-3/2}+D^{-1/2}-1}{t},\qquad
B=2D^{-3/2}+\frac{(t-\mu)/\sqrt D+\mu}{t(1-\mu^2)}.
\]

The implementation uses analytic endpoint limits for `mu=±1`, high-precision scalar evaluation away from the endpoints, and a short series near `t=0`. The resulting reference is

\[
V_{hom}(R\mathbf e)=\frac{q_rA+(\mathbf q_t\cdot\mathbf e)B}{4\pi\sigma R^2},
\]

with center-dipole limit `3*q dot e/(4*pi*sigma*R^2)`. This reference does not call the 7×7 solver or the projector.

## Executed synthetic results

The executable audit uses the stated geometry `r=(0.078,0.080,0.086,0.095) m` and layered conductivities `sigma=(0.33,1.79,0.0042,0.33) S/m`.

- **Homogeneous BVP limit:** 18 cases (`l = 1,2,3,7,16,32`; three independently varied four-radius sets). Maximum absolute ratio error: `4.440892098500626e-16`; maximum relative ratio error: `2.1862853408003084e-16`. Maximum scaled boundary residual: `1.5951573428181118e-16`.
- **Layered BVP residuals:** degrees `l = 1,2,4,8,16`. Across these cases, maximum potential-continuity absolute/scaled residuals were `8.881784197001252e-16` / `1.113541961569599e-15`; maximum current-continuity absolute/scaled residuals were `4.263256414560601e-14 S/m^2` / `7.355230698709626e-15`; outer-current absolute/scaled residuals were `2.9309887850104134e-16 S/m^2` / `1.0429287414515581e-16`. Maximum row-scaled linear-system backward error: `1.713748122373993e-16`.
- **Whole oracle projector vs. independent homogeneous reference:** equal conductivities `(0.33,0.33,0.33,0.33) S/m`; seven cases across source radii `0, 0.020, 0.050, 0.070 m`, radial and tangential moments for each noncentral source, 14 synthetic surface points per case, and projector truncation `L=192`. Across 98 sensor comparisons, maximum absolute error was `1.5881867761018131e-22 V`; maximum error scaled by `|q|/(4*pi*sigma*R^2)` was `5.943914997593426e-15`.

These are arithmetic and boundary-equation checks for this oracle only. The last-degree contribution is reported but is not a certified truncation-error bound. No layered full-projector comparison to an external reference, MNE, FEM, or air-shell solver was performed.

## Input contract and limitations

- `l` / `max_degree`: positive integer; booleans and `l=0` rejected. Truncation is capped at 2048.
- `radii_m`: exactly four finite, positive, strictly increasing metre values; `r4 <= 1 m` is an explicit scale guard.
- `sigmas_sm`: exactly four finite positive S/m values. No unit conversion or inference is attempted.
- `source_position_m`: finite 3-vector strictly inside `r1`; the center is supported by the dipole `l=1` limit.
- `dipole_moment_am`: finite 3-vector in A*m.
- `sensor_positions_m`: non-empty finite `N x 3` coordinates on the `r4` sphere (tolerance `max(1e-12 m, r4*1e-9)`). All coordinates are assumed to share the same Cartesian origin and axes.
- The API cannot infer a caller's units or coordinate frame from numeric values; names, scale constraints, and the surface/source containment checks are the contract. Conductivities are checked for finiteness and positivity, not independently authenticated.
- High-degree coefficient components can be poorly conditioned even when boundary residuals and the surface transfer ratio remain small; no coefficient condition-number bound is claimed.
- The current environment has Python but no NumPy or pytest installed. No installation was attempted. The module uses NumPy's linear solver when NumPy is already available and otherwise uses its dependency-free partial-pivot solver; the executed results below use the latter. The NumPy backend was not exercised here.
- No empirical or participant data, live APIs, external datasets, or third-party code were used. No source code was copied into the repository.

## Reproduction

From the repository root:

```text
python -m tools.experimental_audits.four_shell_bvp_oracle --compact
python -m unittest discover -s tests/experimental_audits -p 'test_*.py' -v
python -m py_compile tools/experimental_audits/four_shell_bvp_oracle.py tests/experimental_audits/test_four_shell_bvp_oracle.py
```

The focused tests independently check the source-radius harmonic series against the direct free-space dipole Green function, then check the complete oracle projector against the closed-form homogeneous Neumann-sphere reference. The standard-library test run reported `Ran 10 tests ... OK`. The command output identifies `python_partial_pivot` as the active backend. Root pytest was not run because pytest and its required timeout plugin are absent, and installing them is outside this assignment's guardrails.
