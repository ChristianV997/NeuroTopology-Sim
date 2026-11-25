# Unified Research-State Report — Contract

Owner: `tools/research_report/**`, `scripts/compile_research_state.py`, `tests/research_report/**`.

This document is the contract for the deterministic research-state and
evidence-report compiler. It compiles evidence documents already produced by
other tools (PR reconciliation, capability snapshots, dataset provenance,
falsification results, benchmark summaries, topology validation, test-runner
summaries, merge-gate decisions, PR-retirement decisions) into one structured
JSON report, a Markdown report for human review, and optional CSV summary
tables — **without** committing binary artifacts, datasets, or credentials,
and without depending on the internals of the tools that produced the inputs.

## Non-goals

- This tool does not fetch data from GitHub, run tests, run benchmarks, or
  invoke any other tool. It only reads JSON files named in its input
  manifest.
- This tool does not modify `tools/integration_reconciliation/**`,
  `scripts/verify_integration_reconciliation.py`, `configs/release/**`,
  `docs/release/**`, the Bayesian falsification implementation, signal
  adapters, streaming code, CI workflows, dashboard routes, or generated
  artifacts. It only *reads* JSON evidence files, in whatever format those
  systems choose to emit them, per the input contracts below.

## Input manifest

The compiler takes one manifest JSON file mapping input-contract names to
file paths (relative paths are resolved against the manifest's own
directory):

```json
{
  "reconciliation": "evidence/reconciliation.json",
  "capability_snapshot": "evidence/capability_snapshot.json",
  "dataset_provenance": "evidence/dataset_provenance.json",
  "falsification": "evidence/falsification.json",
  "performance_benchmark": "evidence/performance_benchmark.json",
  "memory_evidence": "evidence/memory_evidence.json",
  "interoperability": "evidence/interoperability.json",
  "topology_validation": "evidence/topology_validation.json",
  "test_runner": "evidence/test_runner.json",
  "merge_gate": "evidence/merge_gate.json",
  "pr_retirement": "evidence/pr_retirement.json"
}
```

Every key is optional. A key that is absent, or whose target file cannot be
read or parsed, produces a report section with `"available": false` and an
`"error"` string — it never aborts compilation of the rest of the report
(see "Partial reports" below).

### Input contract shapes

All numeric fields that are missing, non-numeric, or non-finite (NaN,
Infinity, -Infinity) are normalized to `null`. All enum-like fields
(`state`, `verdict`, `data_mode`, `ci_status`, ...) are normalized to
`"unknown"` unless they exactly match one of the listed literal values —
nothing is inferred from context.

**`reconciliation`** — `{"pull_requests": [...]}`, each item:

| field | type | notes |
|---|---|---|
| `pr_number` | int | required |
| `branch` | str \| null | head branch name |
| `base_branch` | str \| null | base branch/ref; if it equals another PR's `branch`, that PR becomes a stacking dependency |
| `state` | `"open"｜"merged"｜"draft"｜"closed"` | only these four literals are trusted; anything else -> `"unknown"`. **Never inferred from the branch existing.** |
| `mergeable` | bool \| null | |
| `ci_status` | `"passed"｜"failed"｜"pending"｜"not_started"｜"skipped"` | |
| `superseded_by_pr` | int \| null | |
| `depends_on` | list[int] | explicit PR-number dependencies, in addition to base-branch stacking |
| `changed_files` | list[str] | used for changed-file ownership / overlap detection |

**`capability_snapshot`** — `{"capabilities": [{"name", "status": "available"｜"unavailable"｜"degraded", "backend", "notes"}]}`

**`interoperability`** — `{"adapters": [{"name", "status": "supported"｜"unsupported"｜"partial", "contract_version", "notes"}]}`

**`dataset_provenance`** — `{"datasets": [{"dataset_id", "data_mode": "synthetic"｜"empirical", "source", "license", "checksum", "n_subjects", "notes"}]}`

**`falsification`** — `{"results": [{"hypothesis_id", "data_mode", "metric_type", "metric_value", "unit", "verdict": "PASS"｜"FAIL"｜"INCONCLUSIVE", "notes"}]}`. `metric_type` is rendered verbatim; only the literal value `"bayes_factor"` is ever displayed using the phrase "Bayes factor". Everything else (e.g. `"proxy_K"`) is displayed as `"<metric_type> (not a formal Bayes factor)"`.

**`performance_benchmark`** / **`memory_evidence`** — same shape: `{"benchmarks": [{"name", "metric", "value", "unit", "baseline_value", "regression_pct", "status": "pass"｜"fail"}]}`. These are two separate manifest keys carrying the same contract, kept separate because they answer different questions (throughput/latency vs. memory footprint) and must not be merged by inference.

**`topology_validation`** — `{"checks": [{"name", "data_mode", "Qabs", "I_mean", "verdict": "PASS"｜"FAIL", "notes"}]}`

