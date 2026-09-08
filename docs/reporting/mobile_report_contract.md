# Mobile Research-State Report — Contract

Owner: `tools/mobile_report/**`, `scripts/compile_mobile_research_report.py`, `tests/mobile_report/**`.

This document is the contract for the mobile-compatible research report
compiler: one deterministic tool that reads local JSON/YAML/CSV evidence
files already produced elsewhere and compiles them into **one** readable
Markdown report (optimized for a phone screen), **one** strict JSON report,
and optional compact CSV summary tables — instead of many disconnected
files spread across `docs/release/**`, `outputs/**`, and various tool
output directories.

## Non-goals

- No network access, no `git`/`gh` invocations, no solver imports, no
  automatic directory scanning. The compiler reads exactly the files named
  in its input manifest and nothing else.
- Read-only with respect to every other evidence compiler in this repo:
  it does not modify `docs/release/**`, `tools/integration_reconciliation/**`,
  `governance/merge_gate.py`, existing artifact compilers, the Bayesian
  falsification implementation, signal adapters, streaming tools, CI
  workflows, dashboard routes, generated binary artifacts, or datasets. It
  only reads whatever JSON/YAML/CSV files those systems already produce,
  per the input contracts below.
- Enum vocabularies below intentionally reuse the ones already established
  in `configs/release/evidence_schema.yaml` (merge_status, status_category,
  claim_class, data_mode, verification_status fields, memory kind,
  release_recommendation) so this tool speaks the same language as the
  rest of the repo's evidence tooling without importing or depending on
  it. Where a distinction that schema does not define is needed (CI
  timeouts, the graph-beta-1 vs. spatial-charge topology split, local vs.
  independent checksum verification), a clearly documented tool-specific
  vocabulary is used instead.

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
  "topology_validation": "evidence/topology_validation.json",
  "falsification": "evidence/falsification.json",
  "merge_gate": "evidence/merge_gate.json"
}
```

Every key is optional. A key that is absent, or whose target file cannot
be read, parsed, or contains a non-finite numeric literal, produces a
report section with `"available": false` and an `"error"` string — it
never aborts compilation of the rest of the report. File **format** is
detected from the extension (`.json`, `.yaml`/`.yml`, `.csv`); a `.csv`
file is only valid for a section whose contract is a list of rows (every
section except `dashboard_isolation`), and its rows are wrapped under that
section's list key so `sections.py` never has to know which format a
given input arrived in.

### Input contract shapes

Numeric fields that are missing, non-numeric, or non-finite (NaN,
Infinity, `-Infinity`, and numeric-string spellings of the same, including
values that silently overflow to infinity such as `1e400`) are normalized
to `null`. Enum-like fields are normalized to `"unknown"` (or a
section-appropriate fallback) unless they exactly match one of the listed
literal values — nothing is inferred from context.

**`reconciliation`** — `{"pull_requests": [...]}`, each item:

| field | type | notes |
|---|---|---|
| `pr_number` | int | required |
| `branch` / `base_branch` | str \| null | if `base_branch` equals another PR's `branch`, that PR becomes a stacking parent |
| `parent_pr` | int \| null | explicit stacking parent, takes precedence over `base_branch` inference |
| `merge_status` | `"merged"｜"open"｜"draft"｜"branch_only"｜"blocked"｜"unverified"｜"closed"` | **Never inferred from the branch/PR existing.** `"branch_only"` means present in an integration branch but not merged to the default branch — this is the "merged versus integrated-only" distinction. |
| `status_category` | `"VERIFIED_MERGED"｜"OPEN_REVIEW"｜"DRAFT_REVIEW"｜"BRANCH_ONLY"｜"CI_BLOCKED"｜"BILLING_BLOCKED"｜"SUPERSEDED"｜"DUPLICATE"｜"SCIENTIFIC_REVIEW_REQUIRED"｜"UNVERIFIED"` | **Not** a `merge_status` value (per `evidence_schema.yaml`'s own hard rule) — this is what distinguishes an infrastructure/billing block from a scientific-review block. |
| `is_draft` | bool \| null | `merge_status=merged` with `is_draft=true` is a contradiction, flagged as a conflict. |
| `integration_status` | `"merged_to_main"｜"integrated_only"｜"not_integrated"` | |
| `mergeable` | bool \| null | |
| `ci_status` | `"passed"｜"failed"｜"pending"｜"not_started"｜"timed_out"｜"skipped"` | `"timed_out"` is distinct from both `"failed"` and `"not_started"`. |
| `superseded_by_pr` | int \| null | |
| `depends_on` | list[int] | explicit dependencies, in addition to stacking |
| `changed_files` | list[str] | for duplicate-ownership conflict detection |

**`agent_contributions`** (YAML, modeled on `docs/release/agent_contribution_matrix.yaml`) — an envelope with `repository`, `baseline_commit`, `evidence_source`, `inventory_is_not_evidence`, `merger_instruction`, `required_warnings` (folded into `scientific_limitations`, attributed), and `contributions: [...]`, each item:

`id`, `title`, `agent`, `branch`, `pr_number`, `section` (free-text label, not enum-validated), `merge_status`, `is_draft`, `changed_file_count`, `additions`, `deletions`, `limitations`, and:
- `verification_status`: `{existence, merge_status, scientific_pass, author_test_results, implementation_report}` — each its own `evidence_schema.yaml` enum. This is the "local checksum versus independent validation" axis: `verification_status.merge_status == "verified"` means independently confirmed (e.g. via `evidence_source: github_api`); this compiler's own `checksum` field (below) is never a substitute for that.
- `research_classification`: `{value_class, claim_class, data_mode, empirical_pass_allowed}` — `claim_class` is the "proxy evidence versus formal evidence" axis (`"empirical"` is the only formal value; `"proxy"`/`"synthetic"`/`"unsupported"`/`"unavailable"` are all explicitly weaker).

If the envelope's `baseline_commit` differs from `--integration-commit`, the report raises an `outdated_intermediate_commit` conflict rather than silently treating stale evidence as current.

**`dashboard_isolation`** (flat object, modeled on `tools/integration_reconciliation/dashboard_isolation.py`'s return shape) — `{"ok": bool | null, "scanned_files": int, "violations": [str], "evidence": str}`. `ok: null` means "not checked" and must never be read as passing.

**`test_runner`** — `{"jobs": [{"name", "status", "block_reason": "infrastructure"｜"billing"｜"scientific"｜null, "passed", "failed", "skipped", "duration_s"}]}`. A job with `status="not_started"` or `"timed_out"` is never counted as passing in any aggregate. `block_reason="billing"` combined with `status="passed"` is a `billing_not_pass` conflict — a billing block can never be a passing test result.

**`performance_benchmark`** / **`memory_evidence`** — `{"benchmarks": [{"name", "metric", "value", "unit", "baseline_value", "regression_pct", "status": "pass"｜"fail"}]}`. `memory_evidence` additionally carries `kind`: `"rss"｜"tracemalloc"｜"unavailable"` and `independently_verified`: bool \| null — unlabeled memory numbers are never treated as verified.

**`dataset_provenance`** — `{"datasets": [{"dataset_id", "data_mode", "source", "license", "checksum", "checksum_source": "local"｜"independent", "n_subjects", "notes"}]}`. `checksum_source` defaults to `"unknown"`, never `"independent"`, unless the source explicitly says so.

**`topology_validation`** — `{"checks": [{"name", "metric_family": "graph_beta_1"｜"spatial_charge"｜"other", "data_mode", "metric_value", "unit", "verdict": "PASS"｜"FAIL", "notes"}]}`. `graph_beta_1` (first Betti number / cycle rank from the fMRI-TDA graph pipeline, `contracts/fmri_tda/**`) and `spatial_charge` (Qz/Qabs/plaquette charge, `core/topology.py`) are two different metric families measuring two different things; a PASS on one is never rendered as evidence for the other, and the report's synthetic-vs-empirical and limitations sections call this out explicitly whenever both families are present.

**`falsification`** — `{"results": [{"hypothesis_id", "claim_class", "data_mode", "metric_type", "metric_value", "unit", "verdict": "PASS"｜"FAIL"｜"INCONCLUSIVE", "notes"}]}`. `metric_type` is rendered verbatim; only the literal value `"bayes_factor"` is ever displayed using the phrase "Bayes factor" — everything else (e.g. `"proxy_K"`) is displayed as `"<metric_type> (not a formal Bayes factor)"`. `claim_class in {synthetic, proxy, unsupported}` combined with `verdict=PASS` is a `synthetic_pass_claim` conflict.

**`merge_gate`** — `{"decisions": [{"pr_number", "decision": "allow"｜"block"｜"hold", "block_reason": "infrastructure"｜"billing"｜"scientific"｜null, "reason"}]}`.

## Output contract

`compile_report()` (in `tools/mobile_report/compiler.py`) returns one dict
whose top-level keys map directly onto the required Markdown sections:
`repository_and_integration_commit`, `agent_contribution_table`,
`pr_state`, `merge_status_by_category`, `stacked_relationships`,
`superseded_work`, `conflicts`, `ci_status`,
`billing_infrastructure_status`, `test_totals`, `timeouts`,
`performance_evidence`, `memory_evidence`, `provenance_status`,
`topology_validation_status`, `falsification_status`,
`scientific_limitations`, `dashboard_isolation`, `unresolved_blockers`,
`exact_next_actions`, `final_release_recommendation`,
`recommended_merge_order`, `merge_gate_decisions`. Plus metadata:
`report_schema_version`, `compiler_version`, `generated_at`, `status`
(`"complete"` or `"partial"`), `completeness`, `provenance`
(manifest path + per-input sha256 checksums, explicitly scoped
`"checksum_scope": "local"`).

`scripts/compile_mobile_research_report.py` writes this dict as
`mobile_research_report.json` (`json.dumps(..., indent=2, sort_keys=True,
allow_nan=False)`), a matching `mobile_research_report.md`
(`tools/mobile_report/render_markdown.py`), and, when `csv` is requested,
a `csv/` directory of compact summary tables
(`tools/mobile_report/render_csv.py`) — never binary plots or datasets.

### Mobile-readable section ordering

The Markdown report opens with a short, no-wide-table summary block —
final release recommendation, repo/commit, unresolved-blocker count, and
the top next actions — within its first ~15 lines, so a reviewer on a
phone gets the actionable answer before scrolling through detail
sections. Every table below that point is kept to a handful of narrow
columns (never more than five) so it renders without horizontal
scrolling in a typical mobile Markdown viewer.

## Guardrails

Enforced in code (`tools/mobile_report/guardrails.py`,
`tools/mobile_report/graph.py`, `tools/mobile_report/compiler.py`), not
just documented:

1. **No network access, no solver imports, no automatic data loading.**
   The compiler only reads the exact paths named in its manifest.
2. **No fabricated fields; null for missing values.** Every field not
   explicitly present in the source, or not one of its declared enum
   literals, is `null`/`"unknown"` — never guessed or inferred from
   another field.
3. **Reject NaN and Infinity.** `guardrails.safe_number` rejects
   non-finite values regardless of representation (native float, numeric
   string, or JSON/YAML literal), including numbers that silently
   overflow to infinity (`1e400`).
4. **Deterministic ordering.** Every list is sorted by a stable key
   before being placed in the report; JSON is serialized with
   `sort_keys=True`. The only non-deterministic field is `generated_at`
   (pass `--now` / `now=` to pin it).
5. **Schema version / compiler version / source manifest / input
   checksums** — `report_schema_version`, `compiler_version`,
   `provenance.manifest_path`, `provenance.source_checksums` (sha256 per
   file actually read, explicitly labeled `"checksum_scope": "local"` —
   see distinction 10 below).
6. **Explicit incomplete-report status.** `status` is `"partial"`
   whenever any input section is unavailable; `final_release_recommendation`
   becomes `"INCOMPLETE_EVIDENCE"` in that case rather than a guess.
7. **No committed binary plots or datasets.** Only JSON/Markdown/CSV text
   outputs are ever written.

### The eight required distinctions

8. **Merged versus integrated-only** — `merge_status="merged"` combined
   with `integration_status` of `"integrated_only"`/`"not_integrated"` is
   flagged as an `open_pr_represented_as_merged` conflict.
9. **Open versus draft** — `merge_status="merged"` with `is_draft=true`
   is a contradiction, flagged the same way.
10. **Test failure versus unstarted CI** — `ci_status`/job `status`
    distinguish `"failed"`, `"not_started"`, and `"timed_out"` as three
    separate outcomes; none of the latter two is ever counted as passing.
11. **Infrastructure block versus scientific failure** — `status_category`
    (`CI_BLOCKED`/`BILLING_BLOCKED` vs. `SCIENTIFIC_REVIEW_REQUIRED`) and
    `block_reason` (`"infrastructure"`/`"billing"` vs. `"scientific"`) are
    kept as separate fields; `billing_infrastructure_status` and
    `final_release_recommendation`'s waterfall never conflate the two.
12. **Synthetic versus empirical** — `data_mode` is passed through only
    when it is a literal value from `evidence_schema.yaml`'s vocabulary.
13. **Proxy evidence versus formal evidence** — `claim_class` (only
    `"empirical"` is ever labeled formal) and the falsification
    `metric_type` labeling (only `"bayes_factor"` is ever labeled
    "Bayes factor") are two independent guardrails on this axis.
14. **Graph beta-1 versus spatial charge** — `metric_family` keeps the
    two topology metric families (`graph_beta_1`, `spatial_charge`)
    separately tallied and never blended into one verdict; when both are
    present, `scientific_limitations` says so explicitly.
15. **Local checksum versus independent validation** — `provenance.source_checksums[*].checksum_scope` is always `"local"`
    (this compiler computed it from the bytes it read); only
    `verification_status.merge_status == "verified"` (or an evidence
    document's own `evidence_source: github_api`-style field) may be
    described as independently verified.

## Determinism

`compile_report(manifest_path, now=..., repo=..., integration_ref=...,
integration_commit=...)` is a pure function of its arguments and the
contents of the files the manifest points to: no network calls, no `git`
invocations, no wall-clock reads unless `now` is omitted. Two compiles
with the same manifest, input files, and `now` value produce
byte-identical JSON and Markdown.

## CLI

```bash
python -m scripts.compile_mobile_research_report \
    --manifest governance/mobile_report/manifest.json \
    --output-dir artifacts/mobile_research_report \
    --formats markdown,json,csv \
    --now 2026-01-01T00:00:00+00:00 \
    --repo NeuroTopology-Sim --integration-ref codex/integration-all-open-prs \
    --integration-commit be277ecdac301d49dca27ef9612ebe6c560245ad
```

## Versioning

- `REPORT_SCHEMA_VERSION` (`tools/mobile_report/versions.py`): bump on any
  change to the output JSON/Markdown/CSV shape.
- `COMPILER_VERSION`: bump on any behavior change, including bug fixes,
  even when the output shape is unchanged.
