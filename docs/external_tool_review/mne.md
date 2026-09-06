# Review: MNE-Python

- admission_status: admitted
- integration_mode: integrate
- review_date: 2026-09-05

## Role
Core EEG I/O and preprocessing path. Already declared in `requirements.txt`
and used with `mne-bids` for BrainVision/BIDS recordings such as ds005620.

## Evidence
Official docs https://mne.tools/stable/index.html and BSD-3-Clause license
https://github.com/mne-tools/mne-python/blob/main/LICENSE.txt.

## Constraints
- Tests must not call `mne.datasets` or OpenNeuro.
- High-rate Raw objects need explicit cropping; ds005620 is 5 kHz.
- MNE does not own `K > 100`.

## Test strategy
Local BrainVision header fixtures or synthetic Raw created in memory.
