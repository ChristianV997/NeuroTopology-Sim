# Higher-Order Runtime Streaming Contract

Owner (this PR):
- `tools/higher_order_runtime/stream_contract.py` (minimal production surface)
- `tests/higher_order_runtime_contract/`
- `docs/higher_order_runtime_contract.md`

Existing runtime package (read + thin extension only):
- `tools/higher_order_runtime/{bounded,planner,protocols,benchmark,telemetry}.py`
- Prior tests in `tests/higher_order_runtime/` (not duplicated here)

## Scope

Engineering correctness for **chunked / streaming** execution of the bounded
higher-order runtime: chunk boundaries, state carry vs reset, temporal
alignment, and fail-closed bounded input. Synthetic local arrays only.

This is **not**:
- a performance-claims task
- a new online-analysis engine
- scientific validation or evidence promotion
- BIDS / OpenNeuro / empirical dataset work

A contract failure must never be interpreted as a successful scientific result.

## Collision audit (Batch 2)

Open PRs `#369`–`#376` were inspected at planning time against `origin/main`
(`3f3fe8593303184cb88eef056c1322f3d4e57a16`). None of those tips modified
`tools/higher_order_runtime/**`. Adjacent Batch 2 work (security harness,
pipeline benchmarks, BIDS adapter, missingness/cohorts, evidence gates) owns
other paths and was left untouched.

## Contracts

| Topic | Behavior |
| --- | --- |
| Chunk/stride configuration | `chunk_size`, explicit `stride`, `max_chunk_samples`, `max_channels`, and session `n_channels` require positive Python/NumPy integers. Booleans and floats are rejected at configuration time with `StreamContractError`, rather than failing later during slicing. `allow_uneven_final` requires a Python/NumPy boolean and is normalized to `bool`. Supported window sizes include `1`, short, uneven final, and exact divisors. `chunk_size > max_chunk_samples` raises `ChunkBoundError` (no silent clamp). |
| Ordering | Windows are emitted in increasing sample index order. |
| Timestamps | Optional. When present: a rectangular, real numeric vector that is finite both before and after float64 normalization, length-matched, and strictly increasing after normalization. Ragged input, cast overflow, and distinct values that collapse to the same float64 timestamp are rejected with `TimelineContractError`. Gaps are allowed; no fixed cadence is inferred. Never fabricated, resampled, or interpolated. |
| Warm-up / overlap | Default tumbling (`stride = chunk_size`). Overlap mode uses explicit `stride < chunk_size`; warm-up = `chunk_size - stride`. |
| End-of-stream | Non-overlap: uneven final allowed iff `allow_uneven_final`. Overlap: partial final window is **not** padded; samples past the last full window are dropped when `allow_uneven_final`, otherwise `ChunkBoundError` is raised. Spectral segments already drop incomplete tails (no implicit zero-pad). |
| State reset | Session bounds must be a `StreamBounds` instance, and `run_id` must be a non-empty string. `StreamSession.reset(run_id)` validates before clearing accumulators. Updating with a malformed or different `run_id` without reset fails closed and does not advance session state. |
| Shape drift | Channel-count changes mid-stream raise `ShapeContractError`. Chunks must be 2-D `(samples, channels)`; a 1-D vector is rejected, never reshaped. Column *identity* / permutation is caller-owned (not fingerprint-checked). |
| Input dtype | Complex-valued signals, chunks and timestamps raise `StreamContractError` / `TimelineContractError`; they are never cast to real with the imaginary part discarded. Text, bytes, `datetime64`/`timedelta64`, and object arrays containing such values are rejected as non-numeric rather than cast to float. |
| Accumulator overflow | `StreamSession.update` applies a chunk to copies of the covariance and summary accumulators and commits only if every running value stays finite. A finite chunk whose magnitudes overflow float64 raises `StreamContractError` and leaves counts, accumulators, and `last_timestamp` unchanged. |
| Configuration types | `iter_contract_windows` requires a `ChunkingPolicy` and a `StreamBounds` and validates configuration, signal, and timestamps when called (not on the first `next()`). `deterministic_accumulator_bytes` requires positive integers for both arguments (bools and floats rejected). |
| Tumbling alias | `ChunkingPolicy(chunk_size)` (`stride is None`) ≡ `stride == chunk_size`. |
| Batch ↔ stream parity | Rolling covariance matches `np.cov(..., ddof=1)` within declared `atol`/`rtol` across chunk sizes (engineering parity only). Batch parity requires a finite 2-D real-valued signal with at least two samples and one channel, non-empty positive-integer chunk sizes, and finite non-negative scalar tolerances. The batch reference and streaming result must be finite float64 matrices with identical `C×C` shapes; NumPy's one-channel scalar reference is normalized to `1×1`. Non-finite covariance results or an unrepresentable absolute difference raise `StreamContractError`; NaNs are never considered equal. |
| Memory | `deterministic_accumulator_bytes(C)` is an O(C²) accumulator-size check, not an RSS/speed claim. |

## Declared tolerances

- Covariance batch/stream parity: `atol=1e-8`, `rtol=0.0` (matches existing runtime tests).
- Full vs bounded feature checksums (existing harness): `tolerance=1e-9`.

## Stateful non-equivalence (by design)

- **Overlap windows vs batch-on-full-signal statistics that assume independence of windows** are not claimed equivalent. Overlap is an explicit streaming view for warm-up continuity tests only; covariance parity tests use non-overlapping tumbling windows.
- **Incomplete spectral tails** are dropped (same as `iter_spectral_segments`); padding would change FFT power and is rejected.

## Rejected failure modes

- Silent truncation / clamping of oversize chunks
- Fabricated timestamps
- Hidden resampling
- Cross-run accumulator leakage
- Implicit padding that changes results
- Non-finite samples/results or shape/dtype mismatches treated as covariance parity
- Overflowed or otherwise unrepresentable covariance differences
- Treating contract errors as scientific PASS

## Run

```bash
PYTHONPATH=. python -m pytest tests/higher_order_runtime_contract -q
PYTHONPATH=. python -m pytest tests/higher_order_runtime -q   # existing suite
python -m compileall -q tools/higher_order_runtime tests/higher_order_runtime_contract
git diff --check
```
