# Adaptive Streaming Budget Planner

The adaptive planner picks a **chunk size** for bounded streaming so that a
conservative *estimate* of the per-chunk working set stays under a caller-defined
memory budget, within configured `min_chunk`/`max_chunk` bounds. It is a purely
additive layer on top of PR #211's `bounded_stream` and PR #215's telemetry — it
changes none of their behavior.

- Types: `tools/streaming/adaptive_types.py`
- Planner + integration helper + demo: `tools/streaming/adaptive.py`
- Tests: `tests/performance/test_adaptive_streaming.py`

> **Scientific-integrity note.** The planner is a memory-sizing utility. Fixtures
> and demos here are performance scaffolding only — never scientific evidence. No
> topology or Bayes-factor semantics are involved.

## What it does (and does not) predict

The planner estimates the **Python array working set** for one chunk:

```
bytes_per_row          = channels * dtype_itemsize
estimated_working_set  = bytes_per_row * (chunk_size + overlap) * op_multiplier
```

It chooses the largest `chunk_size` in `[min_chunk, min(max_chunk, samples)]`
whose `estimated_working_set <= target_budget_bytes`, using conservative integer
floors. It is fully deterministic.

It does **not** predict process RSS. See [Memory-model limitations](#memory-model-limitations).

## API

### `ChunkPlanRequest` (inputs)

| Field | Meaning | Constraint |
| --- | --- | --- |
| `channels` | columns per sample row | `>= 1` |
| `samples` | total sample rows | `>= 1` |
| `dtype_itemsize` | bytes per element (use `itemsize_of`) | `>= 1` |
| `target_budget_bytes` | budget for the working-set **estimate** | `> 0` |
| `min_chunk` | smallest allowed chunk (rows) | `>= 1` |
| `max_chunk` | largest allowed chunk (rows) | `>= min_chunk` |
| `overlap` | rows kept resident alongside a chunk | `0 <= overlap < min_chunk` |
| `op_multiplier` | conservative count of simultaneous chunk-sized temporaries | `>= 1` |

Invalid inputs raise `ValueError` (clear message per field).

### `ChunkPlan` (result)

`chunk_size`, `estimated_working_set_bytes`, `safety_margin_bytes`,
`safety_margin_ratio`, `reason` (`ReasonCode`), `feasible` (bool),
`bytes_per_row`, `estimated_num_chunks`. `ChunkPlan.to_dict()` returns a
JSON-safe dict (enum → its string value; all floats finite).

### `ReasonCode` (binding constraint)

| Code | Meaning | `feasible` |
| --- | --- | --- |
| `budget_limited` | chunk sized to fit the budget, within bounds | `True` |
| `at_max_chunk` | budget allowed more; capped by `max_chunk` | `True` |
| `limited_by_samples` | fewer samples than budget/max allow; `chunk == samples` | `True` |
| `infeasible_budget_below_min` | even the floor exceeds the budget; clamped up to it | `False` |

`feasible` reports whether the estimate fits the budget. The chosen `chunk_size`
is **always** within the configured bounds — the planner never violates a bound to
meet a budget, and reports infeasibility honestly (negative safety margin).

### Functions

- `itemsize_of(dtype) -> int` — bytes per element for a NumPy dtype/type/string.
- `plan_chunk_size(request: ChunkPlanRequest) -> ChunkPlan` — the planner.
- `adaptive_bounded_stream(signal, target_budget_bytes, *, min_chunk, max_chunk, overlap=0, op_multiplier=3, transform=None, summarize=None, store_history=False, check_finite=True, track_memory=False) -> (StreamResult, ChunkPlan)` —
  additive helper that derives a plan from the signal's shape/dtype and then
  calls the unmodified `bounded_stream` with the chosen `chunk_size`.

## Examples

### Plan a chunk size

```python
from tools.streaming.adaptive import plan_chunk_size, itemsize_of
from tools.streaming.adaptive_types import ChunkPlanRequest

plan = plan_chunk_size(ChunkPlanRequest(
    channels=32, samples=200_000, dtype_itemsize=itemsize_of("float64"),
    target_budget_bytes=8 * 1024 * 1024, min_chunk=256, max_chunk=65536,
    overlap=0, op_multiplier=3,
))
# plan.chunk_size == 10922, plan.feasible is True, plan.reason == budget_limited
```

### Use it with existing bounded streaming

```python
import numpy as np
from tools.streaming.adaptive import adaptive_bounded_stream

signal = np.random.default_rng(0).standard_normal((40_000, 16))
result, plan = adaptive_bounded_stream(
    signal, target_budget_bytes=2 * 1024 * 1024,
    min_chunk=256, max_chunk=65536, op_multiplier=3, track_memory=True,
)
assert result.chunk_size == plan.chunk_size          # bounded_stream unchanged
```

### Budget sweep demo

`python -m tools.streaming.adaptive --channels 32 --samples 200000 --op-multiplier 3`

```
  budget=   1MB -> chunk=  1365 working_set=  1.0483MB within=True feasible=True reason=budget_limited
  budget=   2MB -> chunk=  2730 working_set=  2.0966MB within=True feasible=True reason=budget_limited
  budget=   4MB -> chunk=  5461 working_set=  4.1940MB within=True feasible=True reason=budget_limited
  budget=   8MB -> chunk= 10922 working_set=  8.3881MB within=True feasible=True reason=budget_limited
  budget=  16MB -> chunk= 21845 working_set= 16.7770MB within=True feasible=True reason=budget_limited
  budget=  32MB -> chunk= 43690 working_set= 33.5539MB within=True feasible=True reason=budget_limited
  budget=  64MB -> chunk= 65536 working_set= 50.3316MB within=True feasible=True reason=at_max_chunk
  budget= 128MB -> chunk= 65536 working_set= 50.3316MB within=True feasible=True reason=at_max_chunk
```

As the budget grows, the planned chunk grows monotonically until `max_chunk`
caps it; every feasible plan's estimated working set stays within its budget.
(`--json` emits a machine-readable version.)

## Determinism and monotonicity

- **Deterministic:** identical requests produce identical `ChunkPlan`s (pure
  integer/float arithmetic, no randomness, no global state).
- **Monotonic in budget:** larger budget ⇒ non-decreasing `chunk_size` (up to
  `max_chunk`).
- **Monotonic in channels/dtype/op_multiplier:** more channels, larger dtype, or
  a larger multiplier ⇒ non-increasing `chunk_size` (each resident row costs
  more).
- **JSON-safe:** `to_dict()` contains no `NaN`/`Infinity`.

## Memory-model limitations

- **Estimate, not RSS.** The planner bounds a conservative estimate of Python
  array bytes for one chunk. It does **not** predict, and does **not** guarantee,
  that total process **RSS** stays under the budget. Process RSS additionally
  includes the interpreter and imported native libraries (NumPy/Numba/SciPy/MNE/
  Torch can add hundreds of MB — PR #215 measured ~212 MB peak RSS from imports
  alone) plus allocator retention that may not return freed pages to the OS.
- **`op_multiplier` is a caller estimate.** It approximates how many chunk-sized
  temporaries an operation holds at once. If a transform allocates more than
  declared, actual usage can exceed the estimate. Choose it conservatively.
- **Overlap accounting is additive only.** `bounded_stream` itself processes
  non-overlapping chunks; the `overlap` field only inflates the working-set
  estimate for callers whose downstream operation keeps overlapping context
  resident. It does not make `bounded_stream` overlap.
- **No fragmentation/alignment modeling.** Real allocators add padding, arena
  headers, and fragmentation not captured by the linear estimate.
- **Cross-check with measurement.** Use `tools/streaming/memory_telemetry.py`
  (PR #215) to measure `tracemalloc` peak and RSS for the chosen chunk size, and
  run per-configuration in isolated processes for RSS attribution. Treat the
  planner as a sizing heuristic, validated by measurement — not a guarantee.
```
