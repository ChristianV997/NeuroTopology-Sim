from __future__ import annotations
import argparse
from pathlib import Path
from . import read_json, write_json

FORBIDDEN = ["ontology proved", "empirical proof", "consciousness solved"]

def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--root", default="outputs/btc_icft/ds005620_real_runbook"); args = ap.parse_args()
    root = Path(args.root); errors: list[str] = []
    cmd = read_json(root / "real_run_command_manual_only.json") if (root / "real_run_command_manual_only.json").exists() else {}
    report = read_json(root / "readiness_report.json") if (root / "readiness_report.json").exists() else {}
    contract = read_json(root / "reviewed_contract_audit.json") if (root / "reviewed_contract_audit.json").exists() else {}
    if cmd.get("can_auto_execute") is not False: errors.append("auto-execute allowed")
    if report.get("empirical_claims_permitted") is not False: errors.append("empirical_claims_permitted true")
    if contract.get("peer_review_confirmed_by_human") is True: errors.append("peer review auto-confirmed")
    ctext = str(cmd.get("command", ""))
    if "--execute" in ctext and not cmd.get("not_executed_by_tool", False): errors.append("execute flag without manual wrapper")
    for p in root.glob("*.json"):
        t = p.read_text(encoding="utf-8").lower()
        if "labels_inferred\": true" in t: errors.append("labels inferred")
        if "targets_fabricated\": true" in t: errors.append("targets fabricated")
        for bad in FORBIDDEN:
            if bad in t: errors.append(f"forbidden claim: {bad}")
    out = {"valid": not errors, "errors": errors}
    write_json(root / "validation.json", out)
    if errors: raise SystemExit(1)

if __name__ == "__main__":
    main()
