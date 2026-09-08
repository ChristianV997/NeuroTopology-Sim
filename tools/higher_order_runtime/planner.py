"""Deterministic memory planner for the bounded higher-order runtime.

Chooses a chunk size whose conservative working-set *estimate* fits a memory
budget, accounting for the streaming chunk buffer, the covariance accumulator, and
one surrogate buffer. This bounds an estimate of Python array working set -- not
process RSS (which additionally includes interpreter/import memory). Self-contained
(no import of tools/streaming) and integer-deterministic.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict


class PlanReason(str, Enum):
    BUDGET_LIMITED = "budget_limited"
    AT_MAX_CHUNK = "at_max_chunk"
    LIMITED_BY_SAMPLES = "limited_by_samples"
    INFEASIBLE_BUDGET_BELOW_MIN = "infeasible_budget_below_min"


@dataclass(frozen=True)
class PlanRequest:
    n_samples: int
    n_channels: int
    dtype_itemsize: int
    target_budget_bytes: int
    min_chunk: int
    max_chunk: int
    op_multiplier: int = 3
    surrogates: bool = True


@dataclass(frozen=True)
class MemoryPlan:
    chunk_size: int
    estimated_working_set_bytes: int
    fixed_overhead_bytes: int
    safety_margin_bytes: int
    safety_margin_ratio: float
    reason: PlanReason
    feasible: bool
    bytes_per_row: int
    estimated_num_chunks: int

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["reason"] = self.reason.value
        return data


def _validate(r: PlanRequest) -> None:
    if r.n_samples < 1:
        raise ValueError("n_samples must be >= 1")
    if r.n_channels < 1:
        raise ValueError("n_channels must be >= 1")
    if r.dtype_itemsize < 1:
        raise ValueError("dtype_itemsize must be >= 1")
    if r.target_budget_bytes <= 0:
        raise ValueError("target_budget_bytes must be > 0")
    if r.min_chunk < 1:
        raise ValueError("min_chunk must be >= 1")
    if r.max_chunk < r.min_chunk:
        raise ValueError("max_chunk must be >= min_chunk")
    if r.op_multiplier < 1:
        raise ValueError("op_multiplier must be >= 1")


def plan_chunk(request: PlanRequest) -> MemoryPlan:
    """Pick the largest in-bounds chunk whose working-set estimate fits budget."""
    _validate(request)
    r = request
    bytes_per_row = r.n_channels * r.dtype_itemsize
    # Fixed transient overhead (beyond the resident input signal):
    #   - covariance co-moment accumulator M2 (C x C);
    #   - the one-at-a-time surrogate stage holds only a few (n,) column
    #     temporaries (ref + rolled + centered), independent of channel count --
    #     NOT a full (n, C) surrogate matrix, since surrogates are streamed.
    cov_bytes = r.n_channels * r.n_channels * r.dtype_itemsize
    surrogate_bytes = (3 * r.n_samples * r.dtype_itemsize) if r.surrogates else 0
    fixed_overhead = cov_bytes + surrogate_bytes

    per_row_cost = bytes_per_row * r.op_multiplier
    budget_for_chunk = r.target_budget_bytes - fixed_overhead
    budget_chunk = budget_for_chunk // per_row_cost if budget_for_chunk > 0 else -1

    cap = min(r.max_chunk, r.n_samples)
    floor = min(r.min_chunk, cap)

    if budget_chunk >= cap:
        chunk = cap
        reason = (PlanReason.LIMITED_BY_SAMPLES
                  if cap == r.n_samples and r.n_samples < r.max_chunk
                  else PlanReason.AT_MAX_CHUNK)
    elif budget_chunk >= floor:
        chunk = int(budget_chunk)
        reason = PlanReason.BUDGET_LIMITED
    else:
        chunk = floor
        reason = PlanReason.INFEASIBLE_BUDGET_BELOW_MIN

    working_set = bytes_per_row * chunk * r.op_multiplier + fixed_overhead
    feasible = working_set <= r.target_budget_bytes
    safety_margin = r.target_budget_bytes - working_set
    safety_ratio = safety_margin / r.target_budget_bytes
    estimated_num_chunks = (r.n_samples + chunk - 1) // chunk

    return MemoryPlan(
        chunk_size=int(chunk),
        estimated_working_set_bytes=int(working_set),
        fixed_overhead_bytes=int(fixed_overhead),
        safety_margin_bytes=int(safety_margin),
        safety_margin_ratio=float(safety_ratio),
        reason=reason,
        feasible=bool(feasible),
        bytes_per_row=int(bytes_per_row),
        estimated_num_chunks=int(estimated_num_chunks),
    )
