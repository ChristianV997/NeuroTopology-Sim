# Performance Benchmarking — Streaming & PITNN Kernels

This document describes how to benchmark and reason about the bounded streaming
utilities (`tools/streaming/bounded.py`), the PITNN NumPy kernel fallback
(`sim/pitnn/kernels_fast.py`), and the end-to-end comparison harness
(`scripts/benchmark_streaming_pipeline.py`).

> **Scientific-integrity note.** Everything here is *performance* evidence only.
> The fixtures are synthetic and deterministic; they are **not** empirical or
> scientific evidence, and none of these paths change topology or Bayes-factor
> semantics. Accelerated paths are always optional with a NumPy fallback, and no
> data is dropped or silently down-cast to gain speed.

## Components under test

| Component | What it provides |
| --- | --- |
| `tools.streaming.bounded.bounded_stream` | Fixed-size chunked processing with reusable work buffers, optional callback summaries, optional history suppression, deterministic aggregation, finite checks, and peak-memory telemetry. |
| `tools.streaming.bounded.MemoryTelemetry` | `tracemalloc`-based transient peak-memory context manager (nestable). |
| `sim.pitnn.kernels_fast.heun_step` (NumPy fallback) | Allocation-reduced Heun step using preallocated cross-product buffers; bit-identical to the previous NumPy implementation. |
| `scripts/benchmark_streaming_pipeline.py` | Baseline-vs-optimized pipeline comparison with runtime/memory telemetry and exact checksums. |

## Benchmark protocol

1. Build a deterministic fixture with a fixed `--seed` (default `0`). The fixture
   is a sinusoid-plus-noise `(samples, channels)` float64 array.
2. Run each pipeline once as warm-up (fills caches, triggers any lazy imports).
3. Time `--repeats` iterations with `time.perf_counter`; report **best** and
   **mean** wall time (best is the most stable single-run estimate; mean shows
   variance).
4. Measure transient **peak** allocation with `tracemalloc` around one dedicated
   call (kept separate from timing so tracing overhead does not skew wall time).
5. Compute exact output **checksums** (sample-sum, moments, per-window energies)
   for both pipelines and compare within a relative `--tolerance` (default
   `1e-9`).

Run:

```bash
python scripts/benchmark_streaming_pipeline.py \
    --channels 32 --samples 200000 --chunk-size 16384 --window 1024 --repeats 5
# machine-readable:
python scripts/benchmark_streaming_pipeline.py --json --channels 32 --samples 200000 \
    --chunk-size 16384 --window 1024 --repeats 5
```

The `--chunk-size` is rounded **up** to a whole multiple of `--window` so that
each transformed chunk contains only complete windows and per-window energies
can be accumulated in a single streaming pass (see `effective_chunk_size`).

## Representative results

Measured on the development VM below (results are hardware-specific; reproduce
locally before quoting). Both pipelines compute identical outputs (per-channel
mean/variance/min/max, sample checksum, and summed per-window energies).

| Config (`samples`×`channels`, chunk/window) | Baseline peak | Optimized peak | Peak ratio | Best time (base → opt) |
| --- | --- | --- | --- | --- |
| 200000×32, 16384/1024 | 102.5 MB | 8.5 MB | 0.083 (~12×) | 51.1 ms → 48.0 ms (1.07×) |
| 500000×64, 8192/1024 | 256.6 MB | 8.5 MB | 0.033 (~30×) | 120.4 ms → 192.1 ms (0.63×) |
| 200000×32, 4096/1024 | 51.5 MB | 2.2 MB | 0.042 (~24×) | 21.3 ms → 44.1 ms (0.48×) |

Interpretation:

- The **primary, robust win is peak memory**: the optimized pipeline never
  materializes the full transformed signal or the full per-window history, so
  its transient peak is bounded by the chunk (≈ `chunk_size × channels × 8 B`)
  regardless of `samples`. Reductions of ~12×–30× are typical.
