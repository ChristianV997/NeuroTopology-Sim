# Round 6 DMD / EP2 / matrix-log audit (oracle, synthetic only)

**State: HOLD / SYNTHETIC_ONLY.** Independent oracle at `tests/dmd_ep2_oracle/test_oracle.py`. Numerical diagnostics and matrix bounds do **not** establish a biological exceptional point, neural generator branch, or empirical effect.

## Scope

- Pure-Python 2×2 oracle: EP2 splitting / nilpotency, within-trajectory pairing, signed Nyquist alias, principal matrix log (interpolation + repeated-root limit), branch proximity.
- Optional bridge class `MergedProductionBridgeTests` imports merged `neurotopology_sim.experimental.dynamics.dmd_crouzeix` when present and cross-checks EP2 + 240↔−10 alias. Skips cleanly if the leaf is absent (e.g. this PR's historical base).
- Owned paths only: `tests/dmd_ep2_oracle/`, `docs/dmd_ep2_oracle_audit.md`. Production DMD is **not** edited here.

## Reproducible checks

```bash
python -m unittest discover -s tests/dmd_ep2_oracle -v
python -m compileall -q tests/dmd_ep2_oracle
git diff --check
```

Oracle suite asserts **full** `N² == 0` (all four entries) plus a regression that the single-entry proxy `n00² + n01·n10 == 0` is insufficient in general.

## Analytic EP2 result

Eigenvalues are `ω − iγ ± sqrt(δ² − g²)`. With δ=1.2: g=0.4 → split 2.2627416997969525; g=1.0 → 1.32664991614216; g=1.2 → 0. At g=δ, after subtracting `(ω−iγ)I`, `N ≠ 0` and `N² = 0` (alg. mult. 2, geo. mult. 1).

## Pairing, logs, Crouzeix language

Pairing builds adjacent snapshots inside each trajectory (no seam pair). Scalar `exp(log(z))` round-trip does **not** identify the branch (`+ 2πik`). Crouzeix `C=2` remains **PREPRINT_UNVERIFIED** on the production leaf; this oracle does not promote it.

## Discovery note

`tests/dmd_ep2_oracle/` is **not** registered in Round-6 `COMPONENTS` and is absent from the Required Checks default allowlist. Path-level hosted execution requires a Codex Agent A mapping/allowlist change (CI not edited in this lane).
