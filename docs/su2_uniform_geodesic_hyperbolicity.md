# Uniform-geodesic transverse principal-symbol screen

`field_theory.su2.hyperbolicity.analyze_uniform_geodesic_transverse_symbol`
is an analytic screen for one restricted continuum background of the
dimensionless Lorentzian Skyrme model. It is not part of the numerical time
integrator and it does not certify arbitrary solver trajectories.

## Background and result

The screen assumes an exact spatially homogeneous geodesic on (S^3),

\[
n(t)=\cos(ut)n_0+\sin(ut)\widehat V_0,\qquad
|n_0|=|\widehat V_0|=1,\qquad n_0\cdot\widehat V_0=0,
\]

with zero spatial gradients (G_i=0), no damping, and positive dimensionless
couplings (F_\pi,e). For transverse perturbations orthogonal to the geodesic
plane, the quadratic Lagrangian density is

\[
\mathcal L^{(2)}_\perp=
\frac{F_\pi^2}{8}\left(
|\dot\eta|^2-u^2|\eta|^2-|\nabla\eta|^2
\right)
+\frac{u^2}{2e^2}|\nabla\eta|^2.
\]

Consequently the linearized equation has the lower-order curvature term

\[
\ddot\eta+u^2\eta-c_\perp^2\nabla^2\eta=0,
\qquad
c_\perp^2=1-\frac{4u^2}{e^2F_\pi^2}.
\]

For a plane wave, the full finite-wavenumber dispersion is
\(\omega^2=u^2+c_\perp^2|\xi|^2\). The API returns the **principal** roots
\(\omega/|\xi|=\pm\sqrt{c_\perp^2}\), not the full finite-wavenumber
frequencies. If \(c_\perp^2<0\), the principal roots are non-real; the
finite-wavenumber mode becomes exponentially growing only when
\(|\xi|^2>u^2/|c_\perp^2|\). A finite lattice may not contain such a mode.

The critical speed is \(u_\mathrm{crit}=eF_\pi/2\). At the threshold the
transverse principal spatial coefficient vanishes, even though the
finite-wavenumber dispersion retains the \(u^2\) term. For \(F_\pi=e=1\):

| (u) | (c_\perp^2) | Principal roots | Finite-(|\xi|) \(\omega^2\) |
|---:|---:|---|---|
| 0.4 | 0.36 | (\pm 0.6) | (0.16+0.36|\xi|^2) |
| 0.5 | 0 | (0,0) | (0.25) |
| 0.6 | -0.44 | (\pm i\sqrt{0.44}) | (0.36-0.44|\xi|^2) |

At zero spatial gradient the repository's local velocity Hessian is
\(M=F_\pi^2 I_4/4\), which is positive definite. Thus this restricted
example demonstrates why positivity of the time-kinetic Hessian alone does
not guarantee real transverse principal roots.

## API scope and numerical classification

The function accepts one real four-vector `field` and one real four-vector
`velocity`, not spatial arrays or a trajectory. It rejects non-finite values,
non-unit fields, non-tangent velocities, and non-positive or unrepresentable
couplings. The documented small constraint tolerances accommodate floating-
point representation; accepted velocity residuals are used as supplied (no
projection or input mutation).

The reported `normalized_time_gradient` is
\(\chi=2|V|/(eF_\pi)\), and the unrounded margin is
\(c_\perp^2=1-\chi^2\). Classification uses
\[
\tau=64\,\epsilon_\mathrm{mach}\max(1,\chi^2)
\]
only to resolve the floating-point sign near zero. It is not a physical
uncertainty band. The result's `full_system_hyperbolicity_status` is always
`not_assessed`.

This analytic screen does not establish strong hyperbolicity for arbitrary
time-dependent or inhomogeneous fields, convergence of the finite-grid
integrator, nonlinear stability, or physical calibration. It also does not
change the trajectory solver's existing `hyperbolicity_status="not_certified"`.

