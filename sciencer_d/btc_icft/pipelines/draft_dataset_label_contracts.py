from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sciencer_d.btc_icft.labels.dataset_contract_draft import (
    draft_contracts_from_readiness_dir,
    write_contract_draft_outputs,
)


def _mock_readiness(out_dir: Path) -> Path:
    rd = out_dir / ".mock_readiness"
    rd.mkdir(parents=True, exist_ok=True)
    seeds = ["DS005620", "DS002094", "ds001787", "ds003969", "ds003816", "PhysioNet_GABA"]
    per = {
        "DS005620": {"dataset_id": "DS005620", "readiness_status": "ready_to_activate", "best_probe": {"candidate_label_columns": ["trial_type", "condition"], "unique_values": {"trial_type": ["focus", "mind_wandering"]}}},
        "DS002094": {"dataset_id": "DS002094", "readiness_status": "needs_explicit_mapping", "best_probe": {"candidate_label_columns": ["condition"], "unique_values": {"condition": ["a", "b"]}}},
        "ds001787": {"dataset_id": "ds001787", "readiness_status": "metadata_file_not_found", "best_probe": {}},
        "ds003969": {"dataset_id": "ds003969", "readiness_status": "insufficient_label_values", "best_probe": {"candidate_label_columns": ["trial_type"], "unique_values": {"trial_type": ["single"]}}},
        "ds003816": {"dataset_id": "ds003816", "readiness_status": "no_candidate_label_column", "best_probe": {}},
        "PhysioNet_GABA": {"dataset_id": "PhysioNet_GABA", "readiness_status": "metadata_empty_or_unreadable", "best_probe": {}},
    }
    (rd / "adapter_readiness_summary.json").write_text(json.dumps({"per_dataset": per, "n_datasets": len(seeds)}, indent=2), encoding="utf-8")
    return rd


def run(readiness_dir: str = "outputs/btc_icft/label_adapter_readiness", out_dir: str = "outputs/btc_icft/label_contract_drafts", mock_fixture: bool = False) -> int:
    rd = Path(readiness_dir)
    out = Path(out_dir)
    if mock_fixture:
        rd = _mock_readiness(out)
    if not rd.exists() and not mock_fixture:
        print("P14 adapter readiness outputs are required. Run plan_dataset_label_adapters first or use --mock-fixture.")
        return 1
    try:
        result = draft_contracts_from_readiness_dir(str(rd))
    except FileNotFoundError:
        print("P14 adapter readiness outputs are required. Run plan_dataset_label_adapters first or use --mock-fixture.")
        return 1
    outputs = write_contract_draft_outputs(result, str(out))
    print(f"Wrote {len(outputs)} outputs to {out}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--readiness-dir", default="outputs/btc_icft/label_adapter_readiness")
    p.add_argument("--out", default="outputs/btc_icft/label_contract_drafts")
    p.add_argument("--mock-fixture", action="store_true")
    a = p.parse_args()
    return run(a.readiness_dir, a.out, a.mock_fixture)


if __name__ == "__main__":
    sys.exit(main())
