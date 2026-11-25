# Næss et al. (2017) Four-Sphere BVP: Independent Oracle

**Disposition: HOLD / SYNTHETIC_ONLY.** This is an independent numerical check of the paper’s equations using synthetic inputs. It is not empirical or biological validation and does not validate a production engine.

## Scope and sources

Primary source: Næss, S., Chintaluri, C., Ness, T. V., Dale, A. M., Einevoll, G. T., & Wójcik, D. K. (2017). *Corrected Four-Sphere Head Model for EEG Signals*. Frontiers in Human Neuroscience, 11:490. [doi:10.3389/fnhum.2017.00490](https://doi.org/10.3389/fnhum.2017.00490) · [open full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC5651266/).

The paper states that its article is distributed under a Creative Commons Attribution license (CC BY). This artifact attributes the paper and DOI above. The paper separately identifies its accompanying Neuroinflab/fourspheremodel implementation as GPL-3.0. **No code from that implementation was copied, adapted, imported, executed, or packaged; LFPy and other GPL runtime/test dependencies were not used.** This is a provenance statement, not legal advice; any licensing question about equation expression or downstream use remains for human review.

`origin/main` was re-fetched at `19c3203573082f8bc41f7da226b52dc20a49fdb0`. A separate four-shell implementation now exists in open draft PR #418 (`physics/eeg_forward/four_sphere.py`). This oracle deliberately does not import, execute, or compare against that candidate. Round 6/Gemini claims are therefore still unverified by this artifact. PR #399 owns shared experimental-audit namespace initializers; this work changes no shared `__init__.py`.

## Paper parameters and conventions

The defaults follow Næss et al. Table 1 and Figure 1/Figure 2, not the alternative prompt tuple:

| Quantity | Paper-derived value / convention |
|---|---|
| Layer order | brain (1), CSF (2), skull (3), scalp (4) |
| Radii | `(0.079, 0.080, 0.085, 0.090) m` |
| Conductivities | `σ1=0.33`, `σ2=5σ1=1.65`, `σ3=σ1/K`, `σ4=σ1` S/m; `K∈{20,40,80}` |
| Skull conductivity by K | `0.0165`, `0.00825`, `0.004125` S/m for K 20, 40, 80 |
| Figure source | `r_z=0.078 m` on +z, 1 mm inside the paper’s `r1=0.079 m` brain/CSF boundary |
| Figure dipole moment | `10^-7 A·m`; radial +z, tangential +y, and 45° from +z in the x=0 plane |
| Coordinates and units | shared Cartesian origin/axes; radii, positions, and sensors in m; conductivity S/m; moment A·m; output V |
| PDE sign | `∇·(σ∇Φ) = -C`; free-space dipole sign `q·(r-r_s)/(4πσ|r-r_s|³)` |
| Interfaces | potential and `σ ∂Φ/∂r` continuous at r1, r2, r3 |
| Scalp boundary | `∂Φ4/∂r(r4)=0` (equivalently `σ4∂Φ4/∂r=0` since σ4>0) |

The supplied alternative values `(0.078,0.080,0.086,0.095) m` and `(0.33,1.79,0.0042,0.33) S/m` are recorded separately in the machine audit as prompt-proposal parameters, not Næss Table 1. In particular, using `r_z=0.078 m` with that tuple’s `r1=0.078 m` would put the source on the boundary; the paper’s `r_z=0.078 m` is valid only with its `r1=0.079 m`.

### Angular and tangential convention

For a source at `r_s=r_z n` and scalp sensor `r=R e`, set `μ=n·e`, `q_r=q·n`, and `q_t=q-q_r n`. The Legendre polynomials are the ordinary `P_l(μ)`. The associated Legendre convention is Condon–Shortley:

\[
P_l^1(μ)=-\sqrt{1-μ^2}\,P_l'(μ).
\]

For the paper’s source on +z and tangential dipole `q=+p y`, use the standard spherical sensor azimuth φ, so `q_t·e=p sinθ sinφ`. Then the paper’s tangential factor `-p sinφ P_l^1(μ)` equals `(q_t·e)P_l'(μ)`. This sign relation and both scalp-axis symmetry cases are tested explicitly.

## Independent boundary-system derivation

Næss Eqs. 5–6 express each radial harmonic, before its angular and physical prefactors, with the source-fixed brain-shell term and shell-scaled regular/singular terms:

\[
\begin{aligned}
U_{1l}(r)&=A_{1l}(r/r_1)^l+(r_z/r)^{l+1}, && r_z<r\le r_1,\\
U_{sl}(r)&=A_{sl}(r/r_s)^l+B_{sl}(r_s/r)^{l+1}, && s=2,3,4.
\end{aligned}
\]

The paper’s radial potential multiplies these terms by `p/(4πσ1 r_z²) · l P_l(cosθ)`; the tangential potential uses the same shell coefficients with `-p sinφ P_l^1/(4πσ1 r_z²)`. The oracle independently assembles the boundary-value matrix from this basis; it does not implement the paper’s coefficient recurrences or use third-party code.

For each integer `l≥1`, the unknown vector is

\[
x=(A_{1l},A_{2l},B_{2l},A_{3l},B_{3l},A_{4l},B_{4l})^T.
\]

There are two equations at each of r1, r2, r3 (potential and current continuity) and one scalp Neumann equation. Thus the paper basis with its brain singular-source coefficient fixed to 1 has **seven unknowns and a 7×7 system**. The earlier normalized transfer basis likewise fixes `b1=1` and is 7×7. An 8×8 system is mathematically possible only if that source coefficient becomes an eighth unknown and an eighth normalization equation is added; an 8×8 label without that extra unknown/row is inconsistent.

For the paper-basis mode, the surface transfer is computed as

\[
T_l=\frac{A_{4l}+B_{4l}}{(r_z/r_4)^{l+1}}.
\]

The coefficient-scale-independent normalized solver gives the same transfer ratio. The homogeneous conductivity limit independently follows from the scalp derivative condition: `T_l=(2l+1)/l`. Its `l=0` case is outside the dipole expansion and rejected.

The projector follows by differentiating the free-space Legendre expansion with respect to source position and multiplying each mode by `T_l`:

\[
V(R e)=\frac{1}{4πσ_1}\sum_{l=1}^{L}T_l\frac{r_z^{l-1}}{R^{l+1}}
\left[lq_rP_l(μ)+(q_t·e)P_l'(μ)\right].
\]

At `r_z=0`, the implementation takes the explicit `l=1` dipole limit. The independent homogeneous reference sums the known homogeneous transfer using the Legendre generating function; its radial branch is also checked directly against Næss Eq. 19. No candidate engine is imported by the public comparison API:

`compare_surface_potentials(reference_v, candidate_v, scale_v=...)`

It requires equal non-empty finite vectors and an explicit positive scale in volts, and returns maximum/RMS absolute and scaled errors. A future caller can supply a candidate output vector without importing the oracle’s private solver or triggering candidate execution.

## Synthetic execution results

Commands and detailed outputs are reproduced under **Verification**. All runs use the standard-library partial-pivot backend (`python_partial_pivot`); NumPy was unavailable and was not installed.

| Check | Cases | Result |
|---|---:|---|
| Homogeneous BVP transfer, `T_l=(2l+1)/l` | 24 (l = 1, 2, 3, 7, 16, 32; four independently varied radius sets) | max absolute ratio error `4.440892098500626e-16`; max relative error `2.1862853408003084e-16`; max scaled boundary residual `1.5951573428181118e-16` |
| Paper-basis layered boundary solve | 15 (K = 20, 40, 80; l = 1, 2, 4, 8, 16; source r_z = 0.078 m) | max scaled interface/scalp residual `5.310349927144369e-15`; max current-continuity absolute residual `2.1316282072803006e-14 S/m²`; max potential-continuity absolute residual `1.1102230246251565e-15`; max outer-current absolute residual `5.861977570020827e-16 S/m²`; max row-scaled linear backward error `1.9526783304133182e-16`; max row-equilibrated infinity condition estimate `399.05080596211224` |
| Source-depth law, `U4/r_z² ∝ r_z^(l-1)` | 5 degrees, depths 0.020, 0.050, 0.078 m | max relative ratio error `2.650988938382845e-16` |
| Full homogeneous dipole projector vs independent closed-form reference | 10 source/orientation cases × 14 sensors = 140 comparisons; source radii 0, 0.020, 0.050, 0.078 m; radial, tangential, tilted 45° | max absolute error `8.673617379884035e-19 V`; max scaled error `2.913460154742836e-13` |
| Radial homogeneous special case vs paper Eq. 19 | 5 polar angles, r_z = 0.078 m | test threshold `max scaled error <2e-12`; passed |
| Tangential Legendre sign and axis symmetry | 5 angular positions including ±z axis; L=512 | test threshold `max scaled error <2e-12`; both axis potentials `<1e-18 V`; passed |

Harmonic truncation for a radial source at r_z=0.078 m and +z scalp sensor, relative to the independent homogeneous closed form:

| L | Max scaled error |
|---:|---:|
| 8 | 76.38850098802013 |
| 16 | 36.47001926997962 |
| 32 | 6.15769585904 |
| 64 | 0.11375165487706224 |
| 128 | 2.263070579426106e-5 |
| 256 | 1.456730077371418e-13 |
| 512 | 2.913460154742836e-13 |

The rapid decay reaches floating-point scale by L=256; the slight 256→512 increase is roundoff, not a certified tail bound. The reported last harmonic is diagnostic only. Finite values, input shapes/units, source containment, interface residuals, symmetry-axis cases, and conditioning diagnostics are covered; a small residual or homogeneous agreement does not authenticate parameters or establish empirical correctness.

## Input contract, limitations, and provenance boundary

- `l` is a positive integer (bool and l=0 rejected); `1≤L≤512`.
- Four finite positive strictly increasing radii in metres; `r4≤1 m` and its surface dipole normalization `1/r4²` must be finite. Four finite positive conductivities in S/m; no conversion or inference.
- Paper-basis source requires `0<r_z<r1`; central dipole uses the explicit l=1 limit. Dipole moment is a finite 3-vector in A·m.
- Sensors are a non-empty finite `N×3` array on the scalp sphere r4 (tolerance `max(1e-12 m, r4·1e-9)`). All coordinates share one Cartesian frame.
- Boundary current residuals are `σ·dU/dr` in normalized `S/m²`; scaled residuals divide by the sum of magnitudes of row terms. Conditioning is the infinity-norm condition estimate after equation-row equilibration; it is diagnostic, not a universal accuracy guarantee.
- Coefficient components may be poorly conditioned at high degree even where surface transfer and boundary residuals are small. L truncation is not a certified error bound, especially for a source close to r1.
- No participant data, EEG datasets, dataset downloads, live APIs, external FEM/MNE comparator, or third-party implementation was used. No scientific, clinical, biological, or production-candidate validation is claimed.

## Verification

Executed in the isolated `batch1/hermes-a-shell-bvp-oracle` worktree:

```text
python -m unittest discover -s tests/experimental_audits -p 'test_*.py' -v
Ran 17 tests in 6.167s — OK

python -m py_compile tools/experimental_audits/four_shell_bvp_oracle.py tests/experimental_audits/test_four_shell_bvp_oracle.py
exit 0

python -m tools.experimental_audits.four_shell_bvp_oracle --compact
status: HOLD / SYNTHETIC_ONLY; solver_backend: python_partial_pivot; finite JSON
```

The NumPy backend was not exercised because NumPy was unavailable; no dependencies were installed. The independent standard-library checks ran successfully. This report does not claim the full repository suite or GitHub Actions is green; PR #409’s current required Awareness test failure is tracked separately in the handoff.
