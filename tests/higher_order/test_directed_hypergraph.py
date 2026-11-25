"""Unit and integration tests for sparse directed-hypergraph representation and transition modeling."""
from __future__ import annotations

import json
import socket
import pytest

from topo_monitor.higher_order.hypergraph import SparseDirectedHypergraph
from topo_monitor.higher_order.hypergraph_types import (
    DirectedHyperedge,
    HypergraphSparsityConfig,
)


def test_known_directed_triad():
    """Test directed triad {A, B} -> {C} with known weight and influence."""
    edge = DirectedHyperedge(
        source_nodes=("A", "B"),
        target_nodes=("C",),
        weight=2.0,
        confidence=0.95,
        context_variables={"modality": "eeg_ecg"},
    )
    hg = SparseDirectedHypergraph([edge])
    assert len(hg) == 1
    assert hg.hyperedges[0].order == 3
    assert hg.hyperedges[0].tail_size == 2
    assert hg.hyperedges[0].head_size == 1

    summary = hg.compute_summary()
    assert summary.hyperedge_count == 1
    assert summary.node_count == 3
    assert summary.order_distribution == {3: 1}
    assert summary.weighted_out_influence["A"] == 2.0
    assert summary.weighted_out_influence["B"] == 2.0
    assert summary.weighted_in_influence["C"] == 2.0
    assert "C" not in summary.weighted_out_influence


def test_hyperedge_order_and_distribution():
    """Test hyperedge order calculations across orders 2, 3, 4."""
    e1 = DirectedHyperedge(source_nodes=("A",), target_nodes=("B",), weight=1.0)  # order 2
    e2 = DirectedHyperedge(source_nodes=("A", "B"), target_nodes=("C",), weight=1.5)  # order 3
    e3 = DirectedHyperedge(source_nodes=("A", "B"), target_nodes=("C", "D"), weight=2.5)  # order 4

    hg = SparseDirectedHypergraph([e1, e2, e3])
    assert len(hg) == 3
    summary = hg.compute_summary()
    assert summary.order_distribution == {2: 1, 3: 1, 4: 1}


def test_node_permutation_invariance():
    """Test that arbitrary relabeling of node identities preserves summary invariants."""
    e1 = DirectedHyperedge(source_nodes=("A", "B"), target_nodes=("C",), weight=3.0)
    e2 = DirectedHyperedge(source_nodes=("B",), target_nodes=("D",), weight=1.0)
    e3 = DirectedHyperedge(source_nodes=("C", "D"), target_nodes=("E",), weight=2.0)
    hg = SparseDirectedHypergraph([e1, e2, e3])

    permutation = {"A": "NODE_1", "B": "NODE_2", "C": "NODE_3", "D": "NODE_4", "E": "NODE_5"}
    assert hg.is_node_reordering_invariant(permutation) is True

    relabeled = hg.relabel_nodes(permutation)
    orig_summary = hg.compute_summary()
    new_summary = relabeled.compute_summary()
    assert orig_summary.order_distribution == new_summary.order_distribution
    assert orig_summary.source_target_asymmetry == new_summary.source_target_asymmetry


def test_score_threshold_filtering():
    """Test that edges below score threshold are pruned."""
    e1 = DirectedHyperedge(source_nodes=("A",), target_nodes=("B",), weight=0.2)
    e2 = DirectedHyperedge(source_nodes=("A",), target_nodes=("C",), weight=0.8)
    e3 = DirectedHyperedge(source_nodes=("B",), target_nodes=("D",), weight=0.5)

    config = HypergraphSparsityConfig(score_threshold=0.5)
    hg = SparseDirectedHypergraph([e1, e2, e3], config=config)
    assert len(hg) == 2
    keys = [e.canonical_key() for e in hg.hyperedges]
    assert "(A)->(C)" in keys
    assert "(B)->(D)" in keys
    assert "(A)->(B)" not in keys


def test_top_k_bound_enforcement():
    """Test that hyperedges are strictly bounded to top-k."""
    edges = [
        DirectedHyperedge(source_nodes=(f"S_{i}",), target_nodes=(f"T_{i}",), weight=float(i))
        for i in range(20)
    ]
    config = HypergraphSparsityConfig(top_k=5)
    hg = SparseDirectedHypergraph(edges, config=config)
    assert len(hg) == 5
    # Retained weights must be top 5 (19.0, 18.0, 17.0, 16.0, 15.0)
    retained_weights = [e.weight for e in hg.hyperedges]
    assert retained_weights == [19.0, 18.0, 17.0, 16.0, 15.0]


def test_missing_context_handling():
    """Test that missing context variables default cleanly to None and serialize to null."""
    edge = DirectedHyperedge(
        source_nodes=("A",),
        target_nodes=("B",),
        weight=1.0,
        context_variables=None,
    )
    hg = SparseDirectedHypergraph([edge])
    summary = hg.compute_summary()
    assert summary.context_conditioned_transition_score == {}

    d = edge.to_dict()
    assert d["context_variables"] is None


