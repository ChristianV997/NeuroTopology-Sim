# Higher-Order Runtime Optimization (Bounded, Semantics-Preserving)

An **additive** benchmark layer that measures bounded-memory, reproducible
execution of the higher-order signal pipeline and proves it is **numerically
equivalent** to full materialization. It changes **no** scientific semantics.

- Package: `tools/higher_order_runtime/`
- CLI: `scripts/benchmark_higher_order_runtime.py`
- Tests: `tests/higher_order_runtime/`

> **Read-only interfaces.** The higher-order feature implementations
> (`topo_monitor/higher_order/triadic.py`, `.../spectra.py`,
> `analysis/transition_forecasting/**`) come from other agents' PRs (#279, #282,
> #281) and are treated as read-only. This layer does **not** import or edit them;
> it declares structural `Protocol` types and ships deterministic local fixtures,
> so any conforming callable (including the real implementation, once merged) can
> be benchmarked by substitution.
>
> **Scientific-integrity note.** Fixtures are synthetic; `evidence_class` is
> `performance_only`. Runtime optimization cannot alter scientific semantics or
> create biological evidence.

## Components

| Concern | Where |
| --- | --- |
| Protocols + fixtures (triad stat, spectral segment, surrogate stat) | `protocols.py` |
| Memory planner (working-set estimate, safety margin, chunk selection) | `planner.py` |
| Telemetry (tracemalloc peak, child RSS, timeout, JSON safety) | `telemetry.py` |
| Bounded wrappers (windows, rolling covariance, triad/spectral iteration, one-at-a-time surrogates, incremental summaries) | `bounded.py` |
| Benchmark (full/bounded/adaptive/replay/checkpoint + equivalence) | `benchmark.py` |

## Bounded wrappers

- **Chunked signal windows** — zero-copy views along the sample axis.
- **Rolling covariance** — Chan-Golub-LeVeque parallel combine; equals
  `np.cov(X, rowvar=False, ddof=1)` within ~1e-8.
- **Triad candidate iteration** — deterministic `(i<j<k)` combinations bounded by
  a `candidate_limit`.
- **Spectral segment iteration** — tumbling complete segments through a segment fn.
- **One-at-a-time surrogates** — seeded per-surrogate statistics without
  materializing a surrogate batch.
- **Incremental summaries** — streaming mean/variance/min/max + stable checksum.

## Memory model

The planner estimates the transient working set (beyond the resident input
signal):

```
working_set = n_channels * itemsize * chunk_size * op_multiplier
              + n_channels^2 * itemsize            # covariance M2 accumulator
              + 3 * n_samples * itemsize           # one-at-a-time surrogate columns
```

It picks the largest chunk within `[min_chunk, min(max_chunk, n_samples)]` whose
estimate fits `target_budget_bytes`, and reports `safety_margin_bytes`,
`safety_margin_ratio`, a `reason` (`budget_limited` / `at_max_chunk` /
`limited_by_samples` / `infeasible_budget_below_min`), and `feasible`. Configurable
inputs: chunk bounds, `op_multiplier`, `candidate_limit`, `surrogate_limit`,
timeout. This bounds an **estimate** of Python array working set — not process RSS.

## Benchmark modes

- **full_materialization** — reference (`np.cov`, whole-array summaries, stacked
  segments).
- **bounded_streaming** — chunked covariance/summaries with reused accumulators.
- **adaptive_chunks** — chunk size chosen by the planner from a memory budget.
- **deterministic_replay** — the bounded path run twice; results are bit-identical.
- **checkpoint_resume** — streaming state is serialized to an atomic `.npz` midway
  and reloaded to finish; result matches the non-checkpointed run.

Each mode records a `tracemalloc` peak; the report includes
`tracemalloc_peak_ratio_bounded_over_full` (≈0.33–0.40 in local runs) and, in
`--isolated` mode, the child process's sampled RSS (`null` without psutil).

## Numerical equivalence

`verify_equivalence` compares, within a configurable tolerance (default `1e-9`):
covariance checksum, per-channel mean/variance/min/max sums, streaming checksum,
triad checksum, spectral sum, surrogate mean and checksum (float metrics), and
triad/spectral/sample **counts** (exact). Chunk-size invariance holds within
tolerance across chunk sizes; min/max and all counts are exact.

## Usage

```bash
python scripts/benchmark_higher_order_runtime.py --json
python scripts/benchmark_higher_order_runtime.py --isolated --timeout-s 120 --json
python scripts/benchmark_higher_order_runtime.py --samples 40000 --channels 16 --chunk-size 4096
```

Exit code is `0` when all modes are numerically equivalent, else `1`. Output is
finite JSON (NaN/Inf → `null`). No `shell=True`; no network; temp dirs are cleaned.

## Limitations

- Numbers reproduce the full path within floating tolerance (summation grouping
  differs across chunk sizes); pin `chunk_size` for bit-identical replay.
- `tracemalloc` peak is Python-allocation only; process RSS additionally includes
  interpreter and imported-library memory and is host/allocator dependent.
- Child RSS requires `psutil`; it is `null` when unavailable (never fabricated).
- The bundled fixtures are synthetic stand-ins for the real higher-order features;
  substitute the merged implementations (same protocols) to benchmark them.
- Performance evidence only — never scientific or biological evidence.
