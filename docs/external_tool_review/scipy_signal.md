# Review: SciPy signal

- admission_status: admitted
- integration_mode: integrate
- review_date: 2026-09-05

## Role
Canonical filters and Hilbert transform. `sim/pitnn/empirical_pipeline.py`
already calls `butter`, `sosfiltfilt`, and `hilbert`.

## Evidence
https://docs.scipy.org/doc/scipy/reference/signal.html (BSD-3-Clause).

## Constraints
Record filter order, band edges, and sample rate in RunRecord. Zero-phase
filtfilt needs adequate pad length — already guarded in empirical_pipeline.
