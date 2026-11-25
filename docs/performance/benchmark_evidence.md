# Benchmark Evidence Normalization

Pure adapter that turns heterogeneous benchmark **reports** into comparable
evidence records and optional pair-wise decisions. It does **not** run
benchmarks and does **not** duplicate process runners, matrix orchestration,
checkpoint/replay, or the performance-policy evaluator.

| Artifact | Path |
| --- | --- |
| Normalizer | `tools/performance/evidence_normalizer.py` |
| CLI | `scripts/normalize_benchmark_evidence.py` |
| Tests | `tests/performance/test_evidence_normalizer.py` |

Integrates with (by consuming their JSON, not importing their modules):

- PR #241 process-isolated runner (`ChildResult` / matrix report)
- PR #244 benchmark orchestration (`CaseResult` / campaign report)
- PR #230 performance-policy (complementary: policy compares telemetry-shaped
  records; this layer normalizes + classifies operational outcomes first)
- PR #232 checkpoints/replay (checksum fields may appear in reports)

> **Scientific-integrity note.** Normalized records are always labeled
> `evidence_class: performance_only` and `synthetic: true` unless a caller
> explicitly marked `synthetic: false` on input — and even then this layer
> never promotes results to scientific claims. A benchmark cannot support
> scientific claims.

## Normalization schema (`1.0`)

Each record includes:

| Field | Notes |
| --- | --- |
| `benchmark_id` | from `benchmark_id` / `case_id` / `id` / `label` |
| `source_commit` | retained; required for comparison |
| `branch` | optional |
| `host` / `platform` | for same-host vs advisory runtime |
| `python_version` | optional |
| `backend` | optional |
| `input_shape` | channels/samples/dtype |
| `chunk_size` / `repetitions` | optional |
| `checksum` | float or hex string |
| `correctness_status` | `ok` / `fail` / `unknown` |
| `runtime_s` | from elapsed/wall fields |
| `tracemalloc_peak_bytes` | **null if missing, never 0** |
| `child_rss_bytes` | **null if missing, never 0** |
| `parent_sampled_rss_bytes` | **null if missing, never 0** |
| `timeout_status` | bool; timeout never becomes pass |
| `process_exit_status` | exit code or null |
| `optional_dependency_state` | e.g. `missing` |
| `evidence_class` | always `performance_only` here |
| `synthetic` | performance scaffolding flag |

## Decision states

`comparable` · `not_comparable` · `correctness_failure` · `timeout` ·
`child_crash` · `missing_metric` · `infrastructure_blocked` · `pass` ·
`regression` · `inconclusive`

Precedence for pair comparison: timeout → child_crash → infrastructure_blocked
→ not_comparable (missing commit / shape) → correctness_failure → missing_metric
→ inconclusive → regression → pass.

Rules of note:

1. Missing RSS / tracemalloc → `null`, never fabricated zero.
2. Cross-host runtime is **advisory** (does not alone force regression).
3. Checksums must match before performance is accepted.
4. Timeout is never pass.
5. Source commits retained; missing commit → `not_comparable`.
6. Input shapes/dtypes must match.
7. JSON is finite (`allow_nan=False`) and key-sorted.

## CLI

```bash
python scripts/normalize_benchmark_evidence.py \
  --input benchmark_reports.json \
  --output normalized_evidence.json

python scripts/normalize_benchmark_evidence.py \
  --input pair.json --output decision.json --compare
```

`pair.json` may be `{"baseline": {...}, "candidate": {...}}` or a `results` list
(first two entries compared).

## Known limitations

- Field aliases cover the common runner/orchestration/telemetry shapes but are
  not a universal schema registry; unknown layouts may yield `unknown`
  correctness or null metrics.
- This layer does not invoke PR #230's `compare_records`; callers may feed
  normalized dicts into the policy evaluator afterward for budget ratios.
- Wall-clock and RSS remain hardware/allocator dependent.
- Synthetic / performance-only labeling is intentional and non-negotiable for
  scientific claim boundaries.
