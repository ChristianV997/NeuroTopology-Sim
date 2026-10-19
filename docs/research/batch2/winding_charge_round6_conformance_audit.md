# Round 6 winding / charge-moment conformance audit

**Project posture:** `HOLD` / `SYNTHETIC_ONLY`  
**Claim scope:** discrete algebraic identity only  
**Scientific VALIDATED/PASS:** forbidden  
**Oracle path:** `tools/experimental_audits/winding_charge_round6/`  
**Lane:** Batch 2 / Cursor Agent A — branch `batch2/cursor-a-winding-charge-audit`

## What this is

An independent, executable conformance audit of the Round 6 *phase-winding and signed charge-moment* discrete claims. It implements a **specification oracle** from the documented mathematics (principal-interval wrapping, integer branch indices, plaquette/triangle charges, origin-shift moment identity, missing-sign separation).

## What this is not

- Not a test harness for Gemini’s `experimental/phase_cochain_reference` candidate (PR #385). That engine is **not imported and not modified**.
- Not a BIDS/EEG/OpenNeuro run.
- Not biological, clinical, or consciousness validation.
- A discrete identity that holds on synthetic fixtures does **not** promote the metric as a validated physical or neural construct.

## Candidate location (read-only context)

Original audit base: `origin/main` @ `3f3fe859…` (Round 6 reference observed on
open PR #385; absent from main). After rebase onto live `origin/main` @
`bc91af19…`, production leaf
`neurotopology_sim/experimental/topology/winding.py` is present.

- Independent oracle remains in `tools/experimental_audits/winding_charge_round6/`
  (self-derived fixtures; does not import production).
- Production-import comparison:
  `tests/experimental_audits/test_winding_charge_production_import.py`
  hard-imports the live production module path and asserts oracle triangle
  charges / orientation / origin-shift identity match. Dipole
  `charge_separation_defined` is `True` when both signs are present
  (`sep≈2`); missing-sign case remains undefined per claim 7.

**Round 6 discovery note (for Codex Agent A — no workflow edits here):**
component `winding_charge_audit` currently lists only
`tests/experimental_audits/test_winding_charge_round6_oracle.py`. The new
production-import path should be added to that component’s `tests` /
`candidate_pairs` if hosted Round 6 is expected to execute it.

## Discrete claims under audit

1. Edge phase differences wrap into a principal interval `[-π, π)` with **explicit** `+π → −π`.
2. Branch indices `n ∈ ℤ` recovered from `Δ − wrap(Δ)` yield integer triangle charges `q = −d₁ n`.
3. Orientation: cyclic permutations preserve loop winding; reversals negate it.
4. Adding `2πk` to vertex phases leaves charges invariant.
5. Net charge `Q_net = Σ q` and absolute charge are conserved as discrete sums on synthetic dipoles/vortices.
6. Origin-shift identity: with origin moved by `a` (`r′ = r − a`),
   `p_q(r − a) = p_q(r) − Q_net · a`
   (equivalent to PR #385’s `m(r+v)=m+Q_net·v` with `a = −v`). Verified for `Q_net=0` and `Q_net≠0`.
7. Missing-sign charge separation is **explicitly undefined** (`NaN` + `charge_separation_defined=False`), never silent `0.0`.
8. Confidence weights scale scores only; integer `q` values are unchanged.

## Branch convention (must be explicit)

| Case | Oracle behavior |
|---|---|
| Exact `+π` | wraps to `−π`; branch index `n = 1` for a raw difference of `+π` |
| Exact `−π` | stays `−π`; branch index `n = 0` |
| Near `±π` | continuous within float tolerance; no silent sign flip beyond wrap |

**Ambiguity avoided:** `rint(Δ/2π)` at `Δ=±π` hits the `±0.5` banker's-rounding edge. This oracle recovers `n` from the wrap instead.

## Discrete identity vs physical claim

| Discrete identity (audited) | Physical / biological claim (not claimed) |
|---|---|
| Integer `q` from coboundary of branch indices | “Topological charge in cortex” |
| `p_q` transforms as stated under origin shift | Moment is a neural dipole observable |
| Undefined separation when a sign is absent | Separation distance is an empirical biomarker |

Algebraic winding alone does **not** establish a biological interpretation. Repository status remains **HOLD / SYNTHETIC_ONLY**.

## How to run

```bash
python3 -m tools.experimental_audits.winding_charge_round6
python3 -m tools.experimental_audits.winding_charge_round6 --json /tmp/winding_charge_audit.json
python3 -m pytest tests/experimental_audits/ -q
```

Engineering vocabulary only: `DISCRETE_IDENTITY_HOLDS` / `DISCRETE_IDENTITY_FAILS` / `INCONCLUSIVE_INPUT`.
