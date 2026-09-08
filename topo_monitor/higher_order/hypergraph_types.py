"""Types and schemas for sparse directed hypergraphs for multimodal transitions.

Strict invariants:
1. All JSON output must use allow_nan=False (NaN/Inf serialized as explicit null).
2. Graph beta-1 cycle counts, spatial winding charge (Q_spatial), and hyperedge order
   must remain mathematically and structurally separate.
3. Directional hyperedges represent dependency structures, NOT automatic causal proofs.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Sequence

SCHEMA_VERSION = "1.0.0"
SCIENTIFIC_DISCLAIMER = (
    "Directed hypergraphs represent sparse multivariate dependency structures and "
    "temporal transition patterns. They do not constitute automatic proof of causal biological "
    "mechanisms without an explicit causal interventional design. Graph beta-1 persistence, "
    "ordinary graph cycles, and spatial phase charge are mathematically distinct."
)


def sanitize_float(val: Any) -> float | None:
    """Return finite float or None if val is NaN, Inf, or None. Never returns NaN or Inf."""
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class DirectedHyperedge:
    """A directed hyperedge (hyperarc) from a source node set to a target node set."""

    source_nodes: tuple[str, ...]
    target_nodes: tuple[str, ...]
    weight: float
    timestamp: float | None = None
    window: tuple[float, float] | None = None
    provenance: str = "synthetic_fixture"
    context_variables: dict[str, Any] | None = None
    confidence: float = 1.0
    synthetic: bool = True

    def __post_init__(self) -> None:
        if not self.source_nodes:
            raise ValueError("source_nodes must be non-empty")
        if not self.target_nodes:
            raise ValueError("target_nodes must be non-empty")

        # Canonicalize source and target nodes: sorted, unique
        s_sorted = tuple(sorted(set(str(n) for n in self.source_nodes)))
        t_sorted = tuple(sorted(set(str(n) for n in self.target_nodes)))

        # Enforce disjoint source and target
        if set(s_sorted).intersection(set(t_sorted)):
            raise ValueError(
                f"source_nodes and target_nodes must be disjoint: {s_sorted} vs {t_sorted}"
            )

        object.__setattr__(self, "source_nodes", s_sorted)
        object.__setattr__(self, "target_nodes", t_sorted)
        object.__setattr__(self, "weight", float(self.weight))
        object.__setattr__(self, "confidence", float(min(1.0, max(0.0, self.confidence))))

        if self.window is not None:
            w_start = float(self.window[0])
            w_end = float(self.window[1])
            if w_end < w_start:
                raise ValueError(f"Invalid window: end ({w_end}) < start ({w_start})")
            object.__setattr__(self, "window", (w_start, w_end))

    @property
    def order(self) -> int:
        """Total number of distinct nodes involved in the hyperedge."""
        return len(self.source_nodes) + len(self.target_nodes)

    @property
    def tail_size(self) -> int:
        """Number of source (tail) nodes."""
        return len(self.source_nodes)

    @property
    def head_size(self) -> int:
        """Number of target (head) nodes."""
        return len(self.target_nodes)

    def canonical_key(self) -> str:
        """Deterministic string key representing the directed hyperedge topology."""
        return f"({','.join(self.source_nodes)})->({','.join(self.target_nodes)})"

    def canonical_digest(self) -> str:
        """Deterministic SHA-256 digest of hyperedge content."""
        w_str = f"{round(self.weight, 6):.6f}"
        c_str = f"{round(self.confidence, 4):.4f}"
        ts_str = f"{round(self.timestamp, 6):.6f}" if self.timestamp is not None else "null"
        win_str = (
            f"[{round(self.window[0], 6):.6f},{round(self.window[1], 6):.6f}]"
            if self.window is not None
            else "null"
        )
        ctx_str = (
            json.dumps(self.context_variables, sort_keys=True, allow_nan=False)
            if self.context_variables is not None
            else "null"
        )
        payload = (
            f"{self.canonical_key()}|w={w_str}|c={c_str}|ts={ts_str}|win={win_str}|"
            f"prov={self.provenance}|ctx={ctx_str}|syn={self.synthetic}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary with strict null safety."""
        clean_ctx = None
        if self.context_variables is not None:
            clean_ctx = {
                k: sanitize_float(v) if isinstance(v, (int, float)) else v
                for k, v in sorted(self.context_variables.items())
            }

        return {
            "source_nodes": list(self.source_nodes),
            "target_nodes": list(self.target_nodes),
            "order": self.order,
            "tail_size": self.tail_size,
            "head_size": self.head_size,
            "weight": sanitize_float(self.weight),
            "timestamp": sanitize_float(self.timestamp),
            "window": [sanitize_float(self.window[0]), sanitize_float(self.window[1])]
            if self.window is not None
            else None,
            "provenance": self.provenance,
            "context_variables": clean_ctx,
            "confidence": sanitize_float(self.confidence),
            "synthetic": self.synthetic,
            "canonical_key": self.canonical_key(),
            "canonical_digest": self.canonical_digest(),
        }


