# Review: EEGLAB

- admission_status: reference_only
- integration_mode: reference
- review_date: 2026-09-05

## Role
MATLAB GUI/toolbox reference for ICA and ERP-style workflows.

## Evidence
https://sccn.ucsd.edu/eeglab/index.php and https://github.com/sccn/eeglab.

## Constraints
Not a CPython package. Must not enter `requirements.txt`. CI must not invoke
MATLAB or Octave. Use MNE when an algorithm must run in this repository.
