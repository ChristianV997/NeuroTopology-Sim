"""Deterministic adaptive chunk planner for bounded streaming.

Given a working-set memory *budget* and the shape/dtype of a signal, pick the
largest chunk size (within caller-configured bounds) whose **estimated** per-chunk
working set stays under the budget. The estimate is intentionally conservative
and integer-deterministic; it bounds an *estimate*, not measured process RSS.

This module is purely additive: it does not modify or wrap the behavior of
``tools.streaming.bounded.bounded_stream`` -- the optional integration helper
:func:`adaptive_bounded_stream` merely *chooses* a chunk size and then calls
``bounded_stream`` exactly as a caller would.

Memory-model caveat (see ``docs/adaptive_streaming.md``): the planner estimates
Python array working set only. It cannot and does not predict total process RSS,
which additionally includes interpreter and imported-library memory (hundreds of
MB for NumPy/Numba/SciPy/MNE/Torch) plus allocator retention. Never treat a
feasible plan as a guarantee that process RSS stays under the budget.
"""
from __future__ import annotations

from typing import Any, Callable, Optional, Tuple

import numpy as np

from .adaptive_types import ChunkPlan, ChunkPlanRequest, ReasonCode

__all__ = [
    "itemsize_of",
    "plan_chunk_size",
    "adaptive_bounded_stream",
]


def itemsize_of(dtype: Any) -> int:
    """Return bytes-per-element for a NumPy dtype/type/string.

    Raises ``ValueError`` for an unresolvable or zero-size dtype.
    """
    try:
        size = int(np.dtype(dtype).itemsize)
    except TypeError as exc:
        raise ValueError(f"unrecognized dtype: {dtype!r}") from exc
    if size < 1:
        raise ValueError(f"dtype {dtype!r} has non-positive itemsize {size}")
    return size


def _working_set_bytes(bytes_per_row: int, chunk: int, overlap: int, op_multiplier: int) -> int:
    """Conservative resident-bytes estimate for processing one chunk."""
    return bytes_per_row * (chunk + overlap) * op_multiplier


def _validate(request: ChunkPlanRequest) -> None:
    r = request
    if r.channels < 1:
        raise ValueError("channels must be >= 1")
    if r.samples < 1:
        raise ValueError("samples must be >= 1")
    if r.dtype_itemsize < 1:
        raise ValueError("dtype_itemsize must be >= 1")
    if r.target_budget_bytes <= 0:
        raise ValueError("target_budget_bytes must be > 0")
    if r.min_chunk < 1:
        raise ValueError("min_chunk must be >= 1")
    if r.max_chunk < r.min_chunk:
        raise ValueError("max_chunk must be >= min_chunk")
    if r.overlap < 0:
        raise ValueError("overlap must be >= 0")
    if r.overlap >= r.min_chunk:
        raise ValueError("overlap must be < min_chunk (so stride is positive)")
    if r.op_multiplier < 1:
        raise ValueError("op_multiplier must be >= 1")


def plan_chunk_size(request: ChunkPlanRequest) -> ChunkPlan:
    """Deterministically choose a chunk size for ``request``.

    The chosen chunk is always within ``[min(min_chunk, cap), cap]`` where
    ``cap = min(max_chunk, samples)`` -- configured bounds are never exceeded.
    Feasibility (estimate within budget) is reported separately via
    :attr:`ChunkPlan.feasible`; the planner never silently violates a bound to
    meet a budget, and never claims RSS is exactly predicted.
    """
    _validate(request)
    r = request
    bytes_per_row = r.channels * r.dtype_itemsize
    per_row_cost = bytes_per_row * r.op_multiplier  # cost of one resident row

    # Largest chunk whose (chunk + overlap) rows fit the budget (conservative floor).
    budget_rows_total = r.target_budget_bytes // per_row_cost      # total resident rows affordable
    budget_chunk = budget_rows_total - r.overlap                   # rows available for the chunk itself

    cap = min(r.max_chunk, r.samples)          # hard upper bound (bounds + data)
    floor = min(r.min_chunk, cap)              # cannot require more rows than exist

    if budget_chunk >= cap:
        chunk = cap
        if cap == r.samples and r.samples < r.max_chunk:
            reason = ReasonCode.LIMITED_BY_SAMPLES
        else:
            reason = ReasonCode.AT_MAX_CHUNK
    elif budget_chunk >= floor:
        chunk = budget_chunk
        reason = ReasonCode.BUDGET_LIMITED
    else:
        # Budget cannot afford even the floor (min_chunk, or samples when
        # smaller). Clamp up to the floor and report the request as infeasible.
        chunk = floor
        reason = ReasonCode.INFEASIBLE_BUDGET_BELOW_MIN

    working_set = _working_set_bytes(bytes_per_row, chunk, r.overlap, r.op_multiplier)
    feasible = working_set <= r.target_budget_bytes

    safety_margin = r.target_budget_bytes - working_set
    safety_ratio = safety_margin / r.target_budget_bytes  # finite: budget > 0

    stride = max(chunk - r.overlap, 1)
    estimated_num_chunks = (r.samples + stride - 1) // stride

    return ChunkPlan(
        chunk_size=int(chunk),
        estimated_working_set_bytes=int(working_set),
        safety_margin_bytes=int(safety_margin),
        safety_margin_ratio=float(safety_ratio),
        reason=reason,
        feasible=bool(feasible),
        bytes_per_row=int(bytes_per_row),
        estimated_num_chunks=int(estimated_num_chunks),
    )


