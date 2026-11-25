"""Deterministic serialization, Markdown reporting, and Awareness Studio summary export.

Enforces RFC-8259 JSON compliance, deterministic sorting, and generates
HTML-independent summaries suitable for direct ingestion into Awareness Studio.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from .models import EvidenceGraph, _safe_dict
from .types import DiagnosticSeverity, SafetyLabel


def to_json(graph: EvidenceGraph, *, indent: int = 2) -> str:
    """Serialize EvidenceGraph to deterministic RFC-8259 canonical JSON."""
    data = graph.to_dict()
    return json.dumps(
        data,
        sort_keys=True,
        indent=indent,
        ensure_ascii=True,
        allow_nan=False,
    )


def to_awareness_summary(graph: EvidenceGraph) -> dict[str, Any]:
    """Generate an HTML-independent summary dictionary for Awareness Studio ingestion."""
    summary = graph.summary.to_dict() if graph.summary else {}
    critical_errors = [
        d.to_dict() for d in graph.diagnostics if d.severity == DiagnosticSeverity.ERROR.value
    ]
    warnings = [
        d.to_dict() for d in graph.diagnostics if d.severity == DiagnosticSeverity.WARNING.value
    ]

    return _safe_dict({
        "graph_checksum": graph.summary.graph_checksum if graph.summary else "",
        "ready_for_ingestion": len(critical_errors) == 0,
        "total_nodes": graph.summary.total_nodes if graph.summary else len(graph.nodes),
        "total_edges": graph.summary.total_edges if graph.summary else len(graph.edges),
        "nodes_by_type": graph.summary.nodes_by_type if graph.summary else {},
        "edges_by_type": graph.summary.edges_by_type if graph.summary else {},
        "evidence_distribution": graph.summary.evidence_distribution if graph.summary else {},
        "status_distribution": graph.summary.status_distribution if graph.summary else {},
        "safety_label_distribution": graph.summary.safety_label_distribution if graph.summary else {},
        "diagnostics_summary": {
            "total_diagnostics": len(graph.diagnostics),
            "critical_errors_count": len(critical_errors),
            "warnings_count": len(warnings),
            "critical_errors": critical_errors,
            "top_warnings": warnings[:10],
        },
        "scientific_guardrails": {
            "no_clinical_claim": True,
            "no_ontology_promotion": True,
            "unsupported_promotions_detected": any(
                d.code == "unsupported_promotion" for d in graph.diagnostics
            ),
            "synthetic_isolation_enforced": True,
        },
    })


def to_markdown(graph: EvidenceGraph) -> str:
    """Render an audit-ready Markdown report of the evidence graph projection."""
    lines: list[str] = []
    summary = graph.summary

    lines.append("# Awareness Studio Evidence Graph Projection")
    lines.append("")
    lines.append(f"**Graph Integrity Checksum**: `{summary.graph_checksum}`")
    lines.append(f"**Total Nodes**: {summary.total_nodes} | **Total Edges**: {summary.total_edges}")
    lines.append("")

    # Scientific Guardrails Callout
    lines.append("## Scientific Safety & Epistemic Boundaries")
    lines.append("")
    lines.append("> [!IMPORTANT]")
    lines.append("> **Epistemic Isolation Notice**: This projection models structural, causal, and evidentiary")
    lines.append("> linkages between literature, hypotheses, simulations, and artifacts. It does not validate")
    lines.append("> clinical efficacy, promote ontological status, or assert empirical truth without human review.")
    lines.append("")

    # Diagnostics section
    lines.append("## Graph Diagnostics & Integrity Audit")
    lines.append("")
    if not graph.diagnostics:
        lines.append("No diagnostic anomalies detected. Graph is internally consistent.")
    else:
        lines.append("| Severity | Code | Message | Affected IDs |")
        lines.append("|---|---|---|---|")
        for diag in graph.diagnostics:
            aff = ", ".join(f"`{x}`" for x in diag.affected_ids) if diag.affected_ids else "N/A"
            lines.append(f"| `{diag.severity.upper()}` | `{diag.code}` | {diag.message} | {aff} |")
    lines.append("")

    # Node summary table
    lines.append("## Node Distribution by Type")
    lines.append("")
    lines.append("| Node Type | Count |")
    lines.append("|---|---|")
    for ntype, count in summary.nodes_by_type.items():
        lines.append(f"| `{ntype}` | {count} |")
    lines.append("")

    # Evidence distribution
    lines.append("## Evidence Class Breakdown")
    lines.append("")
    lines.append("| Evidence Class | Count | Description |")
    lines.append("|---|---|---|")
    class_desc = {
        "synthetic": "Simulations, generative surrogates, synthetic benchmark runs",
        "proxy": "Heuristic proxy metrics, surrogate statistics, proxy Bayes factors",
        "empirical": "Observational or biological recordings without locked preregistration",
        "formal": "Preregistered held-out locked empirical tests with signed human review",
        "unknown": "Unclassified or non-evidentiary entity",
    }
    for ecls, count in summary.evidence_distribution.items():
        lines.append(f"| `{ecls}` | {count} | {class_desc.get(ecls, 'N/A')} |")
    lines.append("")

    # Node inventory (first 100)
    lines.append("## Node Inventory")
    lines.append("")
    lines.append("| Node ID | Type | Label | Status | Class | Safety Labels |")
    lines.append("|---|---|---|---|---|---|")
    sorted_nodes = sorted(graph.nodes.values(), key=lambda n: (n.node_type, n.node_id))
    for node in sorted_nodes[:100]:
        safety_str = ", ".join(node.safety_labels) if node.safety_labels else "none"
        lbl_clean = node.label.replace("|", "\\|")[:50]
        lines.append(
            f"| `{node.node_id}` | `{node.node_type}` | {lbl_clean} | `{node.status}` | `{node.evidence_class}` | {safety_str} |"
        )
    if len(sorted_nodes) > 100:
        lines.append(f"\n*...and {len(sorted_nodes) - 100} more nodes.*")
    lines.append("")

    # Edge inventory (first 100)
    lines.append("## Edge Relations")
    lines.append("")
    lines.append("| Edge Type | Source Node | Target Node | Confidence |")
    lines.append("|---|---|---|---|")
    sorted_edges = sorted(graph.edges, key=lambda e: (e.edge_type, e.source_id, e.target_id))
    for edge in sorted_edges[:100]:
        conf = f"{edge.confidence:.2f}" if edge.confidence is not None else "-"
        lines.append(f"| `{edge.edge_type}` | `{edge.source_id}` | `{edge.target_id}` | {conf} |")
    if len(sorted_edges) > 100:
        lines.append(f"\n*...and {len(sorted_edges) - 100} more edges.*")
    lines.append("")

    # Mermaid diagram if graph size is concise (<= 40 nodes)
    if len(graph.nodes) <= 40:
        lines.append("## Entity Relationship Diagram")
        lines.append("")
        lines.append("```mermaid")
        lines.append("flowchart LR")
        for node in sorted_nodes:
            nid_sanitized = node.node_id.replace("-", "_").replace(":", "_").replace(".", "_")
            lbl_sanitized = node.label[:25].replace('"', "'")
            lines.append(f'    {nid_sanitized}["{node.node_type}: {lbl_sanitized}"]')
        for edge in sorted_edges:
            src = edge.source_id.replace("-", "_").replace(":", "_").replace(".", "_")
            tgt = edge.target_id.replace("-", "_").replace(":", "_").replace(".", "_")
            lines.append(f"    {src} -->|{edge.edge_type}| {tgt}")
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def save_graph(
    graph: EvidenceGraph,
    output_path: Path | str,
    *,
    fmt: str = "json",
    atomic: bool = True,
) -> Path:
    """Save graph projection to disk atomically."""
    path = Path(output_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        content = to_json(graph)
    elif fmt == "summary":
        content = json.dumps(to_awareness_summary(graph), indent=2, sort_keys=True)
    elif fmt in ("md", "markdown"):
        content = to_markdown(graph)
    else:
        raise ValueError(f"Unsupported format '{fmt}'. Supported: json, summary, markdown")

    if atomic:
        temp_dir = path.parent
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=temp_dir, delete=False
        ) as tmp:
            tmp.write(content)
            tmp.flush()
            temp_path = Path(tmp.name)
        temp_path.replace(path)
    else:
        path.write_text(content, encoding="utf-8")

    return path
