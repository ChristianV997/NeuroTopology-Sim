# Full Lorentzian SU(2) Skyrme dynamics on an S3 lattice

This module is a finite-grid, dimensionless exploratory implementation of
the **full quartic-derivative Lorentzian Skyrme action** in the quaternion
representation

\[
U= n_0 I+i\,\mathbf n\cdot\boldsymbol\sigma,\qquad
n=(n_0,\mathbf n)\in S^3,\qquad |n|=1.
\]

It is deliberately distinct from a sigma-model kinetic term paired with a
static Skyrme potential: the Lorentzian time-space quartic terms are retained.
It is not a model of neurons, consciousness, collapse, psi, or rebirth.

## Action and normalization

With metric signature \((+---)\), \(v=\partial_t n\), and spatial derivatives
\(g_i=\partial_i n\), the normalization is chosen to match the repository's
static terms \(E_2=F_\pi^2/8\int\sum_i|g_i|^2\,d^3x\) and
\(E_4=1/(2e^2)\int\sum_{i<j}|g_i\wedge g_j|^2\,d^3x\):

\[
\mathcal L=
\frac{F_\pi^2}{8}\left(|v|^2-\sum_i|g_i|^2\right)
+\frac{1}{2e^2}\left[
\sum_i\left(|v|^2|g_i|^2-(v\cdot g_i)^2\right)
-\sum_{i<j}\left(|g_i|^2|g_j|^2-(g_i\cdot g_j)^2\right)
\right].
\]

Here \(|a\wedge b|^2=|a|^2|b|^2-(a\cdot b)^2\). The Hamiltonian is
\(H=T+E_2+E_4\), where

\[
T=\frac{F_\pi^2}{8}|v|^2+
\frac{1}{2e^2}\sum_i|v\wedge g_i|^2.
\]

The velocity Hessian (the local mass matrix in ambient \(\mathbb R^4\)) is

\[
M(n,g)=\frac{F_\pi^2}{4}I_4+
\frac{1}{e^2}\sum_i\left(|g_i|^2I_4-g_i g_i^\mathsf T\right),
\qquad T=\tfrac12 v^\mathsf T Mv.
\]

For \(F_\pi>0\), this matrix is positive definite. That establishes a
non-degenerate local time-kinetic form for the chosen time slicing; it does
**not** by itself establish strong hyperbolicity or causal characteristics of
the nonlinear field equations.

The action and quaternion formulation follow standard Skyrme-model
conventions; see [Battye & Sutcliffe, *Multi-soliton dynamics in the Skyrme
model*](https://arxiv.org/abs/hep-th/9610113) and [Foster & Manton,
*Scattering of Nucleons in the Classical Skyrme
Model*](https://arxiv.org/abs/1505.06843). The full equations can lose
hyperbolicity in parts of field-velocity space, a known issue rather than a
solver-specific discovery; see [Gibbons, *Causality and the Skyrme
Model*](https://arxiv.org/abs/hep-th/0302149).

## Semidiscrete equations implemented here

For each spatial site \(x\), forward-link derivatives are
\(g_i(x)=[n(x+h_i\hat e_i)-n(x)]/h_i\), with the same periodic/fixed-vacuum
link masks and the same \(E_2+E_4\) potential implementation used by
`nearest_neighbor.py`. The semidiscrete Lagrangian is the spatial sum of the
displayed density times the cell volume. Define \(K_h\) as the full kinetic
part and \(V_h=E_{2,h}+E_{4,h}\).

The kinetic-energy derivative with respect to a forward link is

\[
\zeta_i(x)=\frac{1}{e^2}\left(|v(x)|^2g_i(x)
-(v(x)\cdot g_i(x))v(x)\right),
\]

and therefore its field derivative includes both outgoing and incoming links:

\[
\nabla_{n(x)}K_h=
\sum_i\frac{\zeta_i(x-h_i\hat e_i)-\zeta_i(x)}{h_i}.
\]

Let \(\dot g_i=D_i v\). The velocity-dependent term in the Euler-Lagrange
equation is

\[
(\dot Mv)(x)=\frac{1}{e^2}\sum_i\left[
2(g_i\cdot\dot g_i)v
-\dot g_i(g_i\cdot v)
-g_i(\dot g_i\cdot v)\right].
\]

Including optional generalized Rayleigh drag \(-\gamma Mv\), the constrained
equation is

\[
Ma+\dot Mv-\nabla_nK_h+\nabla_nV_h
=\lambda n-\gamma Mv,
\qquad n\cdot n=1,\quad n\cdot v=0,\quad n\cdot a=-|v|^2.
\]

The code solves this local multiplier system at each active site; frozen
boundary and user-pinned sites remain fixed. It uses the analytic gradient of
the repository's discrete \(V_h\), not a separately chosen potential. In the
vacuum linearization, the forward-link dispersion is

\[
\omega^2=4\sum_i\frac{\sin^2(k_i h_i/2)}{h_i^2},
\]

because the \(E_4\) contribution is fourth order in small pion amplitude.
This gives a vacuum-only reference frequency; it does not replace a nonlinear
stability/hyperbolicity analysis.

## Numerics, bounds, and interpretation

`evolve_lorentzian_skyrme` uses projected classical RK4 on the field and
velocity after each stage. Projection keeps the \(S^3\) constraint and
velocity tangency within roundoff, but RK4 is not symplectic and does not
conserve the discrete Hamiltonian exactly. The regression tests require
energy error to decrease under timestep refinement on a small smooth field.
When damping is enabled, the reported accumulated work is

\[
D(t)=\int_0^t\gamma\,\Delta V\sum_x v(x)^\mathsf T M(x)v(x)\,dt,
\]

and the reported balance residual is \(H(t)+D(t)-H(0)\). It is numerical
mechanical dissipation for this model, not a measured thermodynamic entropy
production.

The explicit-step preflight reports
\(\Delta t\,2\sqrt{\sum_i h_i^{-2}}\) and rejects values above the declared
vacuum-linearized RK4 limit (default 2.5). Nonlinear backgrounds can have
different characteristic speeds; the indicator is not a nonlinear CFL
proof. Grid nodes, step count, saved snapshot count, and estimated snapshot
bytes are capped before evolution. Numerical failure raises rather than
returning a partial trajectory marked complete.

All coordinates, times, and couplings are dimensionless by default. A
physical calibration would require explicit unit conversions, a chosen
physical parameter regime, continuum/grid-refinement studies, and an
independent hyperbolicity diagnostic. This implementation can explore
formation from chosen initial data, deformation, collisions, radiation, and
approximate topological-charge behavior. It does not imply that solitons form
spontaneously: conservative evolution needs specified initial conditions,
and any relaxation/formation mechanism needs explicit damping or energy flow.

## Validation included

The focused test file checks: static-energy normalization against the existing
nearest-link objective; nonzero time-space \(E_4\) kinetic energy and its
constant-field limit; the analytic vacuum dispersion; \(S^3\) norm and
tangency; energy-error reduction under timestep refinement; damped energy
balance; frozen boundaries and pinned sites; invalid initial velocities;
and preflight snapshot/CFL bounds. These are software and discretization
checks on tiny synthetic grids, not a physical validation of the Skyrme model.

Next useful numerical gates are: random-state finite-difference checks of the
full semidiscrete Euler-Lagrange residual; higher-order temporal convergence;
grid refinement for the dynamical solution and charge diagnostic; a numerical
principal-symbol/hyperbolicity screen; then collision observables initialized
from independently converged static solitons rather than unrelaxed hedgehog
profiles.

