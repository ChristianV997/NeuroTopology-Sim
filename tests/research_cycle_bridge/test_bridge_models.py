"""Unit tests for Research Cycle Bridge models and finite JSON serialization."""
from __future__ import annotations

import json
import pytest

from tools.research_cycle_bridge.models import (
    BRIDGE_SCHEMA_VERSION,
    EVIDENCE_GRAPH_SCHEMA,
    BridgeContractError,
    BridgeDataMode,
    BridgeEvidenceClass,
    BridgeRecordStatus,
    EvidenceGraph,
    EvidenceGraphEdge,
    EvidenceGraphNode,
    ResearchCycleBridgeRecord,
    canonical_hash,
    dumps_finite,
    finite_value,
    verify_bridge_checksum,
)


def test_finite_value_primitives_and_null_preservation() -> None:
    """Ensure primitives serialize correctly and nulls are strictly preserved (not zero-filled)."""
    assert finite_value(None) is None
    assert finite_value(True) is True
    assert finite_value(False) is False
    assert finite_value(0) == 0
    assert finite_value(123) == 123
    assert finite_value(3.14159) == 3.14159
    assert finite_value("hello") == "hello"

    # Nested mapping with nulls
    d = {"metric_a": None, "metric_b": 0.5, "flag": False}
    safe_d = finite_value(d)
    assert safe_d["metric_a"] is None
    assert safe_d["metric_b"] == 0.5
    assert safe_d["flag"] is False


def test_finite_value_rejects_nan_and_infinity() -> None:
    """Ensure non-finite floating point tokens raise BridgeContractError."""
    with pytest.raises(BridgeContractError, match="non-finite value"):
        finite_value(float("nan"))

    with pytest.raises(BridgeContractError, match="non-finite value"):
        finite_value(float("inf"))

    with pytest.raises(BridgeContractError, match="non-finite value"):
        finite_value({"metric": [1.0, float("-inf")]})


def test_dumps_finite_formatting() -> None:
    """Ensure dumps_finite produces sorted, indented JSON ending in newline."""
    data = {"b": 2, "a": 1, "c": None}
    out = dumps_finite(data)
    assert out.endswith("\n")
    # Verify key order
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    assert lines[1].startswith('"a"')
    assert lines[2].startswith('"b"')
    assert lines[3].startswith('"c": null')


def test_canonical_hash_determinism() -> None:
    """Ensure canonical_hash produces identical SHA-256 irrespective of key insertion order."""
    dict1 = {"x": 1, "y": 2, "z": None}
    dict2 = {"z": None, "y": 2, "x": 1}
    assert canonical_hash(dict1) == canonical_hash(dict2)
    assert len(canonical_hash(dict1)) == 64


def test_evidence_graph_structure() -> None:
    """Ensure EvidenceGraph produces canonical structure with computed checksum."""
    nodes = [
        EvidenceGraphNode(id="node1", stage="source_dataset", data_mode="synthetic"),
        EvidenceGraphNode(id="node2", stage="simulation_run", data_mode="synthetic"),
    ]
    edges = [
        EvidenceGraphEdge(source="node2", target="node1", relationship="executes"),
    ]
    graph = EvidenceGraph(graph_id="test_graph", nodes=nodes, edges=edges)
    d = graph.to_dict()
    assert d["schema_version"] == EVIDENCE_GRAPH_SCHEMA
    assert d["graph_id"] == "test_graph"
    assert len(d["nodes"]) == 2
    assert len(d["edges"]) == 1
    assert d["checksum"] != ""


def test_bridge_record_checksum_verification() -> None:
    """Ensure ResearchCycleBridgeRecord computes and verifies its SHA-256 digest."""
    rec = ResearchCycleBridgeRecord(
        record_id="bridge-test-001",
        cycle_id="rc-cycle-001",
        dataset_id="ds005620",
        data_mode=BridgeDataMode.EMPIRICAL.value,
        status=BridgeRecordStatus.COMPLETE.value,
        evidence_class=BridgeEvidenceClass.EMPIRICAL_DATASET.value,
        synthetic=False,
        proxy=False,
        empirical=True,
        provenance={"run_id": "run-001", "created_at": "2026-09-11T00:00:00Z", "source": "local"},
    )
    d = rec.to_dict()
    assert d["checksum"] != ""
    assert verify_bridge_checksum(d) is True

    # Tampering with payload invalidates checksum
    d["status"] = BridgeRecordStatus.FAILED.value
    assert verify_bridge_checksum(d) is False
