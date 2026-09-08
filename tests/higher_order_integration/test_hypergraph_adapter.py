"""Integration test suite for directed-hypergraph feature adapter and forecasting contracts."""
from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tools.higher_order_integration.hypergraph_adapter import (
    HypergraphFeatureAdapter,
    HypergraphValidationConfig,
    NormalizedHyperedge,
)
from topo_monitor.higher_order.hypergraph_types import DirectedHyperedge
from transitions.features import validate_feature_name


def _build_sample_edges() -> list[DirectedHyperedge]:
    return [
        DirectedHyperedge(
            source_nodes=("A", "B"),
            target_nodes=("C",),
            weight=2.0,
            confidence=0.9,
            window=(0.0, 2.5),
            context_variables={"modality": "eeg_ecg"},
            provenance="pipeline_test",
        ),
        DirectedHyperedge(
            source_nodes=("C",),
            target_nodes=("D", "E"),
            weight=1.5,
            confidence=0.85,
            window=(2.5, 5.0),
            context_variables={"modality": "eeg_ecg"},
            provenance="pipeline_test",
        ),
    ]


def test_normalization_and_canonical_formatting():
    adapter = HypergraphFeatureAdapter()
    edges = _build_sample_edges()
    norm_edges, issues = adapter.validate_and_normalize(edges)

    assert len(norm_edges) == 2
    assert not any(i.issue_type == "error" for i in issues)
    assert norm_edges[0].order == 3
    assert norm_edges[0].declared_units == "coupling_weight"
    assert norm_edges[0].canonical_key() == "(A,B)->(C)"


def test_malformed_inputs_caught_and_reported():
    adapter = HypergraphFeatureAdapter()

    # 1. Non-disjoint sources and targets
    bad_record_overlapping = {"sources": ["A", "B"], "targets": ["B", "C"], "weight": 1.0}
    # 2. Empty sources
    bad_record_empty = {"sources": [], "targets": ["C"], "weight": 1.0}
    # 3. Non-finite weight
    bad_record_inf = {"sources": ["A"], "targets": ["B"], "weight": float("inf")}

    norm, issues = adapter.validate_and_normalize(
        [bad_record_overlapping, bad_record_empty, bad_record_inf]
    )
    assert len(norm) == 0
    errors = [i for i in issues if i.issue_type == "error"]
    assert len(errors) >= 3


def test_duplicate_hyperedge_rejection():
    adapter = HypergraphFeatureAdapter()
    e1 = DirectedHyperedge(source_nodes=("A",), target_nodes=("B",), weight=1.0)
    e2 = DirectedHyperedge(source_nodes=("A",), target_nodes=("B",), weight=2.0)

    norm, issues = adapter.validate_and_normalize([e1, e2])
    # The duplicate should be flagged
    dup_issues = [i for i in issues if "Duplicate" in i.message]
    assert len(dup_issues) == 1
    assert len(norm) == 1


def test_bounded_hyperedge_count_enforcement():
    config = HypergraphValidationConfig(max_hyperedges=3)
    adapter = HypergraphFeatureAdapter(config=config)
    edges = [
        DirectedHyperedge(source_nodes=(f"S{i}",), target_nodes=(f"T{i}",), weight=1.0)
        for i in range(5)
    ]
    _, issues = adapter.validate_and_normalize(edges)
    count_issues = [i for i in issues if i.field == "hyperedge_count"]
    assert len(count_issues) == 1
    assert count_issues[0].issue_type == "error"


def test_declared_units_validation():
    config = HypergraphValidationConfig(require_units=True)
    adapter = HypergraphFeatureAdapter(config=config)
    bad_unit_record = {
        "sources": ["A"],
        "targets": ["B"],
        "weight": 1.0,
        "declared_units": "invalid_magic_metric",
    }
    norm, issues = adapter.validate_and_normalize([bad_unit_record])
    unit_issues = [i for i in issues if "declared_units" in i.field]
    assert len(unit_issues) == 1


def test_strict_causal_language_guardrail():
    adapter = HypergraphFeatureAdapter()
    causal_record = {
        "sources": ["A"],
        "targets": ["B"],
        "weight": 1.0,
        "provenance": "proves causation across nodes",
    }
    norm, issues = adapter.validate_and_normalize(
        [causal_record], causal_design_metadata=None
    )
    causal_issues = [i for i in issues if "causal_guardrail" in i.field]
    assert len(causal_issues) == 1
    assert "proves causation" in causal_issues[0].message


def test_deterministic_output_order():
    adapter = HypergraphFeatureAdapter()
    e1 = DirectedHyperedge(source_nodes=("A",), target_nodes=("B",), weight=1.0)
    e2 = DirectedHyperedge(source_nodes=("C",), target_nodes=("D",), weight=2.5)

    p1 = adapter.build_feature_payload([e1, e2], run_null_controls=False)
    p2 = adapter.build_feature_payload([e2, e1], run_null_controls=False)

    assert p1.deterministic_checksum == p2.deterministic_checksum
    assert p1.features == p2.features
    assert [e.canonical_key() for e in p1.normalized_hyperedges] == [
        "(C)->(D)",
        "(A)->(B)",
    ]


