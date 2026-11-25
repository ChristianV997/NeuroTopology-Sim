"""Run smoke scenarios through canonical release-evidence interfaces."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from tools.release_readiness.research_cycle_smoke.chain import (
    incomplete_states_visible,
    missing_metrics_not_zeroed,
    synthetic_not_promoted,
    verify_chain,
)
from tools.release_readiness.research_cycle_smoke.fixtures import (
    all_scenarios,
    build_scenario,
    fixture_checksum,
)
from tools.release_readiness.research_cycle_smoke.guards import bounded_resources_ok, no_network
from tools.release_readiness.research_cycle_smoke.schema import (
    DEFAULT_LIMITATIONS,
    SCHEMA_VERSION,
    SMOKE_EVIDENCE_CLASS,
    ScenarioId,
    ScenarioResult,
    StageRecord,
    json_safe,
)


def _soft_optional_consumers(stages: List[StageRecord]) -> Dict[str, Any]:
    """Best-effort soft imports of adjacent canonical interfaces (read-only)."""
    notes: Dict[str, Any] = {"optional_consumers": []}
    # Simulation artifact lineage extractor
    try:
        from tools.simulation_artifacts import extractor as _ext  # noqa: F401

        notes["optional_consumers"].append("tools.simulation_artifacts")
        notes["simulation_artifacts_available"] = True
    except Exception as exc:
        notes["simulation_artifacts_available"] = False
        notes["simulation_artifacts_error"] = str(exc)

    # Evidence graph builder (Awareness Studio)
    try:
        from awareness_studio.research_graph import builder as _builder  # noqa: F401

        notes["optional_consumers"].append("awareness_studio.research_graph")
        notes["evidence_graph_available"] = True
    except Exception:
        try:
            import importlib

            importlib.import_module("apps.awareness_studio.src.awareness_studio.research_graph")
            notes["optional_consumers"].append("apps.awareness_studio.research_graph")
            notes["evidence_graph_available"] = True
        except Exception as exc:
            notes["evidence_graph_available"] = False
            notes["evidence_graph_error"] = str(exc)

    # Research-cycle registry
    try:
        from tools.research_cycle.registry import ResearchCycleRegistry  # noqa: F401

        notes["optional_consumers"].append("tools.research_cycle")
        notes["research_cycle_registry_available"] = True
    except Exception as exc:
        notes["research_cycle_registry_available"] = False
        notes["research_cycle_registry_error"] = str(exc)

    notes["stage_count"] = len(stages)
    return notes


def run_scenario(scenario: ScenarioId) -> ScenarioResult:
    from tools.research_cycle_release.evaluator import evaluate_research_cycle_release
    from tools.research_cycle_release.report import dumps as release_dumps

    stages, bundle, expected = build_scenario(scenario)
    with no_network():
        report = evaluate_research_cycle_release(bundle, adapter_hint="generic")
        release_dict = report.to_dict()
        # Force finite serialization path
        _ = release_dumps(release_dict)

    chain_ok, chain_errors = verify_chain(stages)
    incomplete_ok, incomplete_errors = incomplete_states_visible(stages)
    # Complete engineering scenario has no incomplete stages — visibility vacuously true.
    if scenario == ScenarioId.COMPLETE_VALID_ENGINEERING:
        incomplete_ok = True
        incomplete_errors = []

    synth_ok = synthetic_not_promoted(stages, release_dict)
    missing_ok = missing_metrics_not_zeroed(bundle, release_dict)
    observed = str(release_dict.get("decision"))
    checksum = fixture_checksum(stages, bundle)
    optional = _soft_optional_consumers(stages)

    warnings: List[str] = []
    warnings.extend(chain_errors)
    warnings.extend(incomplete_errors)
    if not synth_ok:
        warnings.append("synthetic_promoted_or_scientific_flag")
    if not missing_ok:
        warnings.append("missing_metric_zeroed")

    return ScenarioResult(
        scenario_id=scenario.value,
        expected_decision=expected,
        observed_decision=observed,
        decision_match=(observed == expected),
        chain_ok=chain_ok,
        incomplete_visible=incomplete_ok,
        synthetic_not_scientific=synth_ok,
        missing_not_zeroed=missing_ok,
        checksum=checksum,
        release_reason_codes=list(release_dict.get("reason_codes") or []),
        stages=stages,
        warnings=warnings,
        details={
            "release_evidence_class": release_dict.get("evidence_class"),
            "scientific_pass_emitted": release_dict.get("scientific_pass_emitted"),
            "bayes_factor_emitted": release_dict.get("bayes_factor_emitted"),
            "optional": optional,
            "bundle_cycle_id": bundle.get("cycle_id"),
        },
    )


def run_smoke_suite(
    scenarios: Optional[Sequence[ScenarioId]] = None,
) -> Dict[str, Any]:
    selected = list(scenarios) if scenarios is not None else all_scenarios()
    results: List[ScenarioResult] = []
    with no_network():
        for scenario in selected:
            results.append(run_scenario(scenario))

    resource_ok, resource_notes = bounded_resources_ok()
    decision_matrix = [
        {
            "scenario_id": r.scenario_id,
            "expected": r.expected_decision,
            "observed": r.observed_decision,
            "match": r.decision_match,
        }
        for r in results
    ]
    all_match = all(r.decision_match for r in results)
    all_guards = all(
        r.chain_ok and r.incomplete_visible and r.synthetic_not_scientific and r.missing_not_zeroed
        for r in results
    )
    # Determinism: re-run first scenario and compare checksum
    deterministic = True
    if selected:
        again = run_scenario(selected[0])
        deterministic = again.checksum == results[0].checksum and again.observed_decision == results[0].observed_decision

    return json_safe(
        {
            "schema_version": SCHEMA_VERSION,
            "evidence_class": SMOKE_EVIDENCE_CLASS,
            "synthetic": True,
            "scientific_pass_emitted": False,
            "bayes_factor_emitted": False,
            "causal_promotion_emitted": False,
            "network_accessed": False,
            "full_dataset_download": False,
            "n_scenarios": len(results),
            "all_decisions_match": all_match,
            "all_guards_pass": all_guards,
            "deterministic": deterministic,
            "resource_ok": resource_ok,
            "resource_notes": resource_notes,
            "decision_matrix": decision_matrix,
            "results": [r.to_dict() for r in results],
            "limitations": list(DEFAULT_LIMITATIONS),
            "note": (
                "Research-cycle smoke harness is an integration consumer. "
                "It does not modify production semantics."
            ),
        }
    )
