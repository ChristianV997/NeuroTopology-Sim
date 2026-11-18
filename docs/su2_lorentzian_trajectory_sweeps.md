# Lorentzian SU(2) trajectory sweeps and visualization

This layer composes the finite-grid Lorentzian solver with bounded, reproducible
parameter sweeps and optional headless plots. It adds no new field equations.
Outputs remain dimensionless engineering diagnostics. A future unit conversion
could assign units, but would not validate the field equations, parameter mapping,
or initial and boundary conditions as a physical model.

## What is swept

LorentzianSweepSpec forms a bounded Cartesian product over \(F_\pi\), \(e\),
Rayleigh damping \(\gamma\), and timestep \(\Delta t\), while holding one input
field, velocity, grid, and final integration time \(T\) fixed. For every
timestep, \(T/\Delta t\) must be an integer within a strict floating-point
tolerance. Therefore the dt axis is a temporal-resolution comparison at a
common horizon, not a different-duration experiment.

The sweep records scale proxies motivated by the static energy scaling:
\(\lambda=e f_\pi\) and \(\mu=f_\pi/e\), with
\(\bar h_i=\lambda h_i\), \(\bar L_i=\lambda L_i\),
\(\bar{\Delta t}=\lambda\Delta t\), and
\(\bar\gamma=\gamma/\lambda\). These are descriptive nondimensional
combinations, not calibrated physical scales. Since this first sweep keeps
the input grid and profile fixed, varying \(\lambda\) changes their
dimensionless geometry; it does not perform the resampling needed for a
controlled fixed-dimensionless-geometry comparison.

The model-parameter axes are caller-defined and have no empirically calibrated
ranges. An illustrative exploration might use a few dimensionless values
around a baseline; those values must not be interpreted as biological or
physical estimates. The package does not yet vary spatial resolution or
initial-condition families in one sweep. Separate grid-refinement and
independently relaxed initial-soliton studies remain necessary.

## Work, memory, and failure behavior

Before the first evolution call, the runner checks the number of points,
aggregate RK workload, per-point saved-snapshot bytes, grid size, initial
velocity shape/finiteness/tangency, and the vacuum-linearized CFL indicator.
The deterministic RK work proxy is

\[
W_{\mathrm{sweep}}
=4N_{\mathrm{sites}}
\left(\prod_{a\in\{F_\pi,e,\gamma\}}N_a\right)
\sum_{\Delta t}N_{\mathrm{steps}}(\Delta t),
\qquad
N_{\mathrm{steps}}(\Delta t)=T/\Delta t.
\]

It is capped at 40,000,000 stage-site evaluations by default. The aggregate work cap is paired with a deterministic diagnostic record-site
budget of 40,000,000 visits, since every recorded frame performs whole-grid
diagnostics. Each underlying trajectory is saved at no more than 32 frames and
is subject to a 128 MiB snapshot-byte cap. The RK work estimate is \(4\sum_jN_jT_j\); the diagnostic record-site
estimate is \(\sum_jN_jS_j\), where \(S_j\) is the number of saved states.
These are deterministic resource bounds, not wall-time guarantees. A failed point raises; the runner does not return a partial sweep
as if it completed.

Full field arrays are intentionally not stored in sweep results. Each point
retains compact time series for energy terms, damping work, balance residual,
approximate charge, local kinetic-matrix diagnostics, input hashes, and a
final-field hash. This keeps serialized results small. The hashes identify
array content but do not authenticate the source code or physical model.

## Example

    from field_theory.su2 import LorentzianSweepSpec, run_lorentzian_sweep

    spec = LorentzianSweepSpec(
        f_pi_values=(1.0,),
        e_values=(1.0,),
        damping_values=(0.0, 0.1),
        dt_values=(0.001, 0.002),
        final_time=0.01,
    )
    result = run_lorentzian_sweep(initial_field, initial_velocity, spec)
    result.write_json("outputs/su2/trajectory-sweep.json")

The example axes are illustrative dimensionless values. In this four-point
sweep, each dt must divide the same final_time; other parameters are fixed
when drawing a one-axis curve. For example, set dt_values=(0.001,) to compare
damping values using x_parameter="damping".

## Visualization

plot_lorentzian_sweep(result, destination, x_parameter=...) overlays total
model-energy and approximate-charge histories for one varied axis. The
Matplotlib-free build_lorentzian_sweep_plot_data function provides the same
validated data for other front ends. Confounded multi-axis results are rejected
rather than silently treated as a one-parameter response.

For a single full trajectory, plot_lorentzian_trajectory shows energy
components, accumulated damping work, energy-balance residual, approximate
charge, and local kinetic-matrix diagnostics. plot_lorentzian_field_slices
renders a bounded sequence of 2D slices of one of the four unit-quaternion
components. The sweep stores no fields, so rerun a selected parameter point
with evolve_lorentzian_skyrme to produce such a field montage.

Matplotlib is optional and imported only by render functions. All renderers
use the Agg canvas directly and do not mutate a global plotting backend.

## Interpretation limits and next numerical gates

A declining energy under nonzero damping is expected from the chosen model; it
is not evidence for biological relaxation, thermodynamic entropy production,
enlightenment, or persistence. The finite-grid charge is approximate and is
not guaranteed to be integer-valued or conserved under the implemented open
boundaries and discretization. The pure-decay RK4 screen uses a conservative default \(\gamma\Delta t\le2.5\);
it is not a complete stability test for damped oscillatory modes. A positive
local kinetic matrix, this damping screen, and an acceptable vacuum CFL
indicator do not certify nonlinear hyperbolicity.
These figures visualize solver outputs; they do not validate continuum
convergence or physical relevance.

Next high-value numerical work is (1) temporal-order estimation using at least
three timesteps, (2) spatial grid-refinement of matched initial data, (3)
numerical screening of the principal symbol/hyperbolicity, and (4) collision
runs initialized from independently relaxed configurations rather than raw
hedgehog ansatz fields.