def adaptive_bounded_stream(
    signal: np.ndarray,
    target_budget_bytes: int,
    *,
    min_chunk: int,
    max_chunk: int,
    overlap: int = 0,
    op_multiplier: int = 3,
    transform: Optional[Callable[[np.ndarray, np.ndarray], np.ndarray]] = None,
    summarize: Optional[Callable[[int, np.ndarray], object]] = None,
    store_history: bool = False,
    check_finite: bool = True,
    track_memory: bool = False,
) -> Tuple[Any, ChunkPlan]:
    """Plan a chunk size for ``signal`` under a budget, then run ``bounded_stream``.

    This is an *additive* convenience wrapper: it derives a :class:`ChunkPlan`
    from the signal's shape/dtype and the given budget/bounds, then calls the
    unmodified ``tools.streaming.bounded.bounded_stream`` with the chosen chunk
    size. It returns ``(StreamResult, ChunkPlan)``.

    Note: ``bounded_stream`` processes *non-overlapping* chunks. ``overlap`` here
    only feeds the working-set estimate (for callers whose downstream operation
    keeps overlapping context resident); it does not make ``bounded_stream``
    overlap. The default ``op_multiplier=3`` is a conservative allowance for a
    transform holding a few chunk-sized temporaries at once.
    """
    from .bounded import bounded_stream  # local import: keep planning import-light

    data = np.asarray(signal)
    if data.ndim == 1:
        channels = 1
    elif data.ndim == 2:
        channels = int(data.shape[1])
    else:
        raise ValueError("signal must be 1-D (samples,) or 2-D (samples, channels)")
    samples = int(data.shape[0])

    plan = plan_chunk_size(ChunkPlanRequest(
        channels=channels,
        samples=samples,
        dtype_itemsize=itemsize_of(data.dtype),
        target_budget_bytes=int(target_budget_bytes),
        min_chunk=int(min_chunk),
        max_chunk=int(max_chunk),
        overlap=int(overlap),
        op_multiplier=int(op_multiplier),
    ))

    result = bounded_stream(
        data,
        plan.chunk_size,
        transform=transform,
        summarize=summarize,
        store_history=store_history,
        check_finite=check_finite,
        track_memory=track_memory,
    )
    return result, plan


# --------------------------------------------------------------------------- #
# Benchmark / demonstration example
# --------------------------------------------------------------------------- #
def _budget_sweep_demo(channels: int = 32, samples: int = 200_000,
                       dtype: Any = np.float64, op_multiplier: int = 3) -> list[dict]:
    """Show that planned working-set estimates stay within each budget.

    Sweeps a range of budgets and returns one plan summary per budget. Feasible
    plans always report ``estimated_working_set_bytes <= budget``.
    """
    itemsize = itemsize_of(dtype)
    rows = []
    for budget_mb in (1, 2, 4, 8, 16, 32, 64, 128):
        budget = budget_mb * 1024 * 1024
        plan = plan_chunk_size(ChunkPlanRequest(
            channels=channels, samples=samples, dtype_itemsize=itemsize,
            target_budget_bytes=budget, min_chunk=256, max_chunk=65536,
            overlap=0, op_multiplier=op_multiplier,
        ))
        rows.append({
            "budget_mb": budget_mb,
            "chunk_size": plan.chunk_size,
            "working_set_mb": round(plan.estimated_working_set_bytes / 1e6, 4),
            "within_budget": plan.estimated_working_set_bytes <= budget,
            "feasible": plan.feasible,
            "reason": plan.reason.value,
            "safety_margin_ratio": round(plan.safety_margin_ratio, 4),
        })
    return rows


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Adaptive chunk-planner budget sweep demo.")
    ap.add_argument("--channels", type=int, default=32)
    ap.add_argument("--samples", type=int, default=200_000)
    ap.add_argument("--op-multiplier", type=int, default=3)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    rows = _budget_sweep_demo(channels=args.channels, samples=args.samples,
                              op_multiplier=args.op_multiplier)
    all_ok = all(r["within_budget"] for r in rows if r["feasible"])
    if args.json:
        print(json.dumps({"sweep": rows, "all_feasible_within_budget": all_ok}, indent=2))
    else:
        print(f"channels={args.channels} samples={args.samples} op_multiplier={args.op_multiplier}")
        for r in rows:
            print(f"  budget={r['budget_mb']:4d}MB -> chunk={r['chunk_size']:6d} "
                  f"working_set={r['working_set_mb']:8.4f}MB within={r['within_budget']} "
                  f"feasible={r['feasible']} reason={r['reason']}")
        print(f"all feasible plans within budget: {all_ok}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
