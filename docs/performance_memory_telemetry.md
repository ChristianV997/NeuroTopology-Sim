# Process-Memory Telemetry (RSS) for Performance Benchmarking

PR #211 measured streaming performance with `tracemalloc`, which tracks only
**Python-level** allocations. That is the right tool for showing that the bounded
streaming path allocates fewer/smaller temporary arrays, but it is **not** a
measure of total process memory. This contribution adds process-level Resident
Set Size (RSS) telemetry so memory claims can be cross-checked against what the
operating system actually attributes to the process.

- Utility: `tools/streaming/memory_telemetry.py`
- Benchmark runner: `scripts/benchmark_process_memory.py`
- Tests: `tests/performance/test_process_memory.py`

> **Scientific-integrity note.** All fixtures here are synthetic and
> deterministic and are **performance** evidence only — never scientific
> evidence. No topology or Bayes-factor semantics are computed, and the optimized
> kernels are *not* modified (the kernel source is imported read-only; only the
> module-level `NUMBA_AVAILABLE` flag is toggled at run time to select a path).

## tracemalloc vs RSS

| Aspect | `tracemalloc` peak | Process RSS / peak RSS |
| --- | --- | --- |
| What it counts | Bytes allocated **through the CPython allocator** during a traced block | Physical memory pages the OS maps to the process |
| Scope | Python objects (incl. NumPy array payloads via the raw-domain hook) | Everything: interpreter, imported native libs (BLAS/MNE/Torch), C-extension buffers, fragmentation |
| Resettable | Yes (`reset_peak()`) — per-block | Current RSS fluctuates; **peak RSS is process-lifetime** and cannot be reset on Linux |
| Overhead | Non-trivial while tracing | Cheap sample |
| Best for | Relative before/after of Python allocation behavior | Absolute footprint and cross-checking that allocation savings actually reduce process memory |

Both are reported side by side. `tracemalloc` is the **reliable in-process
signal** for "did bounded streaming allocate less"; RSS is the **reality check**
for total footprint, but is noisier (see below).

## Allocator effects

- Freeing a NumPy array does not necessarily return pages to the OS. CPython's
  `pymalloc` and the system allocator (glibc `malloc`, tcmalloc, jemalloc) keep
  freed memory in arenas/free lists for reuse. Consequently **current RSS often
  does not drop** after a workload frees its arrays, and an RSS *delta* around a
  short workload can read as ~0 even though large temporaries were created and
  freed. This is expected, not a measurement bug.
- Large allocations may go through `mmap` and *can* be returned on free, so RSS
  behavior depends on allocation size and allocator thresholds.
- Because of this, the benchmark and tests **do not gate on RSS deltas**. They
  report RSS for transparency and assert only the reliable `tracemalloc`
  relationship (bounded peak < full-materialization peak).

## Peak RSS semantics and portability

`get_peak_rss_bytes()` uses, in order:

1. POSIX `resource.getrusage(RUSAGE_SELF).ru_maxrss` — **process-lifetime** peak.
   Units are normalized: **Linux reports KiB** (converted to bytes here), **macOS
   reports bytes**.
2. `psutil` `memory_info().peak_wset` on Windows.
3. Otherwise `None` — never fabricated.

`get_rss_bytes()` (current RSS) uses `psutil` when available, else Linux
`/proc/self/statm`, else `None`.

Because `ru_maxrss` is a lifetime high-water mark, peak RSS reported for a late
workload includes memory from everything the process did earlier. Interpret it as
"largest RSS the process ever reached", not "peak of this block".

## Process isolation

To attribute peak RSS to a specific workload rather than to the whole process
history, run each configuration in a **fresh interpreter**. The repository's
isolated runner already does this per test file:

```bash
python scripts/run_tests_isolated.py --batch-size 8 --timeout-s 120 \
    tests/performance/test_process_memory.py
```

For per-configuration RSS attribution, invoke the benchmark once per config in a
new process (e.g. a shell loop calling `benchmark_process_memory.py --json` with
a single `--samples-list`/`--chunk-sizes` value) and record each JSON separately.
Within a single process, prefer the `tracemalloc` peak for per-block comparisons.

## Benchmark reproducibility

- Fixtures are seeded (`--seed`, default `0`) and fully deterministic.
- Each measured workload returns a deterministic scalar **checksum**; bounded vs
  full-materialization checksums are compared within `--tolerance` (default
  `1e-9`). Fixed-shape runs reproduce the checksum bit-for-bit; different chunk
  sizes agree within floating-point tolerance (summation grouping differs — no
  data dropped).
- JSON output is guaranteed free of `NaN`/`Infinity` (`json_safe`/`dumps`);
  unavailable metrics are JSON `null`, never zero-filled.
- Timing and the `tracemalloc`/RSS window are measured in **separate passes** so
  tracing overhead does not distort wall-clock numbers.

Example:

```bash
python scripts/benchmark_process_memory.py \
    --samples-list 50000 200000 --channels-list 16 32 \
    --chunk-sizes 2048 16384 --repeats 3 --json
```

## Hardware and environment dependence

- Wall-clock and CPU time depend on CPU, BLAS build, thread pinning, and machine
  load. The isolated runner pins `OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1`; the
  standalone benchmark leaves threading at defaults.
- Absolute RSS depends on the interpreter build, which native libraries are
  imported (importing Torch/MNE alone can add hundreds of MB), and the system
  allocator. Only compare RSS numbers gathered on the **same** machine and
  interpreter.
- `numba` is optional. When importable, the kernel benchmark measures both the
  Numba path and the NumPy fallback; the two can differ numerically because the
  Numba kernel uses `fastmath`, so determinism is asserted **within** a backend,
  not across backends. When `numba` is absent, only the NumPy fallback is
  measured and everything still runs.

## Limitations

- RSS deltas around short workloads are dominated by allocator retention and are
  reported but not asserted.
- Peak RSS is process-lifetime on POSIX and not resettable; use process
  isolation for per-workload attribution.
- `tracemalloc` sees Python-domain allocations, not memory allocated purely
  inside C extensions outside the raw-allocator hooks.
- These are performance measurements only and must not be cited as scientific
  evidence.
