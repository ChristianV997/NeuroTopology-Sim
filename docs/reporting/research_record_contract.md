# Research Record — Contract

Owner: `tools/research_record/**`, `scripts/build_research_record.py`, `tests/research_record/**`.

## Collision note

Before writing any file in this package, this repository was checked for
an equivalent compiler. Two were found, both open and unmerged as of this
writing:

- [PR #239](https://github.com/ChristianV997/NeuroTopology-Sim/pull/239) — `tools/research_report/**` ("unified research-state and evidence-report compiler")
- [PR #252](https://github.com/ChristianV997/NeuroTopology-Sim/pull/252) — `tools/mobile_report/**` ("mobile-compatible research report compiler")

Both read the same broad categories of local evidence (PR/branch
reconciliation, agent contributions, dashboard isolation, test-runner,
performance/memory, provenance, topology, falsification, merge-gate) and
compile them into a deterministic Markdown + JSON (+ optional CSV) report
with an overlapping set of guardrails (synthetic-vs-empirical,
proxy-vs-formal evidence, checksum-vs-independent-verification,
graph-beta-1-vs-spatial-charge, billing-not-pass). This package was
explicitly instructed to be built anyway, at its own unowned path
(`tools/research_record/**`, distinct from both `tools/research_report/**`
and `tools/mobile_report/**`), rather than duplicating either — so it does
not import, wrap, or depend on either prior package, and adds the sections
neither of them has: branch ancestry, duplicate-vs-superseded decisions
(with a recommended action per PR), changed-file ownership as its own
section, a verified integration head (rather than trusting a CLI-supplied
commit at face value), cohort readiness, and an explicit
engineering-status/scientific-status split. A human should reconcile which
of the three survives before any of them is merged to `main`.

## What this compiler does

A deterministic tool that reads local JSON/YAML/CSV evidence files already
produced elsewhere and compiles them into **one** mobile-readable Markdown
record, **one** strict JSON record, and optional compact CSV summary
tables.

## Non-goals

- No network access, no `git`/`gh` invocations, no solver imports (rules
  13/14), no automatic directory scanning. The compiler reads exactly the
  files named in its input manifest and nothing else.
- Read-only with respect to every other evidence compiler in this repo:
  it does not modify `docs/release/**`, `tools/integration_reconciliation/**`,
  `configs/release/**`, `governance/merge_gate.py`, existing artifact
  compilers, the Bayesian falsification implementation, signal adapters,
  streaming tools, CI workflows, dashboard routes, generated binary
  artifacts, or datasets. It only reads whatever JSON/YAML/CSV files those
  systems already produce, per the input contracts below.
- Enum vocabularies below intentionally reuse the ones already established
  in `configs/release/evidence_schema.yaml` (merge_status, status_category,
  claim_class, data_mode, verification_status fields, memory kind,
  release_recommendation) so this tool speaks the same language as the
  rest of the repo's evidence tooling without importing or depending on
  it. Where a distinction that schema does not define is needed (CI
  timeouts, a scientific TIMEOUT verdict, the graph-beta-1 vs.
  spatial-charge topology split, local vs. independent checksum
  verification), a clearly documented tool-specific vocabulary is used
  instead.

## Input manifest

A manifest file (JSON or YAML) maps input-contract names to file paths
(relative paths resolve against the manifest's own directory):

```json
{
  "reconciliation": "evidence/reconciliation.json",
  "agent_contributions": "evidence/agent_contribution_matrix.yaml",
  "dashboard_isolation": "evidence/dashboard_isolation.json",
  "test_runner": "evidence/test_runner.json",
  "performance_benchmark": "evidence/performance_benchmark.json",
  "memory_evidence": "evidence/memory_evidence.csv",
  "dataset_provenance": "evidence/dataset_provenance.json",
  "cohort_readiness": "evidence/cohort_readiness.json",
  "topology_validation": "evidence/topology_validation.json",
  "falsification": "evidence/falsification.json",
  "merge_gate": "evidence/merge_gate.json"
}
```

Every key is optional. A key that is absent, or whose target file cannot
be read, parsed, or contains a non-finite numeric literal, produces a
record section with `"available": false` and an `"error"` string — it
never aborts compilation of the rest of the record (rule 9). File
**format** is detected from the extension (`.json`, `.yaml`/`.yml`,
`.csv`); a `.csv` file is only valid for a section whose contract is a
list of rows (every section except `dashboard_isolation`), and its rows
are wrapped under that section's list key so `sections.py` never has to
know which format a given input arrived in.

Every record within a section carries that section's `source_path`/
`checksum` provenance (they were all read from one file in one atomic
load) — this is how rule 11 ("all source records must retain provenance")
is satisfied without redundant per-record duplication of the same two
fields.

### Input contract shapes

Numeric fields that are missing, non-numeric, or non-finite (NaN,
Infinity, `-Infinity`, and numeric-string spellings of the same, including
values that silently overflow to infinity such as `1e400`) are normalized
to `null` (rule 10). Enum-like fields are normalized to `"unknown"` (or a
section-appropriate fallback) unless they exactly match one of the listed
literal values — nothing is inferred from context (rule 9).

**`reconciliation`** — `{"pull_requests": [...]}`, each item:

| field | type | notes |
|---|---|---|
| `pr_number` | int | required |
| `branch` / `base_branch` | str \| null | if `base_branch` equals another PR's `branch`, that PR becomes a stacking parent |
| `parent_pr` | int \| null | explicit stacking parent, takes precedence over `base_branch` inference |
| `merge_status` | `"merged"｜"open"｜"draft"｜"branch_only"｜"blocked"｜"unverified"｜"closed"` | **Never inferred from the branch/PR existing** (rules 1–2). `"branch_only"` means present in an integration branch but not merged to the default branch. |
| `status_category` | `"VERIFIED_MERGED"｜"OPEN_REVIEW"｜"DRAFT_REVIEW"｜"BRANCH_ONLY"｜"CI_BLOCKED"｜"BILLING_BLOCKED"｜"SUPERSEDED"｜"DUPLICATE"｜"SCIENTIFIC_REVIEW_REQUIRED"｜"UNVERIFIED"` | **Not** a `merge_status` value. `CI_BLOCKED`/`BILLING_BLOCKED` are engineering-status categories; `SCIENTIFIC_REVIEW_REQUIRED` is a scientific-status one — kept separate per rule 12. |
| `is_draft` | bool \| null | `merge_status=merged` with `is_draft=true` is a contradiction, flagged as a conflict. |
| `is_ancestor_of_target` | bool \| null | branch ancestry — `merge_status=merged` with `is_ancestor_of_target=false` is a contradiction (rule 1: a local merge commit does not prove a main-branch merge). |
| `integration_status` | `"merged_to_main"｜"integrated_only"｜"not_integrated"` | |
| `mergeable` | bool \| null | |
| `ci_status` | `"passed"｜"failed"｜"pending"｜"not_started"｜"timed_out"｜"skipped"` | `"timed_out"` is distinct from both `"failed"` and `"not_started"` (rule 3). |
| `superseded_by_pr` | int \| null | |
| `duplicate_of_pr` | int \| null | |
| `depends_on` | list[int] | explicit dependencies, in addition to stacking |
| `changed_files` | list[str] | for changed-file-ownership / duplicate-ownership detection |

**`agent_contributions`** (YAML, modeled on `docs/release/agent_contribution_matrix.yaml`) — an envelope with `repository`, `baseline_commit`, `evidence_source`, `inventory_is_not_evidence`, `merger_instruction`, `required_warnings` (folded into `scientific_limitations`, attributed), and `contributions: [...]`, each item:

`id`, `title`, `agent`, `branch`, `pr_number`, `section` (free-text label, not enum-validated), `merge_status`, `is_draft`, `changed_file_count`, `additions`, `deletions`, `limitations`, and:
- `verification_status`: `{existence, merge_status, scientific_pass, author_test_results, implementation_report}` — each its own `evidence_schema.yaml` enum. `verification_status.merge_status == "verified"` (from an `evidence_source: github_api`-class document) is the only thing this compiler treats as "verified" — its own `checksum` field (below) is never a substitute for that (rule 6).
- `research_classification`: `{value_class, claim_class, data_mode, empirical_pass_allowed}` — `claim_class` is the proxy-vs-formal-evidence axis (`"empirical"` is the only formal value).

The envelope's `evidence_source` and `baseline_commit` are also how
`integration_branch_and_verified_head.verified` is computed — see below.

**`dashboard_isolation`** (flat object, modeled on `tools/integration_reconciliation/dashboard_isolation.py`'s return shape) — `{"ok": bool | null, "scanned_files": int, "violations": [str], "evidence": str}`. `ok: null` means "not checked" and must never be read as passing.

**`test_runner`** — `{"jobs": [{"name", "status", "block_reason": "infrastructure"｜"billing"｜"scientific"｜null, "passed", "failed", "skipped", "duration_s"}]}`. A job with `status="not_started"` or `"timed_out"` is never counted as passing in any aggregate (rule 3). `block_reason="billing"` combined with `status="passed"` is a `billing_not_pass` conflict.

**`performance_benchmark`** / **`memory_evidence`** — `{"benchmarks": [{"name", "metric", "value", "unit", "baseline_value", "regression_pct", "status": "pass"｜"fail"}]}`. `memory_evidence` additionally carries `kind`: `"rss"｜"tracemalloc"｜"unavailable"` and `independently_verified`: bool \| null.

**`dataset_provenance`** — `{"datasets": [{"dataset_id", "data_mode", "source", "license", "checksum", "checksum_source": "local"｜"independent", "n_subjects", "notes"}]}`. `checksum_source` defaults to `"unknown"`, never `"independent"`, unless the source explicitly says so (rule 6).

**`cohort_readiness`** — `{"cohorts": [{"cohort_id", "n_subjects", "n_required", "paired": bool, "data_mode", "checksum_source", "notes"}]}`. `ready` is **not** read from the source — it is derived by this compiler as `data_mode == "empirical" and n_subjects >= n_required and paired is True`, so a source document cannot simply assert readiness.

**`topology_validation`** — `{"checks": [{"name", "metric_family": "graph_beta_1"｜"spatial_charge"｜"other", "data_mode", "metric_value", "unit", "verdict": "PASS"｜"FAIL"｜"INCONCLUSIVE"｜"TIMEOUT", "notes"}]}`. `graph_beta_1` (first Betti number / cycle rank from the fMRI-TDA graph pipeline, `contracts/fmri_tda/**`) and `spatial_charge` (Qz/Qabs/plaquette charge, `core/topology.py`) are two different metric families measuring two different things (rule 7); a PASS on one is never rendered as evidence for the other. `"TIMEOUT"` is a distinct verdict from `"FAIL"` — a check that never finished produced no scientific outcome at all (rule 8) and is tracked under `engineering_status`, not counted toward pass/fail tallies.

**`falsification`** — `{"results": [{"hypothesis_id", "claim_class", "data_mode", "metric_type", "metric_value", "unit", "verdict": "PASS"｜"FAIL"｜"INCONCLUSIVE"｜"TIMEOUT", "notes"}]}`. Only the literal `metric_type` value `"bayes_factor"` is ever displayed using the phrase "Bayes factor" — everything else (e.g. `"proxy_K"`) is displayed as `"<metric_type> (not a formal Bayes factor)"` (rule 4). `claim_class in {synthetic, proxy, unsupported}` combined with `verdict=PASS` is a `synthetic_pass_claim` conflict (rule 5).

**`merge_gate`** — `{"decisions": [{"pr_number", "decision": "allow"｜"block"｜"hold", "block_reason": "infrastructure"｜"billing"｜"scientific"｜null, "reason"}]}`.

## Output contract

`compile_record()` (in `tools/research_record/compiler.py`) returns one
dict whose top-level keys map directly onto the required sections:
`repository_identity`, `origin_main_commit`,
`integration_branch_and_verified_head`, `agent_contribution_table`,
`pr_state`, `pr_buckets` (open/draft/closed/merged/integrated_only),
`branch_ancestry`, `stacked_dependencies`, `duplicate_superseded_decisions`,
`changed_file_ownership`, `conflicts`, `ci_status`,
`billing_runner_status`, `test_totals`, `failures`, `timeouts`,
`performance_evidence`, `memory_evidence`, `provenance`,
`cohort_readiness`, `topology_readiness`, `falsification_semantics`,
`scientific_limitations`, `dashboard_isolation`, `engineering_status`,
`scientific_status`, `unresolved_blockers`, `next_actions`,
`final_release_recommendation`, `recommended_merge_order`,
`merge_gate_decisions`. Plus metadata: `report_schema_version`,
`compiler_version`, `generated_at`, `status` (`"complete"` or
`"partial"`), `completeness`, `record_provenance` (manifest path +
per-input sha256 checksums, explicitly scoped `"checksum_scope": "local"`
— see rule 6).

`scripts/build_research_record.py` writes this dict as
`research_record.json` (`json.dumps(..., indent=2, sort_keys=True,
allow_nan=False)`), a matching `research_record.md`
(`tools/research_record/render_markdown.py`, summary block first for
mobile review), and, when `csv` is requested, a `csv/` directory of
compact summary tables (`tools/research_record/render_csv.py`) — never
binary plots or datasets (rule 15).

## The 15 strict rules and where they're enforced

1. **A local merge commit does not prove main-branch merge.** `merge_status=merged` combined with `is_ancestor_of_target=false` or `integration_status` of `"integrated_only"`/`"not_integrated"` is an `open_pr_represented_as_merged` conflict (`compiler.py::_merged_but_not_actually_merged_conflicts`); `integration_branch_and_verified_head.verified` requires independently-sourced corroboration, not just a CLI-supplied commit (`compiler.py::_integration_head_verification`).
2. **A branch does not prove PR merge.** `guardrails.normalize_merge_status` never infers `"merged"` from anything but an explicit literal; `merge_status=merged` with `is_draft=true` is the same conflict class as above.
3. **An unstarted CI job is not a passing test.** `CI_STATUS` keeps `"not_started"`/`"timed_out"`/`"failed"` as three separate values (`guardrails.py`); none is ever counted as `"passed"` in any total.
4. **A proxy Bayes factor is not formal evidence.** `guardrails.metric_label` labels only the literal `"bayes_factor"` as "Bayes factor"; everything else is explicitly "(not a formal Bayes factor)".
5. **Synthetic results cannot be empirical evidence.** `guardrails.normalize_data_mode`/`normalize_claim_class` never upgrade a declared `"synthetic"`/`"proxy"` value; `synthetic_pass_claim` conflicts fire whenever such a value is paired with `verdict=PASS` or an empirical-pass claim (`compiler.py::_synthetic_and_proxy_pass_conflicts`).
6. **A checksum is not independent validation.** `record_provenance.source_checksums[*].checksum_scope` is always `"local"`; only `verification_status.merge_status == "verified"` / `evidence_source: github_api` may be described as independently verified.
7. **Graph beta-1 is not spatial charge.** `metric_family` (`guardrails.normalize_metric_family`) keeps the two topology families separately tallied in `scientific_status.topology_family_verdict_counts`, never blended into one verdict.
8. **A timeout is not a scientific outcome.** `SCIENTIFIC_VERDICT` includes `"TIMEOUT"` as its own value, distinct from PASS/FAIL/INCONCLUSIVE; timed-out checks are excluded from `_synthetic_and_proxy_pass_conflicts` and instead surfaced under `engineering_status.scientific_check_timeouts` — they route the final recommendation to `BLOCKED_BY_CI`, never `BLOCKED_BY_SCIENTIFIC_VALIDATION`.
9. **Missing values must be null.** Every normalizer in `guardrails.py` degrades to `null`/`"unknown"` rather than guessing; absent manifest sections produce `"error": "not_provided"`.
10. **NaN and Infinity must be rejected.** `evidence_loader.py` rejects non-finite JSON/YAML literals at load time; `guardrails.safe_number` rejects non-finite values (including numeric strings and silent-overflow literals like `1e400`) at the field level.
11. **All source records must retain provenance.** Every section carries its `source_path`/`checksum`; `record_provenance.manifest_path` names the manifest itself.
12. **The record must distinguish engineering status from scientific status.** `engineering_status` (CI/billing/dashboard/timeouts) and `scientific_status` (topology/falsification/cohort/synthetic-PASS violations) are two separate top-level sections with independent `label`s (`compiler.py::_engineering_status`, `_scientific_status`); the final-recommendation waterfall routes billing/CI/timeout conflicts to `BLOCKED_BY_CI` and only `synthetic_pass_claim` to `BLOCKED_BY_SCIENTIFIC_VALIDATION`.
13. **No network access during tests.** The compiler makes no HTTP/socket/subprocess calls anywhere in `tools/research_record/**`; tests exercise it purely against local fixture files.
14. **No solver imports.** Nothing here imports `sim.pitnn`, `core.topology`, `physics.exact_dynamics`, or any other scientific solver — evidence about their results arrives pre-computed, as JSON/YAML/CSV.
15. **No generated datasets or binary artifacts may be committed.** Only JSON/Markdown/CSV text outputs are ever written by this package; none are committed as part of it.

## Determinism

`compile_record(manifest_path, now=..., repo=..., origin_main_commit=...,
integration_ref=..., integration_commit=...)` is a pure function of its
arguments and the contents of the files the manifest points to: no
network calls, no `git` invocations, no wall-clock reads unless `now` is
omitted. Two compiles with the same manifest, input files, and `now`
value produce byte-identical JSON and Markdown.

## CLI

```bash
python -m scripts.build_research_record \
    --manifest governance/research_record/manifest.json \
    --output-dir artifacts/research_record \
    --formats markdown,json,csv \
    --now 2026-01-01T00:00:00+00:00 \
    --repo NeuroTopology-Sim --origin-main-commit 62aa8fe... \
    --integration-ref codex/integration-all-open-prs \
    --integration-commit be277ecdac301d49dca27ef9612ebe6c560245ad
```

## Versioning

- `REPORT_SCHEMA_VERSION` (`tools/research_record/versions.py`): bump on
  any change to the output JSON/Markdown/CSV shape.
- `COMPILER_VERSION`: bump on any behavior change, including bug fixes,
  even when the output shape is unchanged.
