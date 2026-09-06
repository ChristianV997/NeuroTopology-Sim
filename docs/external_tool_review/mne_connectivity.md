# Review: MNE-Connectivity

- admission_status: admitted_optional
- integration_mode: integrate
- review_date: 2026-09-05

## Role
Maintained spectral connectivity reference. `requirements.txt` already uses it
to cross-check hand-rolled wPLI.

## Evidence
https://github.com/mne-tools/mne-connectivity (BSD-3-Clause).

## Constraints
All-to-all connectivity is expensive. Outputs are comparators, not topology
proofs and not PITNN verdicts.