- **Runtime is a trade-off that depends on chunk size.** Larger chunks amortize
  Python-level per-chunk overhead and reach parity-or-better (e.g. 1.07× at a
  16384 chunk). Very small chunks pay more per-chunk overhead and can be slower;
  choose the largest chunk that fits the memory budget.
- No speedup is claimed beyond what the harness measures on your hardware; the
  script prints the exact `speedup_best` and `peak_memory_ratio` it observed.

## Environment

Record the environment alongside any quoted numbers. The development
measurements above used:

- CPU: cloud x86_64 Linux VM (`uname -m` = `x86_64`).
- Python 3.12, NumPy 2.x.
- Thread pools unpinned for the benchmark script; the isolated test runner pins
  `OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1` for reproducibility.
- Numba was importable (`0.67.0`); it is **not** required — see fallback paths.

## Peak vs transient memory

- **Transient peak** (what `tracemalloc` reports here) is the high-water mark of
  Python-tracked allocations *during* the measured block. It captures temporary
  arrays created and freed within the call — exactly what bounded streaming
  reduces.
- It is **not** process RSS. The interpreter, imported native libraries (BLAS,
  MNE, Torch), and memory allocated by C extensions outside Python's allocator
  are not included. Use it for relative before/after comparisons of Python-level
  allocation behavior, not as an absolute memory footprint.

## Precision guarantees

- All accumulation is float64. No sample is dropped and no value is silently
  down-cast.
- **Fixed chunk size → bit-reproducible** aggregates and checksum across runs.
- **Different chunk sizes → agreement within tolerance.** Changing `chunk_size`
  changes floating-point summation grouping, so mean/variance/checksum can differ
  at the ~1e-12 (mean) / ~1e-9 (variance) / ~1e-13 relative (checksum) level.
  Min and max are exact regardless of chunk size.
- Streaming mean/variance use the numerically stable Chan–Golub–LeVeque parallel
  combine, applied strictly in chunk order.
- The PITNN NumPy `heun_step` refactor is **bit-identical** to the previous
  implementation (verified over multi-step trajectories: max abs diff `0.0`).

## Fallback paths

- `tools/streaming/bounded.py` has **no** accelerated backend — it is pure NumPy
  + stdlib. There is nothing optional to install and nothing to fall back from.
- `sim/pitnn/kernels_fast.py` keeps its existing optional Numba kernel
  (`_heun_step_numba`) *and* a complete NumPy fallback. Numba is detected at
  import (`NUMBA_AVAILABLE`); if it is absent, `resolve_backend("auto")` returns
  `"numpy"` and `heun_step` runs the NumPy path. No CUDA/JAX/CuPy/Torch is
  required. The performance tests force `NUMBA_AVAILABLE = False` to exercise the
  fallback directly.
- `fastmath` is used only inside the pre-existing optional Numba kernel, which is
  an opt-in accelerated path; the guaranteed NumPy fallback does not use it.

## Limitations

- Wall-clock numbers are hardware-, BLAS-, and load-dependent; always re-measure.
- The benchmark workload (`2x+1` transform, per-window variance) is a stand-in
  for streaming signal/topology cost, not a scientific computation.
- `tracemalloc` adds overhead and only sees Python-level allocations; memory
  measurement and timing are done in separate passes for this reason.
- Bounded streaming trades a possible small runtime overhead at small chunk sizes
  for large memory savings; it is most valuable when inputs are large relative to
  available memory.
- Cross-chunk-size numerical differences, while tiny, are real; pin `chunk_size`
  when bit-exact reproducibility across configurations is required.

## Interpreting speedups

- Treat `speedup_best < 1` as "the memory-bounded path costs some time"; the
  compensating benefit is in `peak_memory_ratio`.
- Prefer reporting **both** `speedup_best` and `peak_memory_ratio` together — the
  point of these utilities is bounded memory at competitive throughput, not raw
  speed.
- Only quote a speedup that the harness actually measured on the same hardware
  and config you are describing.