**`test_runner`** — `{"jobs": [{"name", "status": "passed"｜"failed"｜"error"｜"not_started"｜"skipped", "passed", "failed", "skipped", "duration_s"}]}`. A job with status `"not_started"` (or missing/unrecognized status, normalized to `"unknown"`) is never counted as passing in any aggregate.

**`merge_gate`** — `{"decisions": [{"pr_number", "decision": "allow"｜"block"｜"hold", "reason"}]}`

**`pr_retirement`** — `{"decisions": [{"pr_number", "action": "retire"｜"keep"｜"superseded", "superseded_by", "reason"}]}`

## Output contract

`compile_report()` (in `tools/research_report/compiler.py`) returns one dict
with these top-level keys, matching the required report sections:

1. `repository_and_baseline`
2. `pull_requests` (open/merged/draft/blocked, i.e. `by_state`)
3. `dependency_and_stacking_graph`
4. `changed_file_ownership`
5. `ci_and_infrastructure_status`
6. `performance_evidence`
7. `memory_evidence`
8. `interoperability_status`
9. `dataset_provenance`
10. `topology_validation_status`
11. `falsification_status`
12. `synthetic_versus_empirical_distinction`
13. `scientific_limitations`
14. `unresolved_conflicts`
15. `recommended_merge_order`
16. `final_release_recommendation`

Plus metadata: `report_schema_version`, `compiler_version`, `generated_at`,
`status` (`"complete"` or `"partial"`), `completeness` (per-input-section
availability), `provenance` (manifest path + per-input sha256 checksums),
`capability_snapshot`, `merge_gate_decisions`, `pr_retirement_decisions`.

`scripts/compile_research_state.py` writes this dict as
`research_state_report.json` (`json.dumps(..., indent=2, sort_keys=True,
allow_nan=False)`), a matching `research_state_report.md`
(`tools/research_report/render_markdown.py`), and, when `csv` is requested,
a `csv/` directory of summary tables
(`tools/research_report/render_csv.py`) — never binary plots, datasets, or
credentials.

## Guardrails

These are enforced in code (`tools/research_report/guardrails.py`,
`tools/research_report/graph.py`), not just documented:

1. **Never infer merged status from a branch existing.** `state` is passed
   through only when it is literally one of `open/merged/draft/closed`;
   nothing else (including branch presence) can produce `"merged"`.
2. **Never infer passing tests from a job that did not start.** Aggregates
   count jobs by their literal `status`; `not_started`/`unknown` are
   reported separately and never folded into `passed`.
3. **Never call proxy K a formal Bayes factor.** Only `metric_type ==
   "bayes_factor"` renders as "Bayes factor"; every other metric type is
   labeled `"<type> (not a formal Bayes factor)"`.
4. **Never call synthetic data empirical.** `data_mode` is passed through
   only when it is literally `synthetic` or `empirical`; anything else is
   `"unknown"`. The synthetic-vs-empirical section groups strictly by this
   field.
5. **Preserve exact numeric fields with units and provenance.** Numeric
   values are carried through as-is (only NaN/Infinity -> `null`) alongside
   their declared `unit` and the source file's checksum in `provenance`.
6. **Use null for missing/non-finite values.** `guardrails.safe_number`
   converts non-numeric and non-finite values to `null`.
7. **Report schema version** — top-level `report_schema_version`.
8. **Compiler version** — top-level `compiler_version`.
9. **Source-file checksums** — `provenance.source_checksums`, sha256 per
   input file actually read.
10. **Deterministic except explicitly labeled timestamps** — the only
    non-deterministic field is `generated_at`; pass `--now` (or `now=` to
    `compile_report`) to make output fully byte-identical across runs. All
    lists are sorted by a stable key before being placed in the report, and
    JSON is serialized with `sort_keys=True`.
11. **No binary plots, datasets, or credentials are generated or written.**
12. **Partial reports are explicit.** `status` is `"partial"` whenever any
    input section is unavailable; `completeness` names which sections and
    why (`"not_provided"`, `"invalid_json"`, `"non_finite_value"`,
    `"file_not_found"`, ...).

## Determinism

`compile_report(manifest_path, now=..., repo=..., base_ref=...,
base_commit=...)` is a pure function of its arguments and the contents of
the files the manifest points to: no network calls, no `git` invocations, no
wall-clock reads unless `now` is omitted. Two compiles with the same
manifest, input files, and `now` value produce byte-identical JSON and
Markdown.

## CLI

```bash
python -m scripts.compile_research_state \
    --manifest governance/research_report/manifest.json \
    --output-dir artifacts/research_state_report \
    --formats json,markdown,csv \
    --now 2026-01-01T00:00:00+00:00 \
    --repo NeuroTopology-Sim --base-ref main --base-commit <sha>
```

## Versioning

- `REPORT_SCHEMA_VERSION` (`tools/research_report/versions.py`): bump on any
  change to the output JSON/Markdown/CSV shape.
- `COMPILER_VERSION`: bump on any behavior change, including bug fixes,
  even when the output shape is unchanged.
