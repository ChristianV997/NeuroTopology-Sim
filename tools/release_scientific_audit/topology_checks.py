"""Audit check 8: graph beta_1 vs. spatial winding/charge vs. scalar
chirality must remain distinct, non-collapsible namespaces in whatever
report documents describe them."""
from __future__ import annotations

from typing import List

from .models import Finding, TopologySummary

KNOWN_NAMESPACES: frozenset[str] = frozenset({"spatial_topology", "graph_topology", "scalar_chirality"})

# Bare field names that must never appear outside a namespaced summary --
# their presence at the top level (or duplicated verbatim across two
# different namespaces) is exactly the collapse this check exists to catch.
RESERVED_FIELD_NAMES: frozenset[str] = frozenset({
    "winding_number", "topological_charge", "beta1_loops", "beta_1", "beta1", "Qz", "Qabs",
})


def check_topology_namespace_separation(summaries: tuple) -> List[Finding]:
    findings: List[Finding] = []
    if not summaries:
        findings.append(Finding(
            "topology_namespace_separation", "warning",
            "no topology summaries supplied to this audit",
            "topology_summaries (empty)",
        ))
        return findings

    seen_namespaces: dict[str, TopologySummary] = {}
    for summary in summaries:
        summary: TopologySummary
        if summary.namespace not in KNOWN_NAMESPACES:
            findings.append(Finding(
                "topology_namespace_separation", "warning",
                f"unrecognized topology namespace {summary.namespace!r}",
                f"topology_summaries[{summary.namespace}]",
            ))
            continue
        if summary.namespace in seen_namespaces:
            findings.append(Finding(
                "topology_namespace_separation", "blocking",
                f"namespace {summary.namespace!r} reported more than once -- exactly one summary "
                "per namespace is expected",
                f"topology_summaries[{summary.namespace}]",
            ))
        seen_namespaces[summary.namespace] = summary

    # Cross-namespace field collision: the same field name reported under
    # two DIFFERENT namespaces with different values is the real collapse
    # risk (a graph beta_1 count being confused for a scalar-chirality
    # beta1_loops proxy, etc.).
    field_owners: dict[str, list[str]] = {}
    for namespace, summary in seen_namespaces.items():
        for field_name in summary.fields:
            field_owners.setdefault(field_name, []).append(namespace)
    for field_name, owners in field_owners.items():
        if len(owners) > 1:
            findings.append(Finding(
                "topology_namespace_separation", "blocking",
                f"field {field_name!r} appears in multiple topology namespaces: {sorted(owners)} -- "
                "graph beta_1, spatial winding/charge, and scalar chirality must stay distinct",
                f"topology_summaries[{sorted(owners)}].{field_name}",
            ))

    if "graph_topology" in seen_namespaces and "spatial_topology" in seen_namespaces:
        findings.append(Finding(
            "topology_namespace_separation", "info",
            "graph_topology and spatial_topology are both present and reported under separate namespaces",
            "topology_summaries",
        ))
    return findings
