# Batch 2 Cursor C — Independent Round 6 Chain-Complex Oracle

**Label:** `INDEPENDENT_ORACLE_BATCH2_CURSOR_C`  
**Status:** `HOLD` / `SYNTHETIC_ONLY`

This package is an **independent algebraic oracle**, not a production engine and
not the Round 6 candidate. At original audit base (`origin/main` @ `3f3fe859…`)
and after rebase onto live `origin/main` @ `bc91af19…`, no finite chain-complex
endpoint-validation / exact-rational Betti implementation was found on main.
Public API: `FiniteChainComplex.betti()`, `.ranks()`, `.composition_zero()`,
`.boundary_1` / `.boundary_2` / `.boundary_3` (not `betti_numbers` /
`boundary_matrices`). Open PR #385 (phase cochain / Hodge) is a different lane
and is intentionally not modified or overlapped.

## Scope

- Endpoint validation (negative / OOR indices, self-loops, duplicates)
- Boundary operators ∂1, ∂2, ∂3 with exact `fractions.Fraction` entries
- Composition checks ∂1∂2 = 0 and ∂2∂3 = 0
- Exact rational Gaussian elimination ranks → Betti numbers
- Float SVD rank sensitivity across **declared** tolerances (no silent pick)
- Signed 3-cell / face-bundle cancellation vs absolute “edge appears twice”

## Non-goals

- No SciPy, datasets, participant data, or third-party code copying
- No 2D triangulation lane / Hodge lane overlap
- No scientific VALIDATED / PASS claims
