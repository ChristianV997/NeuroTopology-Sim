# Performance-Regression Budget Policy

An **additive** policy layer that turns benchmark JSON records into a reviewable
verdict, with configurable tolerances. It compares a *candidate* run against a
*baseline* (or a single run against absolute budgets) and reports runtime, RSS,
and `tracemalloc` ratios, checksum equivalence, and a validity/confidence
assessment.

- Evaluator: `tools/streaming/performance_policy.py`
- CLI: `scripts/evaluate_performance_budget.py`
- Tests: `tests/performance/test_performance_policy.py`

The evaluator **runs no benchmarks** and imports no streaming/kernel code — it
only consumes records (e.g. the JSON produced by the process-memory telemetry in
PR #215). It is fully deterministic and emits finite JSON.

> **Scientific-integrity note.** Every report is labeled `evidence_class:
> performance_only` and echoes each record's `synthetic` flag. Synthetic
> benchmarks are performance evidence only — never scientific evidence.

## Input record schema (consumed)

Flat JSON objects with these fields (all optional unless noted; missing ⇒
treated as unknown/`null`, never `0`):

| Field | Type | Used for |
| --- | --- | --- |
| `backend` | str | backend match (`numpy`/`numba`/…) |
| `input_dims` | object | shape commensurability (**must match**) |
| `chunk_size` | int/null | reported context |
| `repetitions` | int | measurement confidence |
| `wall_best_s`, `wall_mean_s` | float | runtime ratio + noise/spread |
| `tracemalloc_peak_bytes` | int | tracemalloc ratio (authoritative) |
| `peak_rss_bytes` | int/null | peak-RSS ratio (advisory cross-machine) |
| `checksum` | float | numerical equivalence (**gates performance**) |
| `hardware` | object | hardware comparability (falls back to `providers.platform`) |
| `synthetic` | bool | evidence labeling |

## Output schema (`PolicyReport.to_dict()`)

```json
{
  "verdict": "pass|regression|correctness_failure|invalid_comparison|inconclusive",
  "valid_comparison": true,
  "invalid_reasons": [],
  "correctness_ok": true,
  "checksum_rel_err": 0.0,
  "runtime_ratio": 0.94, "runtime_regression": false,
  "peak_rss_ratio": null, "peak_rss_regression": null,
  "tracemalloc_ratio": 0.164, "tracemalloc_regression": false,
  "backend": {"baseline": "numpy", "candidate": "numpy", "match": true},
  "hardware": {"baseline": {...}, "candidate": {...}, "match": true, "known": true},
  "input_shape": {"baseline": {...}, "candidate": {...}, "match": true},
  "chunk_size": {"baseline": null, "candidate": 16384},
  "repetitions": {"baseline": 5, "candidate": 5},
  "confidence": "high|medium|low",
  "measurement_quality": {"...": "..."},
  "evidence_class": "performance_only",
  "synthetic": true,
  "thresholds": {"...": "..."},
  "recommendations": ["..."]
}
```

All numeric fields are finite or `null` (no `NaN`/`Infinity`).

## Verdicts (precedence)

1. `invalid_comparison` — not commensurable (shape mismatch; or backend/hardware
   mismatch when required). No performance conclusion is drawn.
2. `correctness_failure` — checksums present but disagree beyond
   `checksum_rel_tol`. Performance is **not** accepted.
3. `inconclusive` — a checksum is missing, so numerical equivalence cannot be
   established (required before accepting any performance result).
4. `regression` — an **authoritative** metric regressed beyond tolerance.
5. `pass` — valid, numerically equivalent, no authoritative regression.

**Authoritative vs advisory.** `tracemalloc` (Python-allocation) ratio is always
authoritative. Runtime and peak-RSS ratios are authoritative **only when the two
records share hardware**; otherwise they are computed and reported but are
advisory and never, by themselves, cause a `regression` verdict. This encodes
the rule that a comparison must never fail *solely* because absolute wall time
differs across machines.

## Rules encoded

1. Incompatible `input_dims` ⇒ `invalid_comparison` (never compared as equal).
2. Missing RSS/tracemalloc ⇒ ratio `null` (never treated as `0`).
3. Cross-machine runtime/RSS differences never *solely* fail a comparison.
4. Numerical equivalence (checksum) is required before a performance result is
   accepted (`inconclusive` when unknown).
5. Correctness failure and performance regression are distinct verdicts.
6. Every report is `performance_only` and carries the `synthetic` flag.
7. All thresholds are configurable (`PolicyThresholds` / CLI flags).
8. Output JSON is always finite (`json_safe`).
9. NumPy and optional Numba records are supported; differing backends are a
   mismatch unless `require_same_backend=False`.
10. Reports always include the process-isolation recommendation for RSS.

## Configurable tolerances (`PolicyThresholds`)

| Field | Default | Meaning |
| --- | --- | --- |
| `checksum_rel_tol` | `1e-9` | max relative checksum difference for equivalence |
| `max_runtime_regression_ratio` | `1.25` | candidate/baseline best wall time |
| `max_peak_rss_regression_ratio` | `1.25` | candidate/baseline peak RSS |
| `max_tracemalloc_regression_ratio` | `1.10` | candidate/baseline tracemalloc peak |
| `min_repetitions` | `3` | below ⇒ low confidence |
| `max_runtime_rel_spread` | `0.50` | `(mean-best)/best` above ⇒ noisy ⇒ low confidence |
| `require_same_backend` | `True` | backend mismatch ⇒ invalid |
| `require_same_hardware` | `False` | if `True`, hardware mismatch ⇒ invalid |

## CLI

```bash
# Compare baseline vs candidate (exit: 0 pass, 2 regression, 3 correctness, 4 invalid, 5 inconclusive)
python scripts/evaluate_performance_budget.py compare \
    --baseline baseline.json --candidate candidate.json \
    --max-tracemalloc-ratio 1.10 --max-runtime-ratio 1.25

# Single record vs absolute budgets (exit: 0 within, 2 over, 5 unknown)
python scripts/evaluate_performance_budget.py budget \
    --record candidate.json --peak-rss-budget-mb 300 --tracemalloc-budget-mb 16
```

Use `--baseline-pointer a.b.0` to select a nested record inside a larger report
JSON. `--allow-backend-mismatch` and `--require-same-hardware` adjust validity.

## Known measurement limitations

- **`tracemalloc` ≠ process RSS.** `tracemalloc` tracks Python-domain
  allocations; it is the most comparable cross-machine signal but does not
  include interpreter/native-library memory. RSS is hardware- and
  allocator-dependent and is process-lifetime for *peak* RSS.
- **Missing RSS is unknown, not zero.** Absent metrics never count as a pass.
- **Runtime is machine-dependent.** Cross-hardware runtime/RSS ratios are
  advisory; run baseline and candidate on the **same** machine for authoritative
  runtime/RSS verdicts.
- **Process isolation for RSS.** Measure each configuration in a fresh process so
  peak RSS is attributable; every report includes this recommendation.
- **Confidence is heuristic.** It derives from repetition count, timing spread,
  and hardware comparability — not a statistical significance test. Increase
  repetitions and pin threads for stable estimates.
- **Synthetic only.** Verdicts describe performance/memory behavior of synthetic
  fixtures and must not be cited as scientific evidence.
```