def test_node_reordering_invariance():
    adapter = HypergraphFeatureAdapter()
    e1 = DirectedHyperedge(source_nodes=("A", "B"), target_nodes=("C",), weight=2.0)
    e2 = DirectedHyperedge(source_nodes=("C",), target_nodes=("D",), weight=1.5)

    # Relabeled node identifiers
    e1_perm = DirectedHyperedge(source_nodes=("X", "Y"), target_nodes=("Z",), weight=2.0)
    e2_perm = DirectedHyperedge(source_nodes=("Z",), target_nodes=("W",), weight=1.5)

    p_orig = adapter.build_feature_payload([e1, e2], run_null_controls=False)
    p_perm = adapter.build_feature_payload([e1_perm, e2_perm], run_null_controls=False)

    # Invariant features must match identically
    for key in [
        "transition.hyperedge_count",
        "transition.hyperedge_order_mean",
        "transition.hyperedge_order_max",
        "transition.source_target_asymmetry",
        "transition.mean_transition_influence",
        "transition.max_transition_influence",
    ]:
        assert p_orig.features[key] == p_perm.features[key]


def test_missing_context_handling():
    adapter = HypergraphFeatureAdapter()
    edge = DirectedHyperedge(source_nodes=("A",), target_nodes=("B",), weight=1.8, context_variables=None)
    payload = adapter.build_feature_payload([edge], run_null_controls=False)

    assert payload.features["transition.context_conditioned_score"] == 1.8
    assert payload.normalized_hyperedges[0].context_variables is None


def test_synthetic_status_propagation():
    adapter = HypergraphFeatureAdapter()
    edge_synth = DirectedHyperedge(source_nodes=("A",), target_nodes=("B",), weight=1.0, synthetic=True)
    payload = adapter.build_feature_payload([edge_synth], synthetic=True, evidence_class="L1_synthetic")

    assert payload.synthetic is True
    assert payload.evidence_class == "L1_synthetic"
    assert payload.normalized_hyperedges[0].synthetic is True


def test_mathematical_separation_from_topology():
    adapter = HypergraphFeatureAdapter()
    payload = adapter.build_feature_payload(_build_sample_edges(), run_null_controls=False)

    assert "ordinary_graph_cycles" in payload.distinct_from_topology
    assert "beta_1_persistence" in payload.distinct_from_topology
    assert "spatial_phase_winding" in payload.distinct_from_topology
    # Features must not encode beta1 or spatial charge
    for feat_name in payload.features.keys():
        assert "beta_1" not in feat_name
        assert "spatial_charge" not in feat_name


def test_canonical_feature_names_validity():
    adapter = HypergraphFeatureAdapter()
    payload = adapter.build_feature_payload(_build_sample_edges(), run_null_controls=False)

    for feat_name in payload.features.keys():
        validate_feature_name(feat_name)


def test_all_four_null_controls_execute():
    adapter = HypergraphFeatureAdapter()
    edges = [
        DirectedHyperedge(source_nodes=("A", "B"), target_nodes=("C",), weight=2.0, window=(0.0, 1.0)),
        DirectedHyperedge(source_nodes=("B",), target_nodes=("D",), weight=1.5, window=(1.0, 2.0)),
        DirectedHyperedge(source_nodes=("C", "D"), target_nodes=("E",), weight=3.0, window=(2.0, 3.5)),
    ]
    nc = adapter.evaluate_null_controls(
        [adapter.normalize_hyperedge(e) for e in edges], num_permutations=20
    )
    # 1. Label permutation
    assert nc.label_permutation_z_score is not None
    # 2. Temporal block shift
    assert nc.temporal_block_shift_preserved_ratio == 1.0
    # 3. Common driver
    assert nc.common_driver_confounding_fraction is not None
    # 4. Matched variance
    assert nc.matched_variance_z_score is not None


def test_strict_finite_json_serialization():
    adapter = HypergraphFeatureAdapter()
    payload = adapter.build_feature_payload(_build_sample_edges(), run_null_controls=True)

    json_str = payload.to_json()
    # Must parse cleanly with json.loads and not contain NaN/Infinity
    data = json.loads(json_str)
    assert data["schema_version"] == "1.0.0"
    assert data["is_valid"] is True
    assert "features" in data
    assert "normalized_hyperedges" in data


def test_no_network_operation(monkeypatch):
    def forbidden_socket(*args, **kwargs):
        raise RuntimeError("Forbidden network call")

    monkeypatch.setattr(socket, "create_connection", forbidden_socket)
    adapter = HypergraphFeatureAdapter()
    payload = adapter.build_feature_payload(_build_sample_edges(), run_null_controls=True)
    assert payload.is_valid is True


def test_cli_runner_execution():
    repo_root = Path(__file__).resolve().parent.parent.parent
    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "validate_hypergraph_feature_contract.py"),
        "--strict",
        "--format",
        "json",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data["is_valid"] is True
    assert data["schema_version"] == "1.0.0"
