# Scientific Release Audit

Branch: `claude/integrated-scientific-release-audit`, based on
`origin/codex/integration-all-open-prs` (PR #236, head
`be277ecdac301d49dca27ef9612ebe6c560245ad`). Owns exclusively:
`tools/release_scientific_audit/**`, `scripts/audit_integrated_release.py`,
`tests/release_scientific_audit/**`, `docs/release/scientific_release_audit.md`.
Touches nothing in `sim/pitnn/bayesian_falsification.py`,
`tools/integration_reconciliation/**`, `governance/merge_gate.py`, any CI
workflow, signal adapter, streaming tool, dashboard route, generated
artifact, or dataset.

## What this is

A read-only audit: `tools.release_scientific_audit.audit.run_audit(AuditInput) -> AuditReport`
consumes a single JSON document describing eight already-produced report
categories (merge matrix, scientific-gate report, provenance records,
falsification payloads, topology summaries, capability snapshot, test
summary, CI status), runs 15 named checks over it, and derives one of six
release decisions — **never adjusting a scientific finding to make the
release look better**. Like the two prior tools in this reconciliation
effort (`tools/integration_reconciliation`, `governance/merge_gate`),
this package has zero import dependency on either of them or on
`sim/pitnn/bayesian_falsification.py`: everything it knows comes from the
JSON document a caller supplies, plus one independent, self-contained
static check (dashboard-solver-import scanning) it performs directly
against source text.

## The 15 audit checks and where they live

| # | Check | Module |
|---|---|---|
| 1 | Synthetic vs. empirical provenance | `provenance_checks.check_synthetic_vs_empirical_provenance` |
| 2 | Proxy vs. formal evidence | `evidence_checks.check_proxy_vs_formal_evidence` |
| 3 | K > 100 gate semantics | `evidence_checks.check_k_gate_semantics` |
| 4 | Null-control presence | `evidence_checks.check_null_control_presence` |
| 5 | Sample-size / effective-N fields | `provenance_checks.check_sample_size_and_effective_n` |
| 6 | Multiple-comparison status | `evidence_checks.check_multiple_comparison_status` |
| 7 | Wilson-Cowan model labeling | `evidence_checks.check_wilson_cowan_labeling` |
| 8 | Graph beta-1 vs. spatial charge separation | `topology_checks.check_topology_namespace_separation` |
| 9 | Dashboard solver isolation | `dashboard_isolation.check_dashboard_solver_isolation` (independent static AST scan) |
| 10 | Memory/performance claims | `engineering_checks.check_performance_claims` |
| 11 | Optional dependency availability | `engineering_checks.check_optional_dependency_availability` |
| 12 | Unresolved failures and timeouts | `engineering_checks.check_unresolved_failures_and_timeouts` |
| 13 | Claims exceeding actual evidence | `claims_checks.check_claims_exceeding_evidence` |
| 14 | Missing provenance / incomplete metadata | `provenance_checks.check_missing_provenance` |
| 15 | Release label | `decision.derive_release_decision` |

(An extra, closely related check — `evidence_checks.check_finite_numeric_fields`
— catches a non-finite value anywhere in a falsification payload's own
numeric fields; folded under check 2's module since it's the same class
of "is this evidence document itself trustworthy" question.)

## Findings, severity, and "insufficient data"

Every check returns `Finding(check, severity, summary, evidence_source, detail, insufficient_data)`.
`severity` is `"info"` / `"warning"` / `"blocking"`. `insufficient_data=True`
marks a blocking finding that exists **only** because a required input
document was absent entirely ("we don't know") — kept distinct from a
genuine, evidenced problem ("we know, and it's bad") so the release
decision can tell the two apart: a release with real evidence of a
problem is reported as such even if *other* inputs also happen to be
missing; a release with *only* missing-input findings and no genuine
problem anywhere is `INCONCLUSIVE`, never quietly waved through as clean.

## Release decision priority order

`decision.derive_release_decision` evaluates in this fixed order:

1. No blocking findings at all → `RELEASE_READY` (or `REVIEW_ONLY` if
   warnings exist).
2. Blocking findings that are all `insufficient_data` → `INCONCLUSIVE`.
3. A genuine safety-gate violation (dashboard solver import) →
   `BLOCKED_BY_SCIENCE` (`DASHBOARD_SOLVER_ISOLATION_VIOLATION`) — checked
   first among genuine blockers, mirroring the merge-gate policy's own
   Tier-0 safety-first ordering.
4. Any other genuine scientific-check blocker (checks 1-8, 10, 13, plus
   the finite-numeric-fields check) → `BLOCKED_BY_SCIENCE`, reason codes
   naming each contributing check. This is checked **before** plain
   test/infrastructure failures, per "scientific claims require stricter
   gates than ordinary code changes" — a release is never reported as
   merely test-blocked when it also has an unresolved scientific problem.
5. A genuine real (non-infrastructure) test failure or timeout →
   `BLOCKED_BY_TESTS`.
6. A genuine infrastructure/billing-blocked CI check or an unclassified
   required optional dependency → `BLOCKED_BY_INFRASTRUCTURE`.
7. Any other genuine blocking finding that matched none of the above →
   `INCONCLUSIVE`.

