# Review: NWB / PyNWB

- admission_status: admitted
- integration_mode: integrate
- review_date: 2026-09-05

## Role
Archival interchange. Already declared (`pynwb`, `h5py`, `remfile`) for DANDI
000458 lazy reads.

## Evidence
https://www.nwb.org/ and https://github.com/NeurodataWithoutBorders/pynwb.

## Constraints
Tests must use local objects/fixtures. `remfile` HTTP and DANDI S3 stay opt-in
and outside `tests/tool_admission/`.
