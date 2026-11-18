# SU(2)/Skyrme solver I/O inspection (experiment-layer notes)

Inspected live against draft PRs (read-only; this branch does **not** checkout
those PR branches):

| Ref | PR | Head (at inspection) | Role |
|---|---|---|---|
| `codex/su2-constrained-pair-relaxation-20261117` | [#466](https://github.com/ChristianV997/NeuroTopology-Sim/pull/466) | `a7d540592f2eed8beadcb88c3e7d1e702909e0d3` | Static nearest-neighbor relax, constrained pair, built-in `parameter_sweep` |
| `codex/su2-lorentzian-skyrme-dynamics-20261117` | [#468](https://github.com/ChristianV997/NeuroTopology-Sim/pull/468) | stacked on #466 | Full Lorentzian Skyrme evolution |

On base branch `antigravity/missingness-and-cohorts-20261016`, `field_theory/su2/`
is **absent** (it exists on `origin/main`). The experiment layer therefore ships
an isolated adapter and records `solver_unavailable` unless the solver package
is present or `--allow-stub` is used for contract smoke tests. Prefer merging
`origin/main` into the experiment branch before claiming live dual-path coverage;
the adapter filters kwargs/result attrs so the thinner main foundation and the
richer PR #466 API both work without inventing missing residual fields.

## Public solver inputs (from PR #466 / #468)

### Field / IC

- `SU2GridField(components, spacing, boundary, length_unit)`
  - components: `(nx,ny,nz,4)` unit four-vectors
  - boundary: `fixed_vacuum` | `periodic`
  - length_unit: nonempty string (usually `dimensionless`)
- Generators: `vacuum`, `hedgehog`, `fixed_axis`, `multi_hedgehog`
  - Experiment schema currently accepts **`vacuum`** and **`hedgehog` only**
  - `multi_hedgehog` / `fixed_mask` labeled **unavailable** in this layer

### Static relax (`relax_skyrme_field_nearest_neighbor`)

Inputs: `f_pi`, `e`, `max_iterations`, `initial_step`, `gradient_tolerance`,
`max_backtracks`, optional `fixed_mask`, `stationarity_metric`, `descent_metric`.

Outputs (`NearestNeighborRelaxationResult`): energy/charge histories, termination,
stationarity status, curvature probe (nullable), gradient residuals, cell volume,
active site count. `minimum_certified` is a solver boolean (expected false for
scientific claims).

### Built-in solver sweep (`parameter_sweep.run_nearest_neighbor_sweep`)

Exists on PR #466 with schema `1.1.0` and axes `inverse_length_scale`,
`energy_prefactor`, dimensionless step / iterations. This experiment layer does
**not** re-implement that scale algebra; it provides a separate, smaller config
contract (`f_pi`, `e`, `max_iterations`, `initial_step`) for reproducible
orchestration and viz-facing envelopes.

### Lorentzian evolve (`evolve_lorentzian_skyrme`, PR #468)

Inputs: field, initial velocity, `dt`, `steps`, `save_every`, `f_pi`, `e`,
`damping`, caps / CFL bound.

Outputs (`LorentzianSkyrmeTrajectory`): energy/kinetic histories, approximate
charge history, constraint residuals, `linearized_cfl_indicator`,
`hyperbolicity_status="not_certified"`.

## Smallest useful experiment schema (this package)

See `schema.py` / `configs/smoke_*.json`:

- identity: `schema_version`, `experiment_id`, `mode`, `seed`
- discretization / BC / IC / model / solver settings
- optional Cartesian `sweep.axes` (capped at 64 points)
- unsupported fields rejected or labeled `unavailable` (no invented ranges)

### Seed / multi-seed staging

`vacuum` and `hedgehog` initial conditions are fully deterministic on the live
solver path: changing `seed` does **not** change the IC field. Seed still:

- enters `config_sha256` / `provenance.seed`
- drives stub-backend synthetic diagnostics when `--allow-stub` is used

There is no `seed` sweep axis. Multi-seed campaigns are staged as separate
configs (or repeated runs) with distinct `seed` values. That changes provenance
identity always; live IC fields stay seed-independent until a stochastic IC
kind is accepted by this schema.

## Result contract for visualization

`ExperimentResultV1` (`result_contract.py`) is the viz consumer envelope:

- provenance: seed, config hash, git revision, python/numpy
- status / failure message / backend availability
- diagnostics as `QuantityRecord` with `evidence ∈ {computed, assumed, speculative, unavailable}`
- `missing_data_semantics`: null means not computed, not zero
- claim tags forbid consciousness / clinical interpretation

Visualization modules should consume **this JSON**, not import solver-private
objects. Field snapshots themselves are not embedded by default (keep artifacts
small); checksums and scalar histories are provided when available.
