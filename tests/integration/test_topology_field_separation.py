"""Dedicated test for the "graph beta_1 and spatial winding must remain
separate" guardrail, exercised through the real assembled pipeline output
(not just the quality_gate unit checks in test_quality_gate.py)."""
from __future__ import annotations

from pathlib import Path

from scripts.assemble_ecosystem_run import assemble


def test_assembled_analysis_keeps_spatial_and_chirality_namespaces_apart(tmp_path):
    result = assemble(
        data_mode="synthetic", input_path=None, output_dir=tmp_path / "out",
        seed=13, dataset_id="namespace-check",
    )
    import json

    record = json.loads(Path(result["artifacts"]["run_record"]).read_text())
    analysis = record["metrics"]["analysis"]

    # graph_topology (real persistent-homology beta_1) is only present when
    # ripser is installed (it is not, in this sandbox) -- but whichever
    # namespaces ARE present must never share keys with each other, and
    # none of the reserved bare names may appear at the top level of the
    # analysis dict.
    forbidden_top_level = {"winding_number", "topological_charge", "beta1_loops", "beta_1", "beta1", "Qz", "Qabs"}
    assert forbidden_top_level.isdisjoint(analysis.keys())

    namespaces_present = [ns for ns in ("spatial_topology", "graph_topology", "scalar_chirality") if ns in analysis]
    assert namespaces_present, "expected at least one topology namespace in a synthetic run's analysis"
    for namespace in namespaces_present:
        assert isinstance(analysis[namespace], dict)

    if "spatial_topology" in analysis and "graph_topology" in analysis:
        assert set(analysis["spatial_topology"]).isdisjoint(analysis["graph_topology"])
    if "spatial_topology" in analysis and "scalar_chirality" in analysis:
        assert set(analysis["spatial_topology"]).isdisjoint(analysis["scalar_chirality"])
