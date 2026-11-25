# Performance Release Evidence Gate

Release-readiness evaluator for **already-normalized** benchmark records
(PR #258 schema `1.0` or compatible dicts). Produces finite JSON + Markdown with
explicit decisions. Does **not** run benchmarks and does **not** modify the
evidence normalizer, performance policy, streaming code, or process runner.

| Artifact | Path |
| --- | --- |
| Gate | `tools/performance/release_evidence_gate.py` |
| CLI | `scripts/evaluate_performance_release_evidence.py` |
| Tests | `tests/performance/test_release_evidence_gate.py` |

> **Scientific-integrity note.** Outputs are always `evidence_class:
> performance_only` and `synthetic: true`. This is performance evidence — never
> scientific evidence. No Bayesian factors, topology metrics, or biological
> conclusions are computed.

## Decision states

| Decision | Meaning |
| --- | --- |
| `EVIDENCE_READY` | Same-shape/backend, checksums match, quality OK, no authoritative regression |
| `EVIDENCE_INCONCLUSIVE` | Commensurable but weak quality (reps/spread) or missing checksum |
| `CORRECTNESS_FAILURE` | Checksum mismatch |
| `TIMEOUT_FAILURE` | Timeout on either side — **never** ready/pass |
| `INFRASTRUCTURE_BLOCKED` | Child crash or optional dependency missing |
| `NOT_COMPARABLE` | Shape/backend/schema mismatch |
| `MISSING_METRIC` | Authoritative memory metrics null (never fabricated as 0) |
| `REGRESSION_DETECTED` | Authoritative metric exceeded threshold |

## Authoritative vs advisory metrics

**Authoritative**

- Checksum match (correctness gate)
- Tracemalloc peak ratio (Python-domain allocation; not process RSS)
- Child RSS ratio — **same host only**
- Runtime ratio — **same host only**

**Advisory**

- Cross-host runtime / child RSS
- Parent-sampled RSS (best-effort; includes interpreter/import noise)
- Explicit note: tracemalloc ≠ process RSS

## Rules

1. Missing RSS / tracemalloc → `null`, never zero.
2. Timeout is never PASS / never `EVIDENCE_READY`.
3. Cross-host runtime is not authoritative.
4. Synthetic performance is not scientific evidence.
5. Tracemalloc is not process RSS.
6. Unavailable optional dependencies are not successful execution.
7. JSON is finite (`allow_nan=False`) and key-sorted.

## CLI

```bash
python scripts/evaluate_performance_release_evidence.py \
  --input normalized_pair.json \
  --output-json release_evidence.json \
  --output-md release_evidence.md
```

Input: `{"baseline": {...}, "candidate": {...}}` or `{"results": [baseline, candidate]}`.

Exit codes: `0` ready · `1` failure/regression/timeout/infra/correctness · `5` inconclusive/not comparable/missing metric · `2` bad input.

## Known measurement limitations

- Child / parent RSS include interpreter and imported-library memory — not the
  chunk working set; compare like-for-like on one host.
- Parent-sampled RSS is approximate (poll interval / psutil availability).
- Wall-clock and RSS are hardware/allocator/BLAS dependent.
- This gate consumes normalized records; it does not replace PR #230 policy or
  PR #258 normalization.