def test_common_driver_null_control():
    """Test that third-node common-driver confounding is detected."""
    # S and T are both driven by common driver Z: Z -> S, Z -> T, apparent S -> T
    e_z_s = DirectedHyperedge(source_nodes=("Z",), target_nodes=("A",), weight=2.0)
    e_z_t = DirectedHyperedge(source_nodes=("Z",), target_nodes=("B",), weight=2.0)
    e_s_t = DirectedHyperedge(source_nodes=("A",), target_nodes=("B",), weight=1.5)

    hg = SparseDirectedHypergraph([e_z_s, e_z_t, e_s_t])
    controls = hg.run_common_driver_control(candidate_drivers=["Z"])
    assert len(controls) > 0
    # The (A)->(B) transition should be flagged as explained by Z
    ab_control = next(c for c in controls if c.apparent_transition == "(A)->(B)")
    assert ab_control.common_driver_explained is True
    assert "Z" in ab_control.candidate_driver


def test_deterministic_output_and_checksum():
    """Test that identical hyperedge inputs produce bit-for-bit identical checksums."""
    edges1 = [
        DirectedHyperedge(source_nodes=("X", "Y"), target_nodes=("Z",), weight=1.5),
        DirectedHyperedge(source_nodes=("A",), target_nodes=("B",), weight=2.0),
    ]
    edges2 = [
        DirectedHyperedge(source_nodes=("A",), target_nodes=("B",), weight=2.0),
        DirectedHyperedge(source_nodes=("X", "Y"), target_nodes=("Z",), weight=1.5),
    ]
    hg1 = SparseDirectedHypergraph(edges1)
    hg2 = SparseDirectedHypergraph(edges2)
    assert hg1.compute_checksum() == hg2.compute_checksum()


def test_memory_bound_enforcement():
    """Test that a restrictive memory budget caps retention."""
    edges = [
        DirectedHyperedge(source_nodes=(f"Node_{i}",), target_nodes=(f"Target_{i}",), weight=float(i))
        for i in range(100)
    ]
    # Restrict budget to very small size (1500 bytes)
    config = HypergraphSparsityConfig(top_k=100, memory_budget_bytes=1500)
    hg = SparseDirectedHypergraph(edges, config=config)
    assert len(hg) < 100
    assert len(hg) > 0


def test_no_network_operation(monkeypatch):
    """Test that construction and summary calculations execute completely offline."""
    def forbidden_connect(*args, **kwargs):
        raise RuntimeError("Forbidden outbound network call during hypergraph computation")

    monkeypatch.setattr(socket, "create_connection", forbidden_connect)

    edges = [DirectedHyperedge(source_nodes=("A", "B"), target_nodes=("C",), weight=1.2)]
    hg = SparseDirectedHypergraph(edges)
    rep = hg.build_report(provenance="offline_test")
    assert rep.schema_version == "1.0.0"
    assert rep.synthetic is True


def test_mathematical_separation_from_topology():
    """Verify that graph beta-1 and spatial phase charge are explicitly isolated from hyperedge metrics."""
    e = DirectedHyperedge(source_nodes=("N1", "N2"), target_nodes=("N3",), weight=1.0)
    hg = SparseDirectedHypergraph([e])
    summary = hg.compute_summary()
    d = summary.to_dict()

    assert "distinct_from_topology" in d
    assert d["distinct_from_topology"]["ordinary_graph_cycles"] == "strictly_separate"
    assert d["distinct_from_topology"]["beta_1_persistence"] == "strictly_separate"
    assert d["distinct_from_topology"]["spatial_phase_winding"] == "strictly_separate"
    # Ensure no conflated keys exist
    assert "beta_1" not in d
    assert "spatial_charge" not in d


def test_multimodal_transition_construction():
    """Test construction from multimodal events (EEG, ECG, respiration)."""
    events = [
        {
            "timestamp": 0.0,
            "features": ["EEG_theta_high", "ECG_HRV_low"],
            "weight": 1.0,
            "context_variables": {"state": "pre_transition"},
        },
        {
            "timestamp": 0.5,
            "features": ["Respiration_apnea_onset"],
            "weight": 2.5,
            "context_variables": {"state": "apnea_transition"},
        },
    ]
    hg = SparseDirectedHypergraph.from_multimodal_feature_events(events, lag_window=1.0)
    assert len(hg) == 1
    edge = hg.hyperedges[0]
    assert "EEG_theta_high" in edge.source_nodes
    assert "ECG_HRV_low" in edge.source_nodes
    assert edge.target_nodes == ("Respiration_apnea_onset",)
    assert edge.order == 3


def test_strict_finite_json_serialization():
    """Test that build_report().to_json() succeeds with allow_nan=False."""
    edges = [
        DirectedHyperedge(
            source_nodes=("A",),
            target_nodes=("B",),
            weight=1.5,
            timestamp=None,
            window=(1.0, 2.5),
            context_variables={"test_key": "test_val"},
        )
    ]
    hg = SparseDirectedHypergraph(edges)
    rep = hg.build_report(provenance="test_provenance", evidence_class="TEST_ONLY")
    json_str = rep.to_json()
    data = json.loads(json_str)
    assert data["schema_version"] == "1.0.0"
    assert data["provenance"] == "test_provenance"
    assert data["evidence_class"] == "TEST_ONLY"
    assert data["hyperedge_count"] == 1
    assert data["hyperedges"][0]["timestamp"] is None
