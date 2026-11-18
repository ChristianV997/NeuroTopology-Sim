# SU(2)/Skyrme experiment layer

Reproducible **experiment runner**, **configuration/provenance contract**, and
**parameter-sweep orchestration** for the SU(2)/Skyrme solvers.

This package does **not** implement solver mathematics or visualization UI.

Research simulator only: outputs are finite-grid numerical diagnostics, not
consciousness scores, clinical findings, or validated physical predictions.

## Dependency blocker (live solver)

| Package | Location | Status on this base |
|---|---|---|
| `field_theory.su2` foundation (NN relax, generators) | `origin/main` | **Absent** on `antigravity/missingness-and-cohorts-20261016` — merge-main follow-up recommended for live runs |
| Enriched NN residuals / metrics / constrained / sweeps | PR [#466](https://github.com/ChristianV997/NeuroTopology-Sim/pull/466) | Draft; adapter filters kwargs/attrs when missing |
| Lorentzian Skyrme evolve | PR [#468](https://github.com/ChristianV997/NeuroTopology-Sim/pull/468) | Stacked on #466; labeled `solver_unavailable` if missing |

Probe:

```bash
python -m experiments.su2_skyrme probe-solver
```

Exit code `2` means the live API is unavailable. Use `--allow-stub` only for
contract / CI smoke of **this** layer (stub values are tagged `assumed`).
When `field_theory` is present (e.g. after merging `origin/main`), omit
`--allow-stub` to exercise the live adapter; Lorentzian still needs #468.

## Reproduce a single run

```bash
# Validate config
python -m experiments.su2_skyrme validate-config \
  --config experiments/su2_skyrme/configs/smoke_relax.json

# Stub-backed smoke (works without solver merge)
python -m experiments.su2_skyrme run \
  --config experiments/su2_skyrme/configs/smoke_relax.json \
  --output experiments/su2_skyrme/outputs/smoke_relax_result.json \
  --allow-stub

# Live solver (only when field_theory.su2 is importable)
python -m experiments.su2_skyrme run \
  --config experiments/su2_skyrme/configs/smoke_relax.json \
  --output experiments/su2_skyrme/outputs/smoke_relax_live.json
```

## Reproduce a parameter sweep

```bash
python -m experiments.su2_skyrme run \
  --config experiments/su2_skyrme/configs/smoke_sweep.json \
  --output experiments/su2_skyrme/outputs/smoke_sweep_result.json \
  --allow-stub
```

Smoke sweep axes: `e ∈ {1.0,1.5}` × `max_iterations ∈ {1,2}` → **4 points**.

## What is recorded

Every result JSON includes:

- `seed`, `config_sha256`, git revision / dirty flag (untracked files count as dirty)
- discretization, boundary conditions, IC, model/solver settings
- run / sweep `status` and per-point diagnostics
- evidence tags: `computed` | `assumed` | `speculative` | `unavailable`
- claim tags forbidding consciousness / clinical interpretation

See `IO.md` for solver I/O inspection notes and `result_contract.py` for the
viz-facing schema.

## Seed contract

Supported live ICs (`vacuum`, `hedgehog`) are **deterministic and seed-independent**.
`seed` is still required in the config for:

1. provenance identity (`provenance.seed` + `config_sha256`)
2. synthetic variation in the stub backend (`--allow-stub`)

Multi-seed staging is **not** a sweep axis yet. Run separate configs (or repeat
the CLI) with distinct `seed` values when you want a multi-seed campaign; on the
live path those seeds change provenance only, not the IC field. A future seed
axis would be additive and labeled when wired.

## Runtime / memory (staged path)

| Stage | Grid | Points | Intent | Expected cost |
|---|---|---|---|---|
| Local smoke (stub) | 4³ | 1–4 | Contract + CLI | ≪1 s, ≪50 MB |
| Local smoke (live relax) | 4³ | 1–4 | Import + tiny relax | typically seconds, ≪100 MB |
| Multi-seed (staged) | 4³–8³ | N configs × axes | Provenance / stub stability | linear in seeds × points; live IC unchanged |
| Grid refinement | 8³–16³ | few | Resolution sensitivity | memory ~ O(N³); keep sweeps narrow |

Hard caps in this layer: ≤4096 nodes per config, ≤64 sweep points. Larger
campaigns should call the solver APIs directly or widen caps intentionally.

## Tests

```bash
pytest tests/experiments/su2_skyrme -q
```

## Handoff for visualization consumers

Consume `ExperimentResultV1` JSON (`schema_version: "0.1.0"`):

1. Branch on `status` / `solver_api_status` before plotting.
2. Read `diagnostics[].evidence` and `availability`; treat `null` as missing.
3. Never map topological / energy diagnostics to consciousness scores.
4. Prefer scalar histories under `points[].histories`; field arrays are not
   embedded by default.
5. Use `provenance.config_sha256` + `result_id` for cache keys.

## Layout

```
experiments/su2_skyrme/
  schema.py            # config contract
  provenance.py        # seed / hash / git
  result_contract.py   # viz envelope
  adapter.py           # thin public-API adapter + stub
  runner.py            # deterministic run + sweep
  cli.py / __main__.py
  configs/smoke_*.json
  IO.md / README.md
```
