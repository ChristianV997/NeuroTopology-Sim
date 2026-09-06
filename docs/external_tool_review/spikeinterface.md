# Review: SpikeInterface

- admission_status: admitted_optional
- integration_mode: reference
- review_date: 2026-09-05

## Role
Extracellular spike-sorting framework only.

## Evidence
https://spikeinterface.readthedocs.io/ (MIT).

## Constraints
Not a scalp-EEG preprocessor. Optional sorter binaries must not be fetched in
tests. NWB export is compatible with the archival path if a later ephys ingest
appears.