`claims_checks.check_claims_exceeding_evidence`'s findings are always
`"warning"`, never `"blocking"` on their own — they only flag that a
human-facing label (a merge-matrix reason, the gate report's own
`overall_status_label`) is out of step with findings that *already*,
independently, produced a blocking decision elsewhere. This was a real
bug caught during this branch's own development: an early version made
these findings `"blocking"`, which meant ANY release with an optimistic-
sounding label and ANY other blocker (even a pure CI failure) got
reclassified as `BLOCKED_BY_SCIENCE` regardless of the real problem's own
category. Fixed; see `test_clean_engineering_only_release_is_release_ready`
and the `failed_ci`/`timed_out_tests`/`missing_optional_dependencies`
fixture tests, which pinned this down.

## Manual dry-run against the real PR #236

GitHub access was available, so PR #236's live state and its integration
branch's own `docs/release/*.md` reports were read directly (not
reconstructed from memory). Two things worth flagging up front:

**The task's summary numbers for this integration do not match PR #236's
own current body.** The brief stated "401 files, 63 isolated batches, 6
failures, 4 timeouts." PR #236's own description (fetched live) says:
*"Mandated isolated run: 415 files / 75 bounded batches; 64 passed, 8
failed, 3 timed out; exit 124."* `docs/release/full_test_summary.md` on
the integration branch confirms the same 415/75/64/8/3 numbers. The audit
below uses the PR's own, fresher numbers, not the task brief's — an
instance of check 13 (claims exceeding/diverging from evidence) applied
to the task's own framing, not just the release's.

**The audit's independent Wilson-Cowan check disagrees with a plain
reading of the integration's own scientific-gate report in a way that
matters.** `docs/release/scientific_gate_report.md` states *"Wilson–Cowan
and related comparisons remain proxy-labeled"* — meaning the label is
honest about being a proxy, which sounds like good hygiene. But "proxy-
labeled" is a claim about the *evidence kind* (a different question,
audit check 2); it never states that the baseline literally named
`classical_wilson_cowan` actually implements the real Wilson-Cowan model
(a distinct, unresolved question this session's earlier independent
scientific review of `sim/pitnn/bayesian_falsification.py` already found
to be false — the baseline is a 4-parameter harmonic regression, not the
real neural-mass model). Since no field in any of the integration
branch's release docs confirms `classical_baseline_is_real_wilson_cowan`,
this audit's reconstruction correctly leaves it `false` (the known,
previously-established truth) and check 7 fires as `blocking`.

Reconstructed input (traced field-by-field to the quoted docs, saved as
`tests/release_scientific_audit/fixtures/real_pr236_dry_run_2026-09-07.json`):

```bash
python scripts/audit_integrated_release.py \
  --input tests/release_scientific_audit/fixtures/real_pr236_dry_run_2026-09-07.json \
  --output-dir /tmp/pr236_audit
```

**Result: `BLOCKED_BY_SCIENCE`** (`WILSON_COWAN_LABELING`), with the
following also surfaced as blocking findings in the same report (none
hidden, all still visible even though Wilson-Cowan mislabeling is the
top-level reason): 8 real local test failures, 3 real local test
timeouts, 1 GitHub-Actions-level infrastructure/billing block, and an
`insufficient_data`-marked absence of structured per-component provenance
records (the release docs are prose, not machine-readable records). This
independently corroborates — with a more precise, itemized reason — the
integration branch's own self-declared `"INCONCLUSIVE / NOT
RELEASE-READY"` status and its `"HOLD — review open PR #236; do not
merge into main"` recommendation in `docs/release/unresolved_blockers.md`.

## Test commands

```bash
PYTHONPATH=. python -m pytest tests/release_scientific_audit -q   # 76 passed
python -m governance.validate                                     # 4/4 specs pass (baseline, unaffected)
python -m compileall -q tools/release_scientific_audit scripts/audit_integrated_release.py tests/release_scientific_audit
```

No test in `tests/release_scientific_audit/` calls a network API, a git
command, or executes any scientific/CI code — every fixture is a plain
JSON file or an in-memory dataclass, and the one filesystem interaction
(dashboard-isolation scanning) only ever reads `.py` source text via
`ast.parse`.

## The ten required fixture scenarios

All under `tests/release_scientific_audit/fixtures/`, exercised by
`test_fixtures_release_decision.py`:

| Fixture | Decision |
|---|---|
| `clean_engineering_only.json` | `RELEASE_READY` |
| `synthetic_only_run.json` (synthetic data wrongly claims PASS) | `BLOCKED_BY_SCIENCE` |
| `incomplete_empirical_provenance.json` | `BLOCKED_BY_SCIENCE` |
| `proxy_bayes_factor.json` (proxy evidence claims PASS) | `BLOCKED_BY_SCIENCE` |
| `formal_evidence_absence.json` (no evidence_kind declared, verdict NOT_SUPPORTED) | `REVIEW_ONLY` |
| `dashboard_solver_import.json` (+ a tmp_path-built bad dashboard source) | `BLOCKED_BY_SCIENCE` |
| `failed_ci.json` | `BLOCKED_BY_TESTS` |
| `timed_out_tests.json` | `BLOCKED_BY_TESTS` |
| `missing_optional_dependencies.json` | `BLOCKED_BY_INFRASTRUCTURE` |
| `non_finite_report_values.json` | `BLOCKED_BY_SCIENCE` |

Every scenario is also asserted deterministic (10 repeat calls each,
byte-identical `Finding` lists and decision).

## Input schema

See `tools/release_scientific_audit/models.py` (every dataclass has
inline field comments) and `tools/release_scientific_audit/loaders.py`
for the exact JSON shape; `tests/release_scientific_audit/fixtures/clean_engineering_only.json`
is a complete, minimal worked example of every section populated.
