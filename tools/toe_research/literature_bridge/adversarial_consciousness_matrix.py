from __future__ import annotations

import argparse
import json
from pathlib import Path


THEORIES = [
    "Global Workspace Theory",
    "Integrated Information Theory",
    "Recurrent Processing Theory",
    "Active Inference",
    "Higher-Order Theories",
    "Orch-OR",
    "Predictive Processing",
]


def build_rows() -> list[dict]:
    return [
        {
            "theory": theory,
            "core_claim": f"Candidate mechanism described by {theory}",
            "what_it_explains": "A theory-specific subset of access, report, integration, or regulation",
            "what_BTC_ICFT_adds": "Artifact-controlled phase-topology telemetry for adversarial comparison",
            "what_BTC_ICFT_does_not_explain": "Subjective experience or ontology",
            "shared_predictions": ["state-dependent measurable dynamics"],
            "divergent_predictions": ["incremental topology value after matched baselines"],
            "falsifier": "No reproducible theory-distinguishing prediction under held-out controls",
            "required_experiment": "Preregistered multi-theory comparison with explicit labels and nulls",
            "claim_scope": "evidence_mapping",
        }
        for theory in THEORIES
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    Path(args.out).write_text(json.dumps(build_rows(), indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
