# Ecosystem Integration — Acceptance Document

Branch: `codex/integration-all-open-prs`
Base: `origin/main` @ `62637a4b9c82c0c258bfc49e28dee1af757b1c25`
This document began as PR #210's acceptance record and was updated in the
dedicated merger checkout after compatible dependency groups were integrated.
The final branch intentionally spans the accepted PRs listed below.

## 1. Branch order

The dependency graph was reconciled in this order: the topology-only portion
of the scientific contract branch, PR #219's authoritative Bayesian module,
PRs #213/#222 for dependency profiles and isolated CI, #211 then #215 for
streaming and RSS telemetry, #212 then #220 for signal contracts and native
adapters, #214 for EEG streaming, #209/#217 for offline inventory and tool
admission, #221 for legacy repairs, #218 for reconciliation tooling, and
PR #210 as the final bridge layer. PR #216 remains intentionally unmerged.

The exact commit hashes, stacked relationships, overlap resolutions, and the
unavailable exact branch named `grok/tool-admission-research` are recorded in
`configs/integration/dependency_matrix.yaml` and
`docs/release/integration_merge_decisions.md`. The branch-only Bayesian file
was not silently duplicated: its distinct topology modules were retained and
the overlapping Bayesian implementation was superseded by PR #219.

## 2. Integration boundaries

| Area | Integrated sources | Notes |
|---|---|---|
| `tools/integration_bridge/**`, `scripts/assemble_ecosystem_run.py`, `tests/integration/**` | PR #210 | bridge, artifact, quality, preflight, and dashboard isolation |
| `shared/interop/**`, EEG adapters, `tools/streaming/**` | PRs #212, #214, #211, #215, #220 | canonical contracts with lazy optional dependencies |
| `sim/pitnn/bayesian_falsification.py`, topology-contract modules | branch-only contract + PR #219 | distinct topology semantics; #219 is authoritative for Bayesian behavior |
| CI, runner, profiles | PRs #213 and #222 | manually reconciled at overlapping paths |
| inventories, admission, repairs, reconciliation | PRs #209, #217, #221, #218 | offline/read-only tooling |

The integrated bridge **consumes** the following public adapters, with
compatibility tested against the strengthened implementations (full list with
roles in `configs/integration/dependency_matrix.yaml`'s
`consumed_public_adapters`): `runs.run_record.RunRecordV1`/`build_run_id`,
`governance.spec.HypothesisSpec`, `governance.io.load_spec`,
`governance.validate.validate_spec`, `sim.pitnn.ingest_empirical.
ingest_empirical`, `sim.pitnn.mumax3_macro_tda.synthetic_signal`/
`invert_macro_signal`, `sim.pitnn.bayesian_falsification.compare_models`,
`core.topology.compute_Qz`/`compute_f_dress`, `analysis.
connectivity_topology.compute_beta1`, `sim.pitnn.topological_invariants.
TopologicalInvariantTracker`. The bridge does not reimplement these contracts.

## 3. Merge gates

Before this branch merges into `main`:

1. `python -m governance.validate` passes (all `governance/specs/*.yaml`
   valid) — unaffected by this branch, re-checked as a baseline.
2. `PYTHONPATH=. python -m pytest tests/integration -q` passes in full.
3. `python -m compileall -q tools/integration_bridge scripts/assemble_ecosystem_run.py tests/integration configs/integration` exits 0.
4. A changed-file audit covers every accepted PR and records all overlap
   resolutions in the merger decision log.
5. A secret scan over tracked production/config/docs files finds nothing
   (API keys, tokens,
   private key blocks, AWS access-key patterns).
6. No unresolved ownership collision remains after the #213/#222 and
   branch-only/#219 reconciliations.
7. Every optional-dependency adapter this integration can invoke is
   explicitly classified as available/unavailable in the run's own
   `environment.adapters` output (never silently attempted).
8. No empirical `PASS` is ever produced from `data_mode="synthetic"` —
   enforced by `tools.integration_bridge.quality_gate.classify_status`
   and directly tested by
   `tests/integration/test_assemble_ecosystem_run.py::test_synthetic_dry_run_produces_not_supported_never_pass`.
9. Network/live mode is refused unless both `--allow-network` and
   `NTS_INTEGRATION_ALLOW_NETWORK=true` are set — tested by
   `tests/integration/test_preflight.py` and
   `tests/integration/test_assemble_ecosystem_run.py::test_no_network_refused_when_live_flag_set_without_env_opt_in`.

## 4. Test commands

```bash
# Governance validator (baseline; this branch does not touch governance/specs)
python -m governance.validate

# Integration bridge and reconciliation suites
PYTHONPATH=. python -m pytest tests/integration -q
python -m pytest tests/integration_reconciliation -q

# Static checks
python -m compileall -q tools/integration_bridge scripts/assemble_ecosystem_run.py tests/integration configs/integration

# Manual smoke run (synthetic, no network, no dataset download)
python scripts/assemble_ecosystem_run.py --data-mode synthetic --output-dir <temp-dir>/nts_smoke --dataset-id demo --seed 0
```

The merger's final validation also runs the repository-wide isolated runner
with bounded batches and records optional-dependency failures separately from
core regressions in `docs/release/integration_merge_decisions.md`.

