# Local SU(2) Skyrme characteristic-symbol screen

The function
`field_theory.su2.local_symbol.analyze_local_skyrme_principal_symbol`
is a continuum, one-point, one-spatial-direction diagnostic for a local field 1-jet. It is separate from the Lorentzian lattice integrator and does not certify strong hyperbolicity of the full PDE or the finite-difference scheme.

## Action and tangent symbol

For the repository's dimensionless quaternion field `n` in S3 and metric signature (+---), the derivative Lagrangian is

\[
\mathcal L =
\frac{F_\pi^2}{8}\left(|V|^2-\sum_i|G_i|^2\right)
+\frac{1}{2e^2}\left[
\sum_i\bigl(|V|^2|G_i|^2-(V\cdot G_i)^2\bigr)
-\sum_{i<j}\bigl(|G_i|^2|G_j|^2-(G_i\cdot G_j)^2\bigr)
\right].
\]

At one point, `V = ∂t n` and `G_i = ∂i n` are required to lie in `T_n S3`. Let `E` be an orthonormal four-by-three tangent frame and use tangent coordinates `v = EᵀV`, `g_i = EᵀG_i`. Define, for three-vectors `q`,

\[
W(q)=|q|^2 I_3-qq^\mathsf T,
\qquad
K(a,b)=ab^\mathsf T+ba^\mathsf T-2(a\cdot b)I_3.
\]

For a unit spatial covector `d = ξ/|ξ|` and phase speed `s=ω/|ξ|`, the tangent principal pencil is

\[
\mathsf P(s,d)=A s^2-D(d)s+C(d),
\]

where

\[
\begin{aligned}
A &= \frac{F_\pi^2}{4}I_3+\frac1{e^2}\sum_i W(g_i),\\
D(d)&=\frac1{e^2}\sum_i d_i K(g_i,v),\\
C(d)&=-\frac{F_\pi^2}{4}I_3
+\frac1{e^2}\sum_i d_i^2 W(v)
-\frac1{e^2}\sum_{i<j}W(d_i g_j-d_j g_i).
\end{aligned}
\]

The six returned speeds, counted with algebraic multiplicity, are obtained from the companion linearization of `det P(s,d)=0`. The implementation whitens the positive time block by Cholesky factorization before forming the six-by-six companion matrix. A non-real root is evidence against real characteristics for that local jet and that direction. The result never promotes the solver's `not_certified` status.

## Normalization checks and a mixed-gradient counterexample

In vacuum, `V=G_i=0`, the pencil is `(F_pi^2/4)(s^2-1)I_3`; the roots `-1,+1` each have multiplicity three. With `G_i=0` and `V=u e_1`, one polarization pair remains `±1` and the other two pairs are

\[
s=\pm\sqrt{1-\frac{4u^2}{e^2F_\pi^2}},
\]

recovering the separate homogeneous-geodesic screen already in `hyperbolicity.py`.

A new mixed-gradient check uses `V=v e_1`, `G_1=g e_1`, and `G_2=G_3=0`. Each transverse polarization obeys

\[
\left(\alpha+\beta g^2\right)s^2+2\beta vg\,s-\alpha+\beta v^2=0,
\qquad
\alpha=F_\pi^2/4,\quad \beta=e^{-2}.
\]

Its discriminant is

\[
\Delta=4\alpha\left(\alpha+\beta g^2-\beta v^2\right),
\]

so this direction has non-real transverse speeds when

\[
v^2>g^2+\left(\frac{eF_\pi}{2}\right)^2.
\]

For `F_pi=e=1, g=1, v=1.2`, the roots are `-0.96 ± 0.17436 i` (each twice), alongside the longitudinal `±1` pair. This is a dimensionless model counterexample, not a calibrated physical parameter claim. The background `n=(cos(v t+g x), sin(v t+g x),0,0)` has collinear derivatives; its Skyrme wedge density vanishes, while its transverse perturbations still feel the mixed principal coefficients.

At the discriminant-zero boundary `v=sqrt(g^2+(e*F_pi/2)^2)`, each transverse polynomial has a repeated root `s=-beta*v*g/(alpha+beta*g^2)`. For `F_pi=e=g=1`, this is `s=-sqrt(1.25)/1.25`; the companion eigenbasis is defective, so the diagnostic should return `numerically_unresolved`. The exact mixed-threshold regression tests that behavior.

## Numerical and epistemic contract

- The function accepts exactly one field value, one velocity, three spatial derivative rows, and one nonzero spatial covector. It is not a trajectory-array API.
- Shape, finite-real dtype, S3 normalization, derivative tangency, and positive finite couplings are validated. Boolean elements are rejected before NumPy can coerce mixed Boolean/numeric sequences; complex, object, and string inputs are rejected.
- Tangency residuals within a relative `1e-10` tolerance are explicitly projected away and the maximum original residual is returned; larger violations are rejected. Inputs are copied and not mutated.
- The spatial covector is normalized stably, so positive rescaling does not change the returned speeds.
- Coupling-weighted `W` and `K` entries, plus the scaled spatial area-gradient components, are accumulated as exact rational expressions of the input float64 values and rounded once to float64. This prevents raw-product underflow and severe cancellation inside those local coefficients from erasing a representable result. Subsequent block additions, matrix whitening, and eigensolving remain float64; this is not an end-to-end arbitrary-precision guarantee. A nonzero local coefficient that is itself unrepresentable is rejected rather than silently erased. Regressions preserve `1e-100` entries alongside `1e300`, exercise area-gradient underflow through the public diagnostic, and retain a small residual after large mixed-term cancellation.
- Root imaginary-part checks use each root's own scale, so a large root cannot set the tolerance for every smaller root. The exposed scalar `root_classification_tolerance` reports the maximum of the per-root machine tolerances; it is informational and is not a shared cutoff.
- If the companion eigenbasis is ill-conditioned, imaginary splittings no larger than `16*sqrt(machine epsilon)*max(1, |s|)` are reported as numerically unresolved. Because of the `max(1, |s|)` term, this guard has an absolute floor for roots with magnitude below one. It is a heuristic sensitivity guard, not a certified eigenvalue error bound; clearly resolved complex roots remain flagged.
- A finite set of local states or directions can discover a counterexample. It cannot prove real roots for all covectors, completeness of a uniform eigenbasis, strong hyperbolicity, nonlinear stability, solver convergence, or physical calibration.
- The continuum local symbol is not the exact principal analysis of the finite-difference lattice. Lattice snapshots require a separately justified tangent-derivative reconstruction before being passed to this API.
- No consciousness, biological, enlightenment, psi, or rebirth inference follows from this numerical model.
