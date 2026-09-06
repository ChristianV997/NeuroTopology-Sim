# Ecosystem Integration — Acceptance Document

Branch: `claude/ecosystem-integration`
Base: `origin/main` @ `62637a4b9c82c0c258bfc49e28dee1af757b1c25`
Owner: this branch only touches `tools/integration_bridge/**`,
`scripts/assemble_ecosystem_run.py`, `configs/integration/**`,
`docs/integration_acceptance.md`, `tests/integration/**`. No file outside
that list is modified by this branch.

## 1. Branch order

The mission expected seven dependency branches
(`codex/interop-signal-contracts`, `codex/scientific-falsification-contract`,
`antigravity/mne-scipy-streaming-eeg`,
`antigravity/test-isolation-dependency-profiles`,
`cursor/streaming-performance-benchmarks`, `grok/tool-admission-research`,
`grok-bot/retrofit-inventory`) to merge ahead of this integration. **None
of them exist on the `ChristianV997/NeuroTopology-Sim` remote** — verified
by `git fetch origin --prune` followed by an exact
`git rev-parse --verify origin/<name>` check for each name against the
full 154-branch remote enumeration (`git branch -r`). No `antigravity/`,
`grok/`, or `grok-bot/` namespace exists on this remote at all; the
`cursor/` namespace has three unrelated branches, none matching
`cursor/streaming-performance-benchmarks`.

Full detail, per-branch blocker text, and the exact seam each branch was
expected to fill (so it can slot in later without reshaping this code) is
in `configs/integration/dependency_matrix.yaml`. This PR was built and
validated standing alone against `origin/main`, with each of those seven
seams occupied by a documented placeholder or a real fallback to an
existing `main`-branch public adapter — never by a recreated
implementation of the missing branch's own work.

**Consequence for merge order:** this PR does not merge any of the seven
branches (there is nothing to merge). It is the integration *scaffold*
that those branches, when they exist, will be integrated through. Re-run
`configs/integration/dependency_matrix.yaml`'s branch check before the
next integration pass; if a branch has since appeared, its commit hash,
changed files, and CI status must be recorded there before it is
consumed.

## 2. Ownership boundaries

| Path | Owner | Notes |
|---|---|---|
| `tools/integration_bridge/**` | this branch | new package, no prior history |
| `scripts/assemble_ecosystem_run.py` | this branch | new file |
| `configs/integration/**` | this branch | new directory |
| `tests/integration/**` | this branch | new directory |
| `docs/integration_acceptance.md` | this branch | this file |
| everything else | unchanged | zero lines touched outside the five paths above (verified: `git diff --stat origin/main` after `git add` shows only new, untracked-turned-added files) |

This integration **consumes** the following existing public adapters
unmodified (full list with roles in `configs/integration/dependency_matrix.yaml`'s
`consumed_public_adapters`): `runs.run_record.RunRecordV1`/`build_run_id`,
`governance.spec.HypothesisSpec`, `governance.io.load_spec`,
`governance.validate.validate_spec`, `sim.pitnn.ingest_empirical.
ingest_empirical`, `sim.pitnn.mumax3_macro_tda.synthetic_signal`/
`invert_macro_signal`, `sim.pitnn.bayesian_falsification.compare_models`,
`core.topology.compute_Qz`/`compute_f_dress`, `analysis.
connectivity_topology.compute_beta1`, `sim.pitnn.topological_invariants.
TopologicalInvariantTracker`. None of these modules' source was edited.

## 3. Merge gates

Before this branch merges into `main`:

1. `python -m governance.validate` passes (all `governance/specs/*.yaml`
   valid) — unaffected by this branch, re-checked as a baseline.
2. `PYTHONPATH=. python -m pytest tests/integration -q` passes in full.
3. `python -m compileall -q tools/integration_bridge scripts/assemble_ecosystem_run.py tests/integration configs/integration` exits 0.
4. A changed-file audit (`git diff --stat origin/main`) shows only files
   under the five owned paths above.
5. A secret scan over the new files finds nothing (API keys, tokens,
   private key blocks, AWS access-key patterns).
6. No unresolved ownership collision: since no dependency branch exists,
   there is nothing to collide with this round; this gate is re-checked
   the next time a real dependency branch is integrated.
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

# This branch's own test suite
PYTHONPATH=. python -m pytest tests/integration -q

# Static checks
python -m compileall -q tools/integration_bridge scripts/assemble_ecosystem_run.py tests/integration configs/integration

# Manual smoke run (synthetic, no network, no dataset download)
python scripts/assemble_ecosystem_run.py --data-mode synthetic --output-dir /tmp/nts_smoke --dataset-id demo --seed 0
```

`scripts/run_tests_isolated.py --batch-size 8 --timeout-s 120` (the
repository-wide isolated runner) was **not** run in full for this PR: this
branch adds files only and edits none, so it carries zero regression risk
to the ~1600-file existing suite; running the full isolated batch runner
end-to-end is deferred to CI rather than this review pass. The commands
above are the actual, complete verification surface for what this PR
changes.

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

- [ ] `git diff --stat origin/main` shows only the five owned paths.
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

These are pre-existing conditions of the modules this integration
*consumes*, not defects introduced by this PR. They are recorded here
because `scripts/assemble_ecosystem_run.py` invokes the affected code
directly and this document is the place an integrator should see them
before trusting a packaged `PASS`/`NOT_SUPPORTED` verdict:

1. **`sim.pitnn.bayesian_falsification.compare_models`'s `K > 100` gate
   produces false `PASS` verdicts on pure noise at small sample sizes.**
   An empirical check (independent random noise as the topology
   regressor, `n=8`, 200 trials) found a 9% false-positive `PASS` rate at
   the function's own permitted minimum sample size (`n >= 8`); the rate
   falls to 0.5–1.5% by `n=128` but does not reach zero. Root cause: the
   gating statistic (`log_k = 0.5*n*log(rss_c/rss_q)`) omits the standard
   BIC-style model-complexity correction that the module's own
   correctly-computed `delta_aicc` would apply, and the gate uses the
   uncorrected statistic, not `delta_aicc`. This integration's
   `quality_gate.classify_status` downgrades any `PASS` computed from
   `data_mode="synthetic"` to `NOT_SUPPORTED`, which blocks the most
   direct abuse (a synthetic demo being reported as evidence), but does
   **not** fix the underlying false-positive risk for genuine small-`n`
   empirical data — that fix belongs in `sim/pitnn/bayesian_falsification.py`
   itself, outside this integration's ownership boundary.
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
3. **No multiple-comparisons correction exists anywhere in this
   repository's statistics stack** (`analysis/stats.py`,
   `analysis/permutation.py`). This integration's `analyze` stage invokes
   at most one topology metric per namespace per run, so it does not
   itself compound this gap, but any downstream cohort-level aggregation
   built on top of `scripts/assemble_ecosystem_run.py`'s output should
   apply its own correction before treating any per-metric significance
   claim as decisive.
4. **`streaming-performance-benchmarks` (cursor/), the streaming EEG
   adapter (antigravity/), and the tool-admission/retrofit-inventory
   research (grok/, grok-bot/) are all unavailable** (Section 1). This
   integration's `ingest` stage therefore runs the existing batch
   ingestion path (`sim.pitnn.ingest_empirical`), which loads a full
   recording into memory — there is no streaming, bounded-memory path
   yet, and no throughput/latency benchmark exists for this pipeline.
