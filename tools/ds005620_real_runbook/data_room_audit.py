from __future__ import annotations
from pathlib import Path
from .schema import FileCheck

ROOTS = ["data/DS005620", "data/ds005620", "inputs/DS005620", "inputs/ds005620"]
CHECKS = {
    "events_tsv": ["**/events.tsv"],
    "raw_eeg_files": ["**/*.edf", "**/*.set", "**/*.bdf", "**/*.vhdr"],
    "reviewed_contract": ["**/*reviewed*contract*.json", "**/*reviewed*contract*.md", "**/*peer*review*.md"],
    "mne_extraction_outputs": ["**/*mne*/*.json", "**/*mne*/*.npy", "**/*mne*/*.csv"],
    "level_m_features": ["**/*level_m*/*.json", "**/*level_m*/*.csv"],
    "level_t_features": ["**/*level_t*/*.json", "**/*level_t*/*.csv"],
    "p18_3_gate_outputs": ["outputs/btc_icft/ds005620_real_execution_gate/*.json", "outputs/btc_icft/ds005620_real_execution_gate/*.md"],
    "p20_artifact_operator_outputs": ["outputs/btc_icft/ds005620_real_artifact_operator/*.json", "outputs/btc_icft/ds005620_real_artifact_operator/*.md"],
    "p21_autonomous_iteration_outputs": ["outputs/btc_icft/ds005620_autonomous_iteration/*.json", "outputs/btc_icft/ds005620_autonomous_iteration/*.md"],
}

def _glob_many(patterns: list[str]) -> list[str]:
    out: list[str] = []
    for pat in patterns:
        out.extend(sorted(str(p) for p in Path('.').glob(pat) if p.is_file()))
    return sorted(set(out))

def build_data_room_audit() -> dict:
    root_status = [{"root": r, "exists": Path(r).exists()} for r in ROOTS]
    checks = []
    missing_files: list[dict] = []
    for cat, pats in CHECKS.items():
        found = _glob_many(pats)
        c = FileCheck(category=cat, expected=pats, found=found, missing=[])
        if not found:
            c.missing = pats
            missing_files.append({"category": cat, "missing_patterns": pats})
        checks.append(c.to_dict())
    return {"dataset_id": "DS005620", "roots": root_status, "checks": checks, "missing_local_files": missing_files}
