"""Typed inputs/outputs for the deterministic adaptive chunk planner.

Kept separate from the planner logic so callers can import the data contracts
without pulling in NumPy-heavy planning code paths. All fields are plain Python
scalars/enums so the structures are trivially JSON-serializable and finite.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict


class ReasonCode(str, Enum):
    """Why the planner chose a particular chunk size.

    String-valued so it serializes directly to JSON. The code names the *binding
    constraint*, independent of feasibility (see ``ChunkPlan.feasible``).
    """

    #: Chunk sized purely to fit the memory budget (between min and max bounds).
    BUDGET_LIMITED = "budget_limited"
    #: Budget allowed a larger chunk, but ``max_chunk`` capped it.
    AT_MAX_CHUNK = "at_max_chunk"
    #: Fewer samples than the budget/max would allow; chunk == samples.
    LIMITED_BY_SAMPLES = "limited_by_samples"
    #: Even the ``min_chunk`` (or sample-limited) floor exceeds the budget, so
    #: the chunk is clamped up to that floor and ``feasible`` is ``False``.
    INFEASIBLE_BUDGET_BELOW_MIN = "infeasible_budget_below_min"


@dataclass(frozen=True)
class ChunkPlanRequest:
    """Inputs to :func:`tools.streaming.adaptive.plan_chunk_size`.

    Parameters
    ----------
    channels:
        Number of channels (columns) per sample row; ``>= 1``.
    samples:
        Total number of sample rows to stream; ``>= 1``.
    dtype_itemsize:
        Bytes per scalar element (e.g. ``8`` for float64); ``>= 1``. Use
        :func:`tools.streaming.adaptive.itemsize_of` to derive this from a NumPy
        dtype/type/string.
    target_budget_bytes:
        Desired upper bound on the estimated per-chunk working set, in bytes;
        ``> 0``. This bounds the *estimate*, not measured process RSS.
    min_chunk:
        Smallest allowed chunk size in rows; ``>= 1``.
    max_chunk:
        Largest allowed chunk size in rows; ``>= min_chunk``.
    overlap:
        Rows of overlap that must stay resident alongside a chunk; ``>= 0`` and
        ``< min_chunk`` (so the stride ``chunk - overlap`` is always positive).
    op_multiplier:
        Conservative multiplier for intermediate arrays a per-chunk operation
        materializes simultaneously (e.g. ``3`` if it holds ~3 chunk-sized
        temporaries at once); ``>= 1``.
    """

    channels: int
    samples: int
    dtype_itemsize: int
    target_budget_bytes: int
    min_chunk: int
    max_chunk: int
    overlap: int = 0
    op_multiplier: int = 1


@dataclass(frozen=True)
class ChunkPlan:
    """Deterministic result of planning a chunk size for a budget.

    Attributes
    ----------
    chunk_size:
        Chosen chunk size in rows. Always within ``[min(min_chunk, cap),
        min(max_chunk, samples)]`` where ``cap`` is the sample/max bound.
    estimated_working_set_bytes:
        Conservative estimate of bytes resident while processing one chunk:
        ``channels * dtype_itemsize * (chunk_size + overlap) * op_multiplier``.
    safety_margin_bytes:
        ``target_budget_bytes - estimated_working_set_bytes`` (negative when the
        estimate exceeds the budget, i.e. an infeasible request).
    safety_margin_ratio:
        ``safety_margin_bytes / target_budget_bytes`` (finite; may be negative).
    reason:
        The binding-constraint :class:`ReasonCode`.
    feasible:
        ``True`` iff the estimated working set is ``<= target_budget_bytes``.
    bytes_per_row:
        ``channels * dtype_itemsize`` (bytes for one sample row).
    estimated_num_chunks:
        Number of chunks to cover ``samples`` at stride ``chunk_size - overlap``.
    """

    chunk_size: int
    estimated_working_set_bytes: int
    safety_margin_bytes: int
    safety_margin_ratio: float
    reason: ReasonCode
    feasible: bool
    bytes_per_row: int
    estimated_num_chunks: int

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe dict (enum -> its string value; all values finite)."""
        data = asdict(self)
        data["reason"] = self.reason.value
        return data
