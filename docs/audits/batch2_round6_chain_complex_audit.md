# Round 6 Finite Chain-Complex Audit (Batch 2 / Cursor C)

**Status:** HOLD / SYNTHETIC_ONLY  
**Oracle label:** `INDEPENDENT_ORACLE_BATCH2_CURSOR_C`  
**Base (original audit):** `origin/main` @ `3f3fe8593303184cb88eef056c1322f3d4e57a16`  
**Live main (merged):** `origin/main` @ `e59dd6c23000c3e76d81ab0bb7d895be32243352`  
**Prior live tip:** `bc91af19a22783d2721fc881842573f7e08a8925`  
**Branch:** `batch2/cursor-c-3d-chain-audit`

## Candidate search

No Round 6 finite chain-complex engine (endpoint validation + ∂ matrices + exact
rational ranks + Betti) was present on live `main` at the original audited SHA,
and still absent after merge of `e59dd6c…` (confirmed: no
`neurotopology_sim/**/chain_complex*` / `finite_chain*` production leaf).

Related but **out of lane** on live main: `neurotopology_sim/experimental/topology/winding.py`
and `neurotopology_sim/experimental/geometry/planar_triangulation.py` (owned by
#399 / #410 production-import comparisons). Open PR #385
(`experimental/phase_cochain_reference`, Hodge / cochain) remains a different
lane and was not inspected as the candidate, modified, or overlapped.

Therefore this PR ships a clearly labeled **independent oracle** only — there is
no production module for a production-import comparison test to hard-import.

## Chain convention (oracle)

Homology operators (not cohomology):

```
C3 --∂3→ C2 --∂2→ C1 --∂1→ C0
∂k matrix shape: (dim C_{k-1}) × (dim C_k)
Exactness: ∂1 @ ∂2 = 0 and ∂2 @ ∂3 = 0
```

Proposal name map: `d0↔∂1`, `d1↔∂2`, `d2↔∂3`.  
Standard product order is `d0@d1=0` and `d1@d2=0`. A candidate that checks
`d1@d0=0` is using transposed / reversed operands and must be reconciled
explicitly against this convention.

Betti formulas (no 4-cells):

```
β0 = n0 − rank(∂1)
β1 = n1 − rank(∂1) − rank(∂2)
β2 = n2 − rank(∂2) − rank(∂3)
β3 = n3 − rank(∂3)
```

Empty degrees: zero-column / zero-row matrices; vacuous products are zero;
empty complex → `(β0,β1,β2,β3)=(0,0,0,0)`.

## Exact results (oracle)

| Fixture | (n0,n1,n2,n3) | ranks (∂1,∂2,∂3) | Betti (β0,β1,β2,β3) | ∂²=0 |
|---|---|---|---|---|
| empty | (0,0,0,0) | (0,0,0) | (0,0,0,0) | yes |
| two isolated vertices | (2,0,0,0) | (0,0,0) | (2,0,0,0) | yes |
| single edge | (2,1,0,0) | (1,0,0) | (1,0,0,0) | yes |
| triangle boundary | (3,3,0,0) | (2,0,0) | (1,1,0,0) | yes |
| filled triangle | (3,3,1,0) | (2,1,0) | (1,0,0,0) | yes |
| tetrahedron surface (closed S²) | (4,6,4,0) | (3,3,0) | (1,0,1,0) | yes |
| filled tetrahedron | (4,6,4,1) | (3,3,1) | (1,0,0,0) | yes |
| **open triangular prism** | (6,12,6,0) | (5,6,0) | **(1,1,0,0)** | yes |
| disconnected two edges | (4,2,0,0) | (2,0,0) | (2,0,0,0) | yes |
| wedge circle ∪ sphere (disconnected) | (7,9,4,0) | (5,3,0) | (2,1,1,0) | yes |

Open-prism claim `(1,1,0)` matches the oracle’s `(β0,β1,β2)=(1,1,0)` for this
lateral-surface triangulation (χ = 0). These are algebraic checks only — not
evidence of a physical 3D neural construct.

## SVD sensitivity

For integer boundary matrices of the open prism, SVD ranks at tolerances
`{1e-12, 1e-9, 1e-6, 1e-3}` agree with exact ranks (`unstable=false`).

A near-dependent float companion (`ε = 1e-10` residual) produces **distinct**
SVD ranks across that same tolerance grid (`unstable=true`). The oracle
**reports** instability and never silently selects a tolerance.

## Defects / findings (no candidate engine on main)

1. **No candidate to score on main** — oracle-only audit.
2. **Proposal product order `d1@d0=0`** is nonstandard relative to homology
   matrix layout used here; any future candidate must document operand order.
3. **“Each active edge appears twice” is insufficient** for a valid closed
   face-bundle / 3-cell edge shadow: two identically oriented faces give
   absolute counts `[2,2,2]` while the signed sum is `[2,2,2] ≠ 0`. Signed
   incidence cancellation is required.
4. **Numerical rank** can flip with tolerance on near-dependent matrices;
   exact rational rank is the audit ground truth.

## Owned paths (this PR only)

- `tools/batch2_chain_complex_audit/`
- `tests/batch2_chain_complex_audit/`
- `docs/audits/batch2_round6_chain_complex_audit.md`

Does **not** touch `experimental/phase_cochain_reference`, triangulation
lanes, or any candidate engine.

## Test command

```bash
python -m pytest tests/batch2_chain_complex_audit/ -q
```

Guardrails: small synthetic complexes only; stdlib `fractions` + optional
numpy SVD; no SciPy; no datasets; no VALIDATED/PASS scientific claims.

## CI / Round 6 discovery note (PR #397)

Round 6 helper maps this lane as `finite_chain_audit` →
`tests/batch2_chain_complex_audit/*.py` (self-pair oracle). After merge of live
main `e59dd6c…`, hosted Round 6 must re-run those exact paths with nonzero
collection; path-mapping edits (if any) go to Codex Agent A — this PR does not
edit workflows.

On prior head `506f13f8…`: `core-tests`, `Cross-system smoke`, and
`ontology-claim-language` passed. `awareness-tests` failed in
`apps/awareness_studio/tests/research_cycle/test_registered_execution.py`
(3 failures: `EXECUTION_FAILED` / missing `resumed`). That suite is
**unchanged by this PR** and reproduced the same 3 failures on clean
`origin/main` @ `3f3fe85…`. Out of ownership for this audit lane —
not patched here.
