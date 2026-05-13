from __future__ import annotations

import argparse
import json
from pathlib import Path

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


def _load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_report(root: Path, validation_summary: Path, contract_summary: Path) -> dict:
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

    report = {
        "report_version": "p18.2-ci-evidence-v1",
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
    args = ap.parse_args(argv)

    root = Path(args.root)
    report = build_report(root, Path(args.validation_summary), Path(args.contract_summary))

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
