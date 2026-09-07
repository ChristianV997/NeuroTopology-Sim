# Changed-file ownership report

The final branch preserves one owner per implementation seam:

- CI/dependency/test isolation: `.github/workflows/**`, `requirements-*.txt`,
  `scripts/run_tests_isolated.py`, `conftest.py`, `pytest.ini`, and CI docs;
  #227 is authoritative for installation policy, while #213/#222 behavior is
  retained where non-duplicative.
- Streaming/performance: `tools/streaming/**`, `scripts/benchmark_*.py`,
  performance policies, checkpoint/replay, and performance tests.
- Signal interoperability/EEG: `shared/interop/**`, `sciencer_d/btc_icft/io/**`,
  EEG tests, and conformance fixtures.
- Scientific falsification: `sim/pitnn/bayesian_falsification.py` is anchored
  to #219 with #226 consumer semantics; `sim/pitnn/api_bridge.py` and export
  semantics are owned by #234. The final integration repair also updates the
  legacy empirical/MEG callers to pass explicit source metadata.
- Provenance/cohorts: `shared/provenance/**` and
  `shared/data_loaders/cohort_manifest.py` remain local-only and do not mutate
  RunRecordV1.
- Tooling/TDA: `shared/tooling/**`, capability snapshots, and
  `topo_monitor/tda_adapters/**` use lazy optional imports and deterministic
  fallbacks.
- Governance/release: `governance/merge_gate.py`, reconciliation artifacts,
  dependency matrix, release decision log, and release-state documentation.
- Cross-platform validation: `benchmarks/validation.py` owns repository-path
  grammar checks; `adapters/mne_bids_feature_recipe.py` owns portable artifact
  path serialization; the symlink test records unavailable Windows privilege
  as an environment skip only.

No datasets, binary trajectories, credentials, or generated plots were added.

- New additive ownership: `shared/provenance/readers.py` owns lazy local
  container inspection; `analysis/cohort_statistics/**` owns paired descriptive
  and non-parametric statistics; `tools/cohort_execution/**` owns readiness-
  gated streaming cohort execution; and `tools/platform_compat/**` owns
  platform capability audits.
- New release/governance ownership: `shared/research_claims/**`,
  `tools/research_record/**`, `tools/release_manifest/**`, and
  `tools/test_admission/**` are deterministic metadata/reporting layers. They
  do not promote synthetic data, proxy Bayes values, or missing provenance.
- CI ownership: #257 is the selected five-file authoritative workflow repair;
  #254 owns process-group timeout safety. The older #249 CI repair is not
  retained as a competing implementation.
