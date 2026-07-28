"""Compare theory-campaign observables with existing empirical summaries."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"status": "missing", "path": str(path)}
    return json.loads(path.read_text(encoding="utf-8"))


def build(campaign_dir: Path, output: Path) -> dict[str, Any]:
    ds005620 = Path("contracts/btc_icft/ds005620/pitnn_cohort/cohort_summary.json")
    ds000245 = Path("contracts/fmri_tda/ds000245/global_efficiency_gate.json")
    summary = _load(campaign_dir / "phase_diagram_summary.json")
    payload = {
        "schema": "NeuroTopologySim.EmpiricalTheoryConstraints.v1",
        "campaign": summary,
        "empirical_constraints": {
            "ds005620": _load(ds005620),
            "ds000245": _load(ds000245),
        },
        "interpretation": {
            "role": "soft_constraint_only",
            "prohibited_inference": "No empirical topology summary is treated as evidence for a microscopic collective or memory mechanism.",
            "required_next_step": "Compare candidate model directions against held-out empirical summaries without fitting speculative parameters to a single dataset.",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    report = """# Empirical Theory Constraints\n\nThis artifact compares existing empirical topology summaries with theory-campaign outputs as soft constraints only. It does not fit a microscopic mechanism, establish causality, or validate prior speculative claims.\n\n## Datasets\n\n- ds005620: paired EEG topology and PITNN falsification artifacts.\n- ds000245: fMRI gate artifacts where available.\n\n## Required interpretation\n\nA model regime is useful only if its directional predictions are robust across matched nulls and remain compatible with held-out empirical summaries. Multiple model regimes producing the same empirical direction indicate underdetermination, not confirmation.\n"""
    output.with_name("theory_empirical_constraints.md").write_text(report, encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.campaign_dir, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