## 5. Artifact contract

Every `scripts/assemble_ecosystem_run.py` invocation writes exactly four
files to `--output-dir`:

| File | Producer | Notes |
|---|---|---|
| `RunRecord.json` | `runs.run_record.RunRecordV1.write_json` | Canonical, unmodified schema (`schema_version: "0.1"`). `verdict` is always one of `PASS`/`NOT_SUPPORTED`/`INCONCLUSIVE`/`ERROR`. |
| `quality_report.json` | `tools.integration_bridge.quality_gate.QualityReport.to_dict` | `schema: "NTS.IntegrationQualityReport.v1"`. |
| `summary.md` | `tools.integration_bridge.reporting.render_markdown_summary` | Human-readable; not machine-parsed by anything. |
| `manifest.json` | `tools.integration_bridge.artifact_manifest` | `schema: "NTS.IntegrationArtifactManifest.v1"`; sha256 + size for the three files above. |

**Determinism note:** `manifest.json`'s *builder* is fully deterministic
(same artifact bytes + same metadata -> byte-identical manifest JSON,
regardless of filesystem iteration order — see
`tests/integration/test_artifact_manifest.py`). A full `RunRecord.json`
from two separate real invocations will still differ in its `created_at`
field, because `RunRecordV1` is canonical and unmodified by this
integration (per the "RunRecordV1 remains canonical" guardrail) and that
field is a genuine wall-clock timestamp by the existing schema's own
design — this is expected, not a determinism bug in the manifest logic
itself.

## 6. Rollback strategy

This PR is purely additive (five new paths, zero edits to existing
files). Rollback is a plain revert of the merge commit — no data
migration, no schema change to any existing artifact, no change to any
existing test's behavior. If a future dependency-branch integration
built on top of this scaffold needs to be rolled back independently, that
branch's own commits revert cleanly as long as it, too, stayed within its
declared ownership boundary (see `configs/integration/dependency_matrix.yaml`'s
`integration_stance` per branch for what each future branch is expected to
touch).

## 7. Review checklist

- [ ] `git diff --stat origin/main` matches the accepted PR inventory and
      has no unexplained files outside the recorded ownership boundaries.
- [ ] `configs/integration/dependency_matrix.yaml` accurately reflects the
      remote's actual branches at merge time (re-run the branch-existence
      check if time has passed since this document was written).
- [ ] `PYTHONPATH=. python -m pytest tests/integration -q` is green.
- [ ] `python -m governance.validate` is green (baseline, unaffected).
- [ ] No new file contains a secret, credential, dataset, binary, or
      generated artifact (only source `.py`, `.yaml`, `.md` files are
      committed; `tests/integration` writes all generated output to
      `tmp_path` fixtures, never into the repository tree).
- [ ] No solver/falsification/topology/governance module is imported from
      `apps/awareness_studio/src/**` (`tests/integration/test_dashboard_isolation.py`).
- [ ] Synthetic data cannot surface as an empirical `PASS` anywhere in the
      packaged output (`tests/integration/test_quality_gate.py`,
      `tests/integration/test_assemble_ecosystem_run.py`).
- [ ] Network/live mode is refused by default and requires two
      independent opt-ins to enable.
- [ ] Graph beta_1 and spatial winding/charge/chirality remain in
      separate, non-collapsible namespaces in every packaged artifact.

## 8. Remaining scientific limitations

These limits remain explicit after integration. They are recorded here
because `scripts/assemble_ecosystem_run.py` invokes the affected code and no
packaged artifact should be read as biological confirmation:

1. **A K threshold is not evidence by itself.** PR #219 now requires a
   formal marginal-likelihood method, empirical provenance, valid inputs,
   declared controls/multiplicity, and an effective-sample gate before an
   empirical `PASS` can be emitted. RSS/AICc/BIC outputs remain explicit
   proxies; synthetic, invalid, or incomplete-provenance inputs are blocked
   or inconclusive.
2. **The baseline this integration's `bayesian_falsification` step
   compares against, labeled `classical_wilson_cowan` by the upstream
   module, does not implement the Wilson-Cowan neural-mass model** — it
   is a 4-parameter linear/harmonic regression. A real Wilson-Cowan
   implementation exists in this repository (`pipelines/run_neurolib.py`,
   via `neurolib`'s `WCModel`) but is not connected to this comparison.
   Any report generated from this integration's output that describes the
   comparison in Wilson-Cowan terms should be read as referring to the
   upstream module's internal (mis)labeling, not a validated neural-mass
   baseline.
3. **Multiplicity correction is declared and available, but not automatic
   for every downstream cohort analysis.** Any aggregation beyond the
   packaged run must declare and apply an appropriate correction.
4. **Optional scientific and cloud backends remain environment-dependent.**
   Tool admission reports capability and does not install packages, open
   sockets, use credentials, or execute AWS/QPU code. Local adapters are
   lazy and unavailable capabilities are structured rather than silently
   attempted.
5. **No biological confirmation is asserted.** The integration is a
   solver-free/offline artifact and dashboard/API layer; no AWS, QPU, cloud,
   external dataset, or biological execution was performed.
