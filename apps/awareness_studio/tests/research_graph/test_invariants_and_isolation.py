"""Tests for invariants, determinism, JSON finiteness, network isolation, and lightweight imports."""
from __future__ import annotations

import json
import math
import socket
import subprocess
import sys
from pathlib import Path
import pytest

from awareness_studio.research_graph import (
    EvidenceGraphBuilder,
    GraphNode,
    NodeType,
    load_from_dict,
    to_json,
    to_markdown,
)
from scripts.build_awareness_evidence_graph import main as cli_main


def test_deterministic_repeat(complete_manifest_data: dict):
    """Verify that building from the same manifest repeatedly yields byte-for-byte identical output."""
    graph1 = load_from_dict(complete_manifest_data)
    graph2 = load_from_dict(complete_manifest_data)

    json1 = to_json(graph1)
    json2 = to_json(graph2)
    assert json1 == json2

    md1 = to_markdown(graph1)
    md2 = to_markdown(graph2)
    assert md1 == md2

    assert graph1.summary.graph_checksum == graph2.summary.graph_checksum


def test_finite_json_rfc8259_enforcement():
    """Verify that non-finite floats (NaN, Inf) are sanitized and do not violate RFC-8259."""
    builder = EvidenceGraphBuilder()
    builder.add_node(
        GraphNode(
            node_id="hyp-nan-test",
            node_type=NodeType.HYPOTHESIS.value,
            label="Hypothesis with non-finite values",
            properties={
                "nan_metric": float("nan"),
                "inf_metric": float("inf"),
                "neg_inf": float("-inf"),
                "valid_float": 0.42,
            },
        )
    )
    graph = builder.build()
    json_output = to_json(graph)

    # Must be valid parseable JSON with allow_nan=False
    parsed = json.loads(json_output)
    node_props = parsed["nodes"][0]["properties"]
    assert node_props["nan_metric"] is None
    assert node_props["inf_metric"] is None
    assert node_props["neg_inf"] is None
    assert node_props["valid_float"] == 0.42


def test_no_network_access(monkeypatch, complete_manifest_data: dict):
    """Verify that the subsystem performs no socket/network calls during graph building."""
    def guarded_socket(*args, **kwargs):
        raise RuntimeError("Forbidden network socket access in evidence graph projection!")

    monkeypatch.setattr(socket, "socket", guarded_socket)

    # Building graph, diagnostics, and serializing must not trigger network calls
    graph = load_from_dict(complete_manifest_data)
    assert len(graph.nodes) > 0
    _ = to_json(graph)
    _ = to_markdown(graph)


def test_no_heavy_imports():
    """Verify that awareness_studio.research_graph does not import heavyweight scientific/solver packages."""
    heavy_modules = ("torch", "scipy", "numpy", "cvxpy", "networkx", "z3", "sympy")
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import awareness_studio.research_graph; "
            "mods=('torch','scipy','numpy','cvxpy','networkx','z3','sympy'); "
            "found=','.join(m for m in mods if m in sys.modules); "
            "print(found, end=''); raise SystemExit(1 if found else 0)",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.returncode == 0, f"Heavy module(s) imported by research_graph: {probe.returncode} {probe.stderr}"
    assert not probe.stdout.strip(), f"Heavy module(s) imported by research_graph: {probe.stdout.strip()}"


def test_cli_end_to_end(tmp_path: Path, complete_manifest_data: dict):
    """Verify CLI tool execution, output files, and strict flag behavior."""
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(json.dumps(complete_manifest_data), encoding="utf-8")

    out_json = tmp_path / "graph.json"
    out_md = tmp_path / "report.md"
    out_summary = tmp_path / "summary.json"

    exit_code = cli_main([
        "--manifest", str(manifest_file),
        "--output-json", str(out_json),
        "--output-md", str(out_md),
        "--output-summary", str(out_summary),
        "--strict",
    ])
    assert exit_code == 0
    assert out_json.exists()
    assert out_md.exists()
    assert out_summary.exists()

    # Validate generated JSON content
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert "nodes" in data
    assert "edges" in data
    assert "summary" in data
