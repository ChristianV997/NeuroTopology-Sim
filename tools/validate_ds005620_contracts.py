from __future__ import annotations

import argparse
import json
from pathlib import Path

CORE_ARTIFACTS = [
    "ds005620_real_benchmark_execution.json",
    "stage_execution_plan.json",
    "stage_results.json",
    "execution_blockers.json",
    "omega_event.json",
    "report.md",
]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def require_keys(obj: dict, keys: list[str], ctx: str, failures: list[str]) -> None:
    for k in keys:
        if k not in obj:
            failures.append(f"{ctx} missing key: {k}")


def require_type(obj: dict, key: str, typ: type, ctx: str, failures: list[str]) -> None:
    if key in obj and not isinstance(obj[key], typ):
        failures.append(f"{ctx}.{key} must be {typ.__name__}")


def scan_forbidden_phrases_in_json(obj, forbidden: list[str], ctx: str, failures: list[str]) -> None:
    blob = json.dumps(obj).lower()
    for phrase in forbidden:
        if phrase.lower() in blob:
            failures.append(f"{ctx} contains forbidden phrase: {phrase}")


def validate_execution_summary(data: dict, failures: list[str]) -> None:
    required = ["dataset_id","mode","dry_run","execute_requested","peer_reviewed_contract_confirmed","p12_executed","p13_executed","p11_executed","p12_succeeded","p13_succeeded","p11_succeeded","benchmark_completed","artifact_root","execution_blockers","warnings","safe_claim"]
    require_keys(data, required, "ds005620_real_benchmark_execution.json", failures)
    if data.get("dataset_id") != "DS005620":
        failures.append("dataset_id must equal DS005620")
    if data.get("benchmark_completed") and not all(data.get(k) is True for k in ["p12_succeeded", "p13_succeeded", "p11_succeeded"]):
        failures.append("benchmark_completed true requires all stage succeeded true")
    if data.get("dry_run") is True and data.get("benchmark_completed") is True:
        failures.append("dry_run true requires benchmark_completed false")
    if not isinstance(data.get("execution_blockers"), list):
        failures.append("execution_blockers must be list")
    if not isinstance(data.get("warnings"), list):
        failures.append("warnings must be list")


def validate_stage_plan(data: dict, failures: list[str]) -> None:
    require_keys(data, ["stages", "paths"], "stage_execution_plan.json", failures)
    stages = data.get("stages", [])
    if not isinstance(stages, list):
        failures.append("stage_execution_plan.json.stages must be list")
        return
    allowed = {"P12", "P13", "P11"}
    for s in stages:
        require_keys(s, ["stage_id","stage_name","command","command_str","ready_to_run","expected_outputs"], "stage_execution_plan stage", failures)
        sid = s.get("stage_id")
        if sid not in allowed:
            failures.append(f"stage_execution_plan invalid stage_id: {sid}")
        cmd = " ".join(s.get("command", [])) if isinstance(s.get("command"), list) else str(s.get("command", ""))
        if sid == "P12" and ("align_eeg_labels" not in cmd or "--external-contract" not in cmd):
            failures.append("P12 command must include align_eeg_labels and --external-contract")
        if sid == "P13" and "inject_eeg_targets" not in cmd:
            failures.append("P13 command must include inject_eeg_targets")
        if sid == "P11":
            if "run_eeg_signal_mt" not in cmd or "features_m_signal_labeled.csv" not in cmd:
                failures.append("P11 command must include run_eeg_signal_mt and features_m_signal_labeled.csv")
            if "--m-features" in cmd and "features_m_signal.csv" in cmd and "labeled" not in cmd:
                failures.append("P11 command must not pass raw features_m_signal.csv to --m-features")


def validate_stage_results(data: dict, failures: list[str]) -> None:
    require_keys(data, ["stages"], "stage_results.json", failures)
    stages = data.get("stages", [])
    if not isinstance(stages, list):
        failures.append("stage_results.json.stages must be list")
        return
    by_id = {s.get("stage_id"): s for s in stages if isinstance(s, dict)}
    for s in stages:
        require_keys(s, ["stage_id","stage_name","command","ready_to_run","would_execute","executed","skipped","succeeded","exit_code","blockers","expected_outputs","actual_outputs","stdout_preview","stderr_preview","duration_seconds"], "stage_results stage", failures)
        if s.get("executed") is False and s.get("exit_code") is not None:
            failures.append(f"{s.get('stage_id')} executed=false requires exit_code=null")
        if len(str(s.get("stdout_preview", ""))) > 4500 or len(str(s.get("stderr_preview", ""))) > 4500:
            failures.append(f"{s.get('stage_id')} stdout/stderr preview exceeds 4500 chars")
    p12, p13, p11 = by_id.get("P12", {}), by_id.get("P13", {}), by_id.get("P11", {})
    p12_ok_or_exists = p12.get("succeeded") is True or bool(p12.get("actual_outputs"))
    p13_ok_or_exists = p13.get("succeeded") is True or bool(p13.get("actual_outputs"))
    if p13.get("executed") is True and not p12_ok_or_exists:
        failures.append("P13 cannot execute unless P12 succeeded or P12 output exists")
    if p11.get("executed") is True and not p13_ok_or_exists:
        failures.append("P11 cannot execute unless P13 succeeded or P13 output exists")