@dataclass(frozen=True)
class HypergraphSparsityConfig:
    """Configuration for sparse directed hyperedge pruning and resource budgeting."""

    top_k: int = 100
    score_threshold: float = 0.0
    max_hyperedge_order: int = 5
    memory_budget_bytes: int = 10_000_000  # 10 MB default safety envelope
    deterministic_ordering: bool = True

    def __post_init__(self) -> None:
        if self.top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {self.top_k}")
        if self.max_hyperedge_order < 2:
            raise ValueError(f"max_hyperedge_order must be >= 2, got {self.max_hyperedge_order}")
        if self.memory_budget_bytes < 1024:
            raise ValueError("memory_budget_bytes must be at least 1 KB")

    def to_dict(self) -> dict[str, Any]:
        return {
            "top_k": self.top_k,
            "score_threshold": sanitize_float(self.score_threshold),
            "max_hyperedge_order": self.max_hyperedge_order,
            "memory_budget_bytes": self.memory_budget_bytes,
            "deterministic_ordering": self.deterministic_ordering,
        }


@dataclass(frozen=True)
class DirectedHypergraphSummary:
    """Summary metrics of a sparse directed hypergraph transition model."""

    hyperedge_count: int
    node_count: int
    order_distribution: dict[int, int]
    weighted_in_influence: dict[str, float]
    weighted_out_influence: dict[str, float]
    temporal_persistence: float | None
    source_target_asymmetry: float
    context_conditioned_transition_score: dict[str, float]
    distinct_from_topology: dict[str, str] = field(
        default_factory=lambda: {
            "ordinary_graph_cycles": "strictly_separate",
            "beta_1_persistence": "strictly_separate",
            "spatial_phase_winding": "strictly_separate",
            "directed_transition_influence": "higher_order_hypergraph_metric",
        }
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "hyperedge_count": self.hyperedge_count,
            "node_count": self.node_count,
            "order_distribution": {str(k): v for k, v in sorted(self.order_distribution.items())},
            "weighted_in_influence": {
                k: sanitize_float(v) for k, v in sorted(self.weighted_in_influence.items())
            },
            "weighted_out_influence": {
                k: sanitize_float(v) for k, v in sorted(self.weighted_out_influence.items())
            },
            "temporal_persistence": sanitize_float(self.temporal_persistence),
            "source_target_asymmetry": sanitize_float(self.source_target_asymmetry),
            "context_conditioned_transition_score": {
                k: sanitize_float(v)
                for k, v in sorted(self.context_conditioned_transition_score.items())
            },
            "distinct_from_topology": self.distinct_from_topology,
        }


@dataclass(frozen=True)
class CommonDriverControlResult:
    """Audit result testing whether an apparent directed transition is explained by a common driver."""

    apparent_transition: str
    candidate_driver: str
    direct_score: float
    conditioned_score: float
    common_driver_explained: bool
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "apparent_transition": self.apparent_transition,
            "candidate_driver": self.candidate_driver,
            "direct_score": sanitize_float(self.direct_score),
            "conditioned_score": sanitize_float(self.conditioned_score),
            "common_driver_explained": self.common_driver_explained,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class LabelPermutationControlResult:
    """Control evaluation comparing observed hyperedge weights to label-permuted null distributions."""

    observed_mean_weight: float
    null_mean_weight: float
    null_std_weight: float
    z_score: float | None
    p_value_empirical: float | None
    num_permutations: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "observed_mean_weight": sanitize_float(self.observed_mean_weight),
            "null_mean_weight": sanitize_float(self.null_mean_weight),
            "null_std_weight": sanitize_float(self.null_std_weight),
            "z_score": sanitize_float(self.z_score),
            "p_value_empirical": sanitize_float(self.p_value_empirical),
            "num_permutations": self.num_permutations,
        }


@dataclass
class DirectedHypergraphReport:
    """Comprehensive report representing a sparse directed hypergraph transition model."""

    schema_version: str
    created_at_utc: str
    summary: DirectedHypergraphSummary
    hyperedges: list[DirectedHyperedge]
    common_driver_controls: list[CommonDriverControlResult]
    label_permutation_control: LabelPermutationControlResult | None
    deterministic_checksum: str
    provenance: str
    synthetic: bool
    evidence_class: str
    scientific_disclaimer: str = SCIENTIFIC_DISCLAIMER

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created_at_utc": self.created_at_utc,
            "summary": self.summary.to_dict(),
            "hyperedge_count": len(self.hyperedges),
            "hyperedges": [e.to_dict() for e in self.hyperedges],
            "common_driver_controls": [c.to_dict() for c in self.common_driver_controls],
            "label_permutation_control": (
                self.label_permutation_control.to_dict()
                if self.label_permutation_control is not None
                else None
            ),
            "deterministic_checksum": self.deterministic_checksum,
            "provenance": self.provenance,
            "synthetic": self.synthetic,
            "evidence_class": self.evidence_class,
            "scientific_disclaimer": self.scientific_disclaimer,
        }

    def to_json(self, indent: int | None = 2) -> str:
        """Serialize to JSON string with strict allow_nan=False null safety."""
        return json.dumps(self.to_dict(), indent=indent, allow_nan=False)
