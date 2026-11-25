"""Post-analysis validation and status normalization.

This is the one place in the integration layer that enforces the mission's
hard scientific guardrails on the *assembled* result:

  - synthetic data cannot produce an empirical PASS
  - invalid data becomes INCONCLUSIVE or ERROR, never a silent default
  - graph beta_1 and spatial winding/charge stay in clearly separate,
    non-collapsible namespaces
  - every packaged result carries complete provenance

It never re-implements a scientific computation — it only inspects and
(when required by a guardrail) relabels the *status* of an already-computed
result. It must not mutate the numeric fields a wrapped adapter returned.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

STATUS_VALUES: frozenset[str] = frozenset({"PASS", "NOT_SUPPORTED", "INCONCLUSIVE", "ERROR"})

SYNTHETIC_DATA_MODES: frozenset[str] = frozenset({"synthetic", "synthetic_demo"})

# Provenance fields every packaged RunRecordV1-bound result must carry.
REQUIRED_PROVENANCE_FIELDS: tuple[str, ...] = (
    "data_mode",
    "dataset_id",
    "source_kind",
    "seed",
)

# Namespaces that must never be merged into one flat key, per the
# "graph beta_1 and spatial winding must remain separate" guardrail. Each
# entry names the exact field this integration writes for that quantity so
# a downstream reader can tell, from the key name alone, which module and
# formula produced it (closing the ambiguity flagged in the prior
# independent scientific review of sim/pitnn/topological_invariants.py vs.
# core/topology.py vs. analysis/connectivity_topology.py).
TOPOLOGY_NAMESPACES: tuple[str, ...] = (
    "spatial_topology",     # core.topology: plaquette charge / Qz / Qabs / f_dress
    "graph_topology",       # analysis.connectivity_topology.compute_beta1 (real H1 persistent homology)
    "scalar_chirality",     # sim.pitnn.topological_invariants (winding_number / topological_charge / beta1_loops proxy)
)


@dataclass
class QualityReport:
    """QualityReport-compatible structure (mirrors this repo's existing
    `{"status": ..., "checks": {...}}`-shaped quality outputs, e.g.
    DevelopmentWorkflow's run_quality_checks results in other NTS/RDR
    sibling repos, kept schema-parallel deliberately)."""

    status: str
    checks: Dict[str, bool] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": "NTS.IntegrationQualityReport.v1",
            "status": self.status,
            "checks": dict(sorted(self.checks.items())),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def all_finite(values: Sequence[float]) -> bool:
    try:
        return all(math.isfinite(float(v)) for v in values)
    except (TypeError, ValueError):
        return False


def check_topology_namespace_separation(analysis_result: Dict[str, Any]) -> List[str]:
    """Fail if any two of the reserved topology namespaces were collapsed
    into a shared flat key, or if a namespace's payload leaked a bare
    ``winding_number``/``topological_charge``/``beta1_loops`` key at the
    *top level* of the assembled result instead of nested under its
    namespace."""
    errors: List[str] = []
    top_level_leaks = {"winding_number", "topological_charge", "beta1_loops", "Qz", "Qabs", "beta_1", "beta1"}
    leaked = top_level_leaks.intersection(analysis_result.keys())
    if leaked:
        errors.append(
            "topology fields must be nested under a namespace "
            f"({', '.join(TOPOLOGY_NAMESPACES)}), found at top level: {sorted(leaked)}"
        )
    present_namespaces = [ns for ns in TOPOLOGY_NAMESPACES if ns in analysis_result]
    for namespace in present_namespaces:
        payload = analysis_result.get(namespace)
        if not isinstance(payload, dict):
            errors.append(f"namespace '{namespace}' must be a dict, got {type(payload).__name__}")
    return errors


def check_provenance_completeness(provenance: Dict[str, Any]) -> List[str]:
    return [
        f"missing provenance field: {field_name}"
        for field_name in REQUIRED_PROVENANCE_FIELDS
        if provenance.get(field_name) in (None, "")
    ]


def classify_status(
    *,
    raw_status: Optional[str],
    data_mode: str,
    exception_occurred: bool,
    insufficient_data: bool,
) -> tuple[str, List[str]]:
    """Normalize any upstream adapter's native verdict string into the
    integration layer's fixed four-value enum, enforcing the two hard
    guardrails:

      - an exception during analysis -> ERROR (never silently swallowed
        into NOT_SUPPORTED)
      - explicitly insufficient/invalid input -> INCONCLUSIVE (never a
        default PASS or NOT_SUPPORTED)
      - a PASS computed from synthetic data is always downgraded and
        annotated -- it is never reported as unqualified empirical
        evidence, matching this repository's own scientific rule that
        synthetic data is never empirical evidence

    Returns (status, notes).
    """
    notes: List[str] = []

    if exception_occurred:
        return "ERROR", ["analysis raised an exception; classified as ERROR, not NOT_SUPPORTED"]

    if insufficient_data:
        return "INCONCLUSIVE", ["input data was insufficient or invalid for analysis"]

    if raw_status is None:
        return "INCONCLUSIVE", ["no verdict was produced by the underlying adapter"]

    # Translate known upstream vocabularies into the fixed enum without
    # touching the modules that produced them.
    normalized = raw_status
    if raw_status.startswith("FALSIFIED"):
        normalized = "NOT_SUPPORTED"
        notes.append(f"upstream verdict {raw_status!r} mapped to NOT_SUPPORTED")
    elif raw_status not in STATUS_VALUES:
        normalized = "INCONCLUSIVE"
        notes.append(f"unrecognized upstream verdict {raw_status!r} mapped to INCONCLUSIVE")

    if normalized == "PASS" and data_mode in SYNTHETIC_DATA_MODES:
        notes.append(
            "upstream verdict was PASS on synthetic data; downgraded to "
            "NOT_SUPPORTED because synthetic data can never constitute "
            "empirical evidence (hard guardrail)"
        )
        return "NOT_SUPPORTED", notes

    return normalized, notes


def evaluate(
    *,
    analysis_result: Dict[str, Any],
    provenance: Dict[str, Any],
    raw_status: Optional[str],
    exception_occurred: bool = False,
    insufficient_data: bool = False,
    numeric_fields: Optional[Sequence[float]] = None,
) -> tuple[str, QualityReport]:
    """Run every guardrail check and return (final_status, QualityReport)."""
    errors: List[str] = []
    warnings: List[str] = []
    checks: Dict[str, bool] = {}

    provenance_errors = check_provenance_completeness(provenance)
    checks["provenance_complete"] = not provenance_errors
    errors.extend(provenance_errors)

    namespace_errors = check_topology_namespace_separation(analysis_result)
    checks["topology_namespace_separated"] = not namespace_errors
    errors.extend(namespace_errors)

    if numeric_fields is not None:
        finite_ok = all_finite(numeric_fields)
        checks["all_numeric_fields_finite"] = finite_ok
        if not finite_ok:
            errors.append("one or more reported numeric fields is non-finite (NaN/inf)")
    else:
        checks["all_numeric_fields_finite"] = True

    data_mode = str(provenance.get("data_mode", ""))
    status, status_notes = classify_status(
        raw_status=raw_status,
        data_mode=data_mode,
        exception_occurred=exception_occurred,
        insufficient_data=insufficient_data,
    )
    warnings.extend(status_notes)

    # Structural defects in the assembled artifact itself (missing
    # provenance, a collapsed topology namespace, a non-finite reported
    # value) are an integration-packaging fault, not a statement about the
    # underlying science -- they always force ERROR, overriding whatever
    # verdict classify_status derived from the scientific result alone.
    if errors:
        status = "ERROR"
    checks["status_in_enum"] = status in STATUS_VALUES

    report = QualityReport(
        status=status,
        checks=checks,
        errors=errors,
        warnings=warnings,
    )
    return report.status, report
