"""CLI: validate the Awareness Studio research-cycle orchestrator's input
contract against fixtures shaped like the real upstream registries
(literature registry, PR #276; hypothesis/experiment registry,
already-merged tools/research_cycle).

Reads exactly the four files named on the command line (each defaults to
the bundled representative fixture under
fixtures/awareness_studio_research_loop/integration_contracts/ so this
runs standalone with no arguments) and writes one JSON diagnostics report.
No network access; no import of the upstream packages themselves --
everything is consumed as data via tools.awareness_studio_research_loop.contract_adapters.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.awareness_studio_research_loop import contract_adapters as ca  # noqa: E402

_FIXTURES_DIR = _REPO_ROOT / "fixtures" / "awareness_studio_research_loop" / "integration_contracts"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--literature-export", type=Path, default=_FIXTURES_DIR / "literature_registry_export_sample.json")
    parser.add_argument("--hypothesis-registry", type=Path, default=_FIXTURES_DIR / "hypothesis_registry_sample.json")
    parser.add_argument("--experiment-plans", type=Path, default=_FIXTURES_DIR / "experiment_plans_sample.json")
    parser.add_argument("--experiment-evidence-updates", type=Path, default=_FIXTURES_DIR / "experiment_evidence_updates_sample.json")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--now", default=None, help="ISO-8601 timestamp to stamp the report with (default: current UTC time).")
    return parser.parse_args(argv)


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def main(argv: list[str] | None = None) -> int:
    from datetime import datetime, timezone

    args = parse_args(argv)
    generated_at = args.now if args.now is not None else datetime.now(timezone.utc).isoformat()

    literature_raw = _load_json(args.literature_export)
    hypothesis_raw = _load_json(args.hypothesis_registry)
    plans_raw = _load_json(args.experiment_plans)
    updates_raw = _load_json(args.experiment_evidence_updates)

    lit_bundle, lit_diagnostics = ca.adapt_literature_evidence_bundle(literature_raw)
    hyp_bundle, hyp_diagnostics = ca.adapt_hypothesis_registry_bundle(hypothesis_raw)

    plan_diagnostics = []
    adapted_plans = []
    for raw_plan in plans_raw.get("plans", []) if isinstance(plans_raw.get("plans"), list) else []:
        result = ca.adapt_experiment_plan(raw_plan)
        plan_diagnostics.extend(result.diagnostics)
        if result.ok:
            adapted_plans.append(result.record)

    evidence_update_diagnostics = []
    adapted_executions, adapted_null_tests, contradictions = [], [], []
    for raw_update in updates_raw.get("evidence_updates", []) if isinstance(updates_raw.get("evidence_updates"), list) else []:
        execution_result, null_test, contradiction = ca.adapt_experiment_evidence_update(raw_update)
        evidence_update_diagnostics.extend(execution_result.diagnostics)
        if execution_result.ok:
            adapted_executions.append(execution_result.record)
        if null_test is not None:
            adapted_null_tests.append(null_test)
        if contradiction is not None:
            contradictions.append(contradiction)

    known_hypothesis_ids = {h["hypothesis_id"] for h in hyp_bundle["hypotheses"]}
    cross_diagnostics = ca.validate_cross_registry_hypothesis_links(claims=lit_bundle["claims"], hypothesis_links=lit_bundle["hypothesis_links"], known_hypothesis_ids=known_hypothesis_ids)

    all_diagnostics = lit_diagnostics + hyp_diagnostics + plan_diagnostics + evidence_update_diagnostics + cross_diagnostics
    diagnostics_by_kind = {kind: sum(1 for d in all_diagnostics if d.kind == kind) for kind in sorted(ca.DIAGNOSTIC_KINDS)}

    report = {
        "generated_at": generated_at,
        "sources_read": {
            "literature_export": str(args.literature_export),
            "hypothesis_registry": str(args.hypothesis_registry),
            "experiment_plans": str(args.experiment_plans),
            "experiment_evidence_updates": str(args.experiment_evidence_updates),
        },
        "adapted": {
            "literature_evidence": lit_bundle,
            "hypothesis_registry": hyp_bundle,
            "experiment_plans": adapted_plans,
            "executions_from_evidence_updates": adapted_executions,
            "null_tests_from_evidence_updates": adapted_null_tests,
            "contradictions_from_evidence_updates": contradictions,
        },
        "diagnostics": [d.to_dict() for d in all_diagnostics],
        "diagnostics_by_kind": diagnostics_by_kind,
        "never_coerce_guards": list(ca.NEVER_COERCE),
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "contract_integration_report.json").write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")

    print(f"diagnostics={len(all_diagnostics)} by_kind={diagnostics_by_kind}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
