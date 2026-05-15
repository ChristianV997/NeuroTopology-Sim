from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path when running as a script from tools/.
sys.path.insert(0, str(Path(__file__).parent.parent))

from sciencer_d.btc_icft.ontology.artifact_reader import summarize_ontology_for_packet

BANNED_PHRASES = (
    "proves consciousness",
    "consciousness proven",
    "soul proven",
    "afterlife proven",
    "liberation detected",
    "ontology solved",
    "ultimate reality",
    "q equals self",
    "q equals soul",
    "q_abs equals suffering",
    "f_dress equals karma",
    "sedated implies no_experience",
    "unresponsive implies unconscious",
    "topology proves liberation",
    "eeg proves consciousness",
)

_DEFAULT_ONTOLOGY_ROOT = "outputs/btc_icft/ds005620_ontology_evaluation_mock"


def _load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_report(
    root: Path,
    validation_summary: Path,
    contract_summary: Path,
    *,
    ontology_root: str | None = None,
) -> dict:
    failures: list[str] = []
    warnings: list[str] = []

    execution = _load_json(root / "ds005620_real_benchmark_execution.json") or {}
    stage_results = _load_json(root / "stage_results.json") or {}
    omega = _load_json(root / "omega_event.json") or {}
    validation = _load_json(validation_summary)
    contract = _load_json(contract_summary)
    p11_metrics = _load_json(root / "stage_outputs/p11_signal_mt/metrics_signal_mt.json")

    if validation is None:
        warnings.append(f"missing validation summary: {validation_summary}")
    if contract is None:
        warnings.append(f"missing contract summary: {contract_summary}")
    if p11_metrics is None:
        warnings.append("missing P11 metrics: stage_outputs/p11_signal_mt/metrics_signal_mt.json")

    checked_artifacts = []
    checked_stages = []
    contract_validated_artifacts = []

    if isinstance(validation, dict):
        checked_artifacts = list(validation.get("checked_artifacts", []))
        checked_stages = list(validation.get("checked_stages", []))
        failures.extend(list(validation.get("failures", [])))

    if isinstance(contract, dict):
        contract_validated_artifacts = list(contract.get("validated_artifacts", []))
        failures.extend(list(contract.get("failures", [])))

    stages = {s.get("stage_id"): s for s in stage_results.get("stages", []) if isinstance(s, dict)}

    # Ontology summary
    _ont_root = Path(ontology_root) if ontology_root else Path(_DEFAULT_ONTOLOGY_ROOT)
    ontology_summary = summarize_ontology_for_packet(_ont_root)
    if not ontology_summary["ontology_available"]:
        warnings.append("ontology_evaluation_missing")

    report = {
        "report_version": "p18.2-ci-evidence-v2",
        "dataset_id": execution.get("dataset_id", "DS005620"),
        "pipeline_id": "ds005620_real_benchmark_execution_mock",
        "artifact_root": str(root),
        "benchmark_completed": bool(execution.get("benchmark_completed", False)),
        "validation_ok": bool(validation.get("ok", False)) if isinstance(validation, dict) else False,
        "contract_validation_ok": bool(contract.get("ok", False)) if isinstance(contract, dict) else False,
        "p12_executed": bool(execution.get("p12_executed", False)),
        "p13_executed": bool(execution.get("p13_executed", False)),
        "p11_executed": bool(execution.get("p11_executed", False)),
        "p12_succeeded": bool(execution.get("p12_succeeded", False)),
        "p13_succeeded": bool(execution.get("p13_succeeded", False)),
        "p11_succeeded": bool(execution.get("p11_succeeded", False)),
        "explicit_targets_available": bool(stages.get("P13", {}).get("actual_outputs")),
        "predictive_metrics_available": p11_metrics is not None,
        "auc_m": p11_metrics.get("auc_m") if isinstance(p11_metrics, dict) else None,
        "auc_mt": p11_metrics.get("auc_mt") if isinstance(p11_metrics, dict) else None,
        "omega_invariants": {
            "labels_inferred": omega.get("labels_inferred"),
            "targets_fabricated": omega.get("targets_fabricated"),
            "source_contracts_modified": omega.get("source_contracts_modified"),
            "legacy_mt_real_modified": omega.get("legacy_mt_real_modified"),
            "contracts_activated_by_executor": omega.get("contracts_activated_by_executor"),
            "p11_promotion_gate_modified": omega.get("p11_promotion_gate_modified"),
            "consciousness_claims_made": omega.get("consciousness_claims_made"),
        },
        "checked_artifacts": checked_artifacts,
        "checked_stages": checked_stages,
        "contract_validated_artifacts": contract_validated_artifacts,
        "failures": failures,
        "warnings": warnings,
        "safe_claim": "DS005620 mock E2E CI now emits a downloadable evidence bundle for engineering validation and contract audit.",
        "ci_claim_scope": "mock_e2e_engineering_validation_only",
        # Ontology fields
        "ontology_available": ontology_summary["ontology_available"],
        "ontology_max_claim_scope": ontology_summary["max_claim_scope"],
        "ontology_promotion_state": ontology_summary["promotion_state"],
        "ontology_claim_status": ontology_summary["ontology_claim_status"],
        "ontology_promotion": ontology_summary["ontology_promotion"],
        "empirical_marker_promotion": ontology_summary["empirical_marker_promotion"],
        "empirical_topology_promotion": ontology_summary["empirical_topology_promotion"],
        "mechanism_promotion": ontology_summary["mechanism_promotion"],
        "metaphysical_promotion": ontology_summary["metaphysical_promotion"],
        "ontology_safe_claim": ontology_summary["safe_claim"],
    }
    return report


