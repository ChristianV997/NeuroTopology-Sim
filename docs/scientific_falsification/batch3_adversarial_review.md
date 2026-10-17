# Batch 3 adversarial review

This note is the human-readable companion to
`configs/scientific_falsification/batch3_falsification_matrix.yaml`.
It is a falsification harness, not an empirical result.
It does not emit scientific PASS and does not compute a formal Bayes factor.
A successful falsification harness does not validate the theory; it only
makes invalid conclusions harder to emit.

Owned paths only:
- `docs/scientific_falsification/batch3_adversarial_review.md`
- `configs/scientific_falsification/batch3_falsification_matrix.yaml`
- `tests/scientific_falsification/test_batch3_falsification_matrix.py`

Primary checkout on `codex/disorder-averaged-collective-modes` was not
touched. Branch starts from current `origin/main`. REA was unavailable;
no neurodata, credentials, or external data services were accessed.

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
- nonattachment from EEG
- triadic dependence as a biological mechanism
- exceptional point as a biological phase transition
- prediction as causation
- graph beta-1 as spatial topological charge
- scientific PASS / formal Bayes factor from this matrix

## Scientific limit

Completeness of this matrix is not evidence that higher-order
connectivity, higher-order spectra, directed hypergraphs, or topological
proxies forecast a state transition. Prior project review remains
REVIEW_INCONCLUSIVE. PITNN K>100 failed 20/20 on ds005620.
