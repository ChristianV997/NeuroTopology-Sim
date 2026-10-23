# Batch 3 adversarial review

This note is the human-readable companion to
`configs/scientific_falsification/batch3_falsification_matrix.yaml`.
It is a falsification harness, not an empirical result.
It does not emit scientific PASS and does not compute a formal Bayes factor.
A successful falsification harness does not validate the theory; it only
makes invalid conclusions harder to emit.

Live main synced: `b51bb9b4bdf63c19894bb407eadcd70f528f7dda` (PR #376 merge `7fb3c18`; normal sync merge incorporated this current base).

Owned paths only:
- `docs/scientific_falsification/batch3_adversarial_review.md`
- `configs/scientific_falsification/batch3_falsification_matrix.yaml`
- `tests/scientific_falsification/test_batch3_falsification_matrix.py`

Primary checkout was not touched. Branch starts from current `origin/main`.
No neurodata, credentials, or external data services were accessed.

## Protocol Limits and Power Validation

- Status: protocol-only (`scientific_pass=false`, `empirical_claim_allowed=false`, `formal_bayes_factor=null`, `k_value=null`).
- Completeness never implies scientific success: Completing the falsification matrix (`complete=true`) only verifies that protocol rules and gates are structurally specified; it never sets `scientific_pass=true`, never allows empirical claims, and never establishes scientific adequacy.
- Proposed thresholds are not power validation: Proposed splits, null models, sample and effect thresholds (such as `minimum_paired_subjects=20`, `minimum_held_out_subjects=8`, `minimum_sessions_per_split=2`, and minimum 100 null replicates), confound controls, subject exclusion policies, and replication gates are conservative protocol proposals and falsification criteria, not empirical power validation, statistical ground truth, or established scientific adequacy.
- Falsification metrics cannot be inverted into affirmative empirical confirmation.

## Campaign Execution States and Resumability

The campaign execution harness defines an explicit deterministic state machine:
- **Campaign Execution States**:
  - `PLANNING`: Initial specification and preregistration phase.
  - `REGISTERED`: Protocol locked with cryptographic manifest digest.
  - `EXECUTING`: Workload dispatch under isolated boundaries.
  - `INTERRUPTED`: Gracefully stopped mid-execution upon timeout, signal, or boundary trigger.
  - `RESUMED`: Resumed from intermediate checkpoint with verified plan digest.
  - `COMPLETED`: Terminal state reached when all registered units finish cleanly.
  - `ABORTED`: Terminal state reached upon hard failure, schema breach, or claim violation.
- **Terminal States**: `COMPLETED` and `ABORTED` are terminal. They have zero outgoing transitions
  and cannot be reopened or mutated.
- **Transition graph**: Only the locked adjacency is accepted (for example `PLANNING` may go to
  `REGISTERED` or `ABORTED`, never directly to `COMPLETED`). Destinations outside
  `campaign_execution_states` (including outcome labels such as `PASS`) fail closed.
- **Resumability Invariants**:
  - Resumption requires exact plan and artifact hash matches.
  - Resumed runs must replay from verified checkpoint manifests and only execute interrupted units.
  - Resumption cannot bypass falsification gates or transition into non-protocol states.
- **Formal K fields**: Top-level `formal_bayes_factor` and `k_value` must be present and null;
  omitting the keys is not treated as an authorized unset.

## Claims reviewed

1. Higher-order connectivity versus pairwise baselines.
2. Higher-order spectra versus ordinary cross-frequency coupling.
3. Respiration and autonomic variables versus generic calmness claims.
4. Discernment versus nonjudgment, decentering, and nonattachment.
5. Topological proxy measures versus true spatial or graph topology.
6. Synthetic, proxy, engineering, and empirical evidence separation.
7. Causal language, hidden confounding, leakage, temporal smoothing,
   volume conduction, and common drivers.
8. Multiple comparisons, sample-size adequacy, replication, null
   calibration, and held-out prediction.
9. Whether any report or CLI can emit scientific PASS without sufficient
   evidence.
10. Whether missing or failed subjects can distort results.

## Falsification rules

- Incremental HOI must beat PSD and pairwise FC on subject-held-out,
  session-held-out, and forward-time splits after volume-conduction and
  common-driver controls.
- Higher-order spectra must beat ordinary cross-frequency coupling.
- Respiration, HR, and HRV are predictors or controls. Respiration is
  not equanimity.
- Discernment, nonjudgment, decentering, and nonattachment require
  contemporaneous instruments (EQ, FFMQ-nonjudge, NAS). EEG alone is
  blocked.
- Graph beta-1, spatial winding, and scalar chirality stay distinct.
  Graph beta-1 is not spatial topological charge.
- Synthetic output cannot be labeled empirical.
- Unknown test count is not one test. Below 20 paired / 8 held-out
  subjects is INSUFFICIENT_POWER.
- Missing or failed subjects are excluded and reported, never
  zero-filled as a null effect.
- No path in this harness emits PASS or a formal K.

## Blocked claims

- proof of consciousness
- biological quantum coherence
- respiration as equanimity
- discernment from EEG alone
