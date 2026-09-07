# Dependency and capability report

- Base/CPU requirements are separated from EEG, live, NWB, ML, quantum, and
  research profiles.
- CI installs the CPU/base profile for required checks, disables pip caching,
  bounds pip temporary space, and records install diagnostics.
- Optional capability registries and TDA adapters use lazy imports; missing
  optional packages are reported as unavailable rather than auto-installed.
- Observed optional/platform classifications: missing `torch`, missing
  `cripser`, and Windows symlink privilege (`WinError 1314`). These are not
  treated as passing scientific evidence.
- No package installation was performed by application code, and no hidden
  network request was added.
- YAML parsing passed for 10 workflow/config files; the targeted CI,
  governance, tooling, and provenance group passed 93 tests.
