# Dependency and capability report

- Base/CPU requirements are separated from EEG, live, NWB, ML, quantum, and
  research profiles.
- CI installs the CPU/base profile for required checks, disables pip caching,
  bounds pip temporary space, and records install diagnostics.
- Optional capability registries and TDA adapters use lazy imports; missing
  optional packages are reported as unavailable rather than auto-installed.
- Observed optional/platform classifications: missing `torch`, missing
  `cripser`, missing `ripser`, and Windows symlink privilege (`WinError 1314`).
  These are not treated as passing scientific evidence.
- No package installation was performed by application code, and no hidden
  network request was added.
- YAML parsing passed for 10 workflow/config files; the targeted CI,
  governance, tooling, and provenance group passed 93 tests.
- Batch 2 focused validation added provenance readers, platform compatibility,
  cohort statistics, cohort topology, TDA hardening, research claims/records,
  release manifest, admission, interop, null calibration, and performance
  evidence suites. Missing optional packages remain explicit capabilities, not
  successful validation.