def validate_execution_blockers(data: dict, failures: list[str]) -> None:
    require_keys(data, ["execution_blockers", "stage_blockers", "all_blockers", "blocker_counts"], "execution_blockers.json", failures)
    if data.get("blocker_counts") != len(data.get("all_blockers", [])):
        failures.append("execution_blockers.blocker_counts must equal len(all_blockers)")


def validate_omega_event(data: dict, failures: list[str]) -> None:
    req = ["event_id","event_type","dataset_id","p12_executed","p13_executed","p11_executed","benchmark_completed","labels_inferred","targets_fabricated","source_contracts_modified","legacy_mt_real_modified","contracts_activated_by_executor","p11_promotion_gate_modified","consciousness_claims_made","safe_claim","forbidden_claims"]
    require_keys(data, req, "omega_event.json", failures)
    for k in ["labels_inferred","targets_fabricated","source_contracts_modified","legacy_mt_real_modified","contracts_activated_by_executor","p11_promotion_gate_modified","consciousness_claims_made"]:
        if data.get(k) is not False:
            failures.append(f"omega invariant {k} must be false")


def validate_validation_summary(data: dict, failures: list[str]) -> None:
    req = ["ok", "root", "failures", "checked_artifacts", "checked_stages", "benchmark_completed"]
    require_keys(data, req, "validation_summary.json", failures)
    if not isinstance(data.get("failures"), list):
        failures.append("validation_summary.failures must be list")
    if not set(CORE_ARTIFACTS).issubset(set(data.get("checked_artifacts", []))):
        failures.append("validation_summary.checked_artifacts missing required P18.1 artifacts")
    if data.get("ok") is True and data.get("failures"):
        failures.append("validation_summary.ok true requires empty failures")


def validate_all(root: Path, contracts: Path, validation_summary_path: Path | None):
    failures, warnings = [], []
    contracts_map = {
        "ds005620_real_benchmark_execution.json": "ds005620_real_benchmark_execution.contract.json",
        "stage_execution_plan.json": "stage_execution_plan.contract.json",
        "stage_results.json": "stage_results.contract.json",
        "execution_blockers.json": "execution_blockers.contract.json",
        "omega_event.json": "omega_event.contract.json",
        "validation_summary.json": "validation_summary.contract.json",
    }
    validators = {
        "ds005620_real_benchmark_execution.json": validate_execution_summary,
        "stage_execution_plan.json": validate_stage_plan,
        "stage_results.json": validate_stage_results,
        "execution_blockers.json": validate_execution_blockers,
        "omega_event.json": validate_omega_event,
        "validation_summary.json": validate_validation_summary,
    }
    validated = []
    for artifact, contract_name in contracts_map.items():
        path = validation_summary_path if artifact == "validation_summary.json" and validation_summary_path else root / artifact
        if not path.exists():
            if artifact == "validation_summary.json":
                warnings.append(f"optional artifact missing: {path}")
                continue
            failures.append(f"missing artifact: {path}")
            continue
        cdata = load_json(contracts / contract_name)
        adata = load_json(path)
        require_keys(cdata, ["contract_id", "version", "artifact"], f"contract {contract_name}", failures)
        scan_forbidden_phrases_in_json(adata, cdata.get("forbidden_phrases", []), artifact, failures)
        validators[artifact](adata, failures)
        validated.append(artifact)
    return {"ok": len(failures) == 0, "root": str(root), "contracts": str(contracts), "validated_artifacts": validated, "failures": failures, "warnings": warnings}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="outputs/btc_icft/ds005620_real_benchmark_execution_mock")
    ap.add_argument("--contracts", default="contracts/btc_icft/ds005620/p18_1")
    ap.add_argument("--validation-summary", default=None)
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--quiet", action="store_true", default=False)
    args = ap.parse_args(argv)
    root = Path(args.root)
    validation_summary = Path(args.validation_summary) if args.validation_summary else (root / "validation_summary.json")
    summary = validate_all(root, Path(args.contracts), validation_summary)
    out = Path(args.json_out) if args.json_out else (root / "contract_validation_summary.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if not args.quiet:
        print(f"[validate-ds005620-contracts] {'PASS' if summary['ok'] else 'FAIL'}: {root}")
        for failure in summary["failures"]:
            print(f"  - {failure}")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
