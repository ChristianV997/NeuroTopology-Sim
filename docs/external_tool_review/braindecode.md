# Review: Braindecode

- admission_status: deferred
- integration_mode: reference
- review_date: 2026-09-05

## Role
Downstream deep-learning decoder. Must not determine falsification verdicts.

## Evidence
https://braindecode.org/ (BSD-3-Clause; some bundled assets CC-BY-NC).

## Constraints
Dataset fetchers (MOABB/EEGDash) are forbidden in tests. Model outputs cannot
write `verdict: PASS` or alter `K`.
