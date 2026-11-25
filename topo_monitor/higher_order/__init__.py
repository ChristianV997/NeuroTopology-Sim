"""Higher-order topology and statistical connectivity features."""

from __future__ import annotations

from topo_monitor.higher_order.hypergraph import SparseDirectedHypergraph
from topo_monitor.higher_order.hypergraph_types import (
    SCHEMA_VERSION as HYPERGRAPH_SCHEMA_VERSION,
    SCIENTIFIC_DISCLAIMER,
    CommonDriverControlResult,
    DirectedHyperedge,
    DirectedHypergraphReport,
    DirectedHypergraphSummary,
    HypergraphSparsityConfig,
    LabelPermutationControlResult,
    sanitize_float,
)
from topo_monitor.higher_order.triadic import (
    SCHEMA_VERSION,
    SUPPORTED_SURROGATES,
    Provenance,
    SignalWindow,
    SurrogateComparison,
    TriadicConnectivityResult,
    TriadicEntropySummary,
    TriadicInteraction,
    array_checksum,
    canonical_checksum,
    canonical_json,
    estimate_triadic_connectivity,
)

__all__ = [
    "CommonDriverControlResult",
    "DirectedHyperedge",
    "DirectedHypergraphReport",
    "DirectedHypergraphSummary",
    "HypergraphSparsityConfig",
    "LabelPermutationControlResult",
    "HYPERGRAPH_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "SCIENTIFIC_DISCLAIMER",
    "SparseDirectedHypergraph",
    "sanitize_float",
    "SUPPORTED_SURROGATES",
    "Provenance",
    "SignalWindow",
    "SurrogateComparison",
    "TriadicConnectivityResult",
    "TriadicEntropySummary",
    "TriadicInteraction",
    "array_checksum",
    "canonical_checksum",
    "canonical_json",
    "estimate_triadic_connectivity",
]
