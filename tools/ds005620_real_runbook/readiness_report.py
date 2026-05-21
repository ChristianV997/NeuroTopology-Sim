from __future__ import annotations
import argparse
from pathlib import Path
from . import write_json
from .data_room_audit import build_data_room_audit
from .operator_checklist import build_operator_checklist
from .reviewed_contract_audit import build_reviewed_contract_audit
from .real_run_command_builder import build_manual_command
from .post_run_artifact_inventory import build_post_run_expected_artifacts

def build_report() -> dict:
    data_audit = build_data_room_audit()
    contract = build_reviewed_contract_audit(data_audit)
    missing_files = data_audit.get("missing_local_files", [])
    missing_contract_items = contract.get("missing_contract_items", [])
    blocked = [f"missing_local_files:{len(missing_files)}" if missing_files else "", f"missing_contract_items:{len(missing_contract_items)}" if missing_contract_items else ""]
    blocked_by = [b for b in blocked if b]
    return {
        "dataset_id": "DS005620",
        "ready_for_manual_real_run": not blocked_by,
        "blocked_by": blocked_by,
        "next_action": "Resolve missing files and contract review items, then perform human peer review.",
        "missing_files": missing_files,
        "missing_contract_items": missing_contract_items,
        "missing_controls": ["human_peer_review_signoff", "post_run_control_validation"],
        "empirical_claims_permitted": False,
    }

def render_report_md(report: dict) -> str:
    return "\n".join([
        "# DS005620 Real Execution Readiness Report",
        f"- ready_for_manual_real_run: {report['ready_for_manual_real_run']}",
        f"- blocked_by: {report['blocked_by']}",
        f"- next_action: {report['next_action']}",
        "- empirical_claims_permitted: false",
    ]) + "\n"

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="outputs/btc_icft/ds005620_real_runbook")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    data_audit = build_data_room_audit(); write_json(out / "data_room_audit.json", data_audit)
    write_json(out / "missing_local_files.json", {"missing_local_files": data_audit.get("missing_local_files", [])})
    (out / "operator_checklist.md").write_text(build_operator_checklist(), encoding="utf-8")
    contract = build_reviewed_contract_audit(data_audit); write_json(out / "reviewed_contract_audit.json", contract)
    write_json(out / "real_run_command_manual_only.json", build_manual_command())
    write_json(out / "post_run_expected_artifacts.json", build_post_run_expected_artifacts())
    report = build_report(); write_json(out / "readiness_report.json", report)
    (out / "ds005620_real_runbook_report.md").write_text(render_report_md(report), encoding="utf-8")
    write_json(out / "generation_manifest.json", {"package": "tools.ds005620_real_runbook", "dataset_id": "DS005620", "manual_only": True})

if __name__ == "__main__":
    main()