def build_markdown(report: dict) -> str:
    lines = [
        "# DS005620 Mock E2E CI Evidence Report",
        "",
        "## Run summary",
        f"- dataset_id: `{report['dataset_id']}`",
        f"- benchmark_completed: `{report['benchmark_completed']}`",
        f"- artifact_root: `{report['artifact_root']}`",
        "",
        "## Stage summary",
        f"- P12 executed/succeeded: `{report['p12_executed']}` / `{report['p12_succeeded']}`",
        f"- P13 executed/succeeded: `{report['p13_executed']}` / `{report['p13_succeeded']}`",
        f"- P11 executed/succeeded: `{report['p11_executed']}` / `{report['p11_succeeded']}`",
        "",
        "## Validator summary",
        f"- validation_ok: `{report['validation_ok']}`",
        f"- checked_artifacts: `{len(report['checked_artifacts'])}`",
        f"- checked_stages: `{report['checked_stages']}`",
        "",
        "## Contract summary",
        f"- contract_validation_ok: `{report['contract_validation_ok']}`",
        f"- validated artifacts: `{report['contract_validated_artifacts']}`",
        "",
        "## P11 metrics summary",
        f"- predictive_metrics_available: `{report['predictive_metrics_available']}`",
        f"- auc_m: `{report['auc_m']}`",
        f"- auc_mt: `{report['auc_mt']}`",
        "",
        "## Guardrail summary",
        f"- omega_invariants: `{report['omega_invariants']}`",
        f"- warnings: `{report['warnings']}`",
        f"- failures: `{report['failures']}`",
        "",
        "## Ontology Evaluation Summary",
        "",
        f"- ontology_available: `{report['ontology_available']}`",
        f"- scope: `{report['ontology_max_claim_scope']}`",
        f"- promotion state: `{report['ontology_promotion_state']}`",
        f"- ontology status: `{report['ontology_claim_status']}`",
        f"- empirical_marker_promotion: `{report['empirical_marker_promotion']}`",
        f"- empirical_topology_promotion: `{report['empirical_topology_promotion']}`",
        f"- mechanism_promotion: `{report['mechanism_promotion']}`",
        f"- metaphysical_promotion: `{report['metaphysical_promotion']}`",
        "",
        "Engineering runtime validation only. "
        "Empirical Level M / T claims are blocked pending real execution and controls. "
        "Substrate / theory / ontology candidates remain quarantined.",
        "",
        "## CI claim scope",
        f"- {report['ci_claim_scope']}",
        "",
        "## What this does not establish",
        "- This report does not establish empirical findings, causal interpretation, or external validity.",
        "",
        "## Next real/local requirements",
        "- Real/local runs still require reviewed contract confirmation and human-controlled data placement.",
    ]
    md = "\n".join(lines) + "\n"
    lower = md.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lower:
            raise ValueError(f"markdown contains banned phrase: {phrase}")
    return md


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--validation-summary", required=True)
    ap.add_argument("--contract-summary", required=True)
    ap.add_argument("--json-out", required=True)
    ap.add_argument("--markdown-out", required=True)
    ap.add_argument(
        "--ontology-root",
        default=_DEFAULT_ONTOLOGY_ROOT,
        help="Path to ontology evaluation output directory",
    )
    args = ap.parse_args(argv)

    root = Path(args.root)
    report = build_report(
        root,
        Path(args.validation_summary),
        Path(args.contract_summary),
        ontology_root=args.ontology_root,
    )

    json_out = Path(args.json_out)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    markdown = build_markdown(report)
    md_out = Path(args.markdown_out)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.write_text(markdown, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
