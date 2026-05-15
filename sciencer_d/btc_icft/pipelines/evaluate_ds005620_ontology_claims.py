"""
DS005620 ontology claim evaluator CLI (O3).

Reads P18.1/P18.2 execution artifacts and produces the ontology evaluation
output bundle:
  - ontology_claim_evaluation.json
  - claim_scope_matrix.json
  - bridge_claim_status.json
  - falsifier_status.json
  - alternative_explanations.json
  - ontology_promotion_decision.json
  - omega_event.json
  - report.md

Engineering claims only. No empirical, mechanism, theory, or ontology
claims are promoted by this CLI.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sciencer_d.btc_icft.ontology.ds005620_evaluator import run_evaluation


_DEFAULT_EXECUTION_ROOT = "outputs/btc_icft/ds005620_real_benchmark_execution_mock"
_DEFAULT_CONTROLS_ROOT = "outputs/btc_icft/ds005620_real_controls"
_DEFAULT_BRIDGE_REGISTRY = "configs/btc_icft/ontology_bridge_registry.json"
_DEFAULT_EVIDENCE_MATRIX = "contracts/btc_icft/ontology_claims/evidence_requirement_matrix.json"
_DEFAULT_OUT_DIR = "outputs/btc_icft/ds005620_ontology_evaluation_mock"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate DS005620 ontology claims (O3)")
    parser.add_argument("--execution-root", default=_DEFAULT_EXECUTION_ROOT)
    parser.add_argument("--controls-root", default=_DEFAULT_CONTROLS_ROOT)
    parser.add_argument("--evidence-packet", default=None)
    parser.add_argument("--bridge-registry", default=_DEFAULT_BRIDGE_REGISTRY)
    parser.add_argument("--evidence-matrix", default=_DEFAULT_EVIDENCE_MATRIX)
    parser.add_argument("--out", default=_DEFAULT_OUT_DIR)
    parser.add_argument("--run-mode", default=None,
                        help="Override run mode (e.g. mock_e2e, real_local)")
    parser.add_argument("--independent-dataset", action="store_true",
                        help="Treat independent_dataset_replication.json as present")
    parser.add_argument("--independent-mechanism-evidence", action="store_true",
                        help="Treat independent_mechanism_evidence_packet.json as present")
    parser.add_argument("--human-review-completed", action="store_true",
                        help="Mark human review as completed")
    args = parser.parse_args(argv)

    controls_root = args.controls_root if Path(args.controls_root).exists() else None

    paths = run_evaluation(
        execution_root=args.execution_root,
        controls_root=controls_root,
        out_dir=args.out,
        bridge_registry_path=args.bridge_registry,
        evidence_matrix_path=args.evidence_matrix,
        evidence_packet_path=args.evidence_packet,
        run_mode_override=args.run_mode,
        independent_dataset_present=args.independent_dataset,
        independent_mechanism_evidence_present=args.independent_mechanism_evidence,
        human_review_completed=args.human_review_completed,
    )
    for name, path in paths.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
