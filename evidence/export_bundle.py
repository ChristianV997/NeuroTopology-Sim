"""CLI for building a governed `EvidenceBundleV1`.

Usage::

    python -m evidence.export_bundle \\
        --dataset ds005620 --feature-set cohort_summary \\
        --registry benchmarks/registry_seed.json \\
        --source contracts/btc_icft/ds005620/pitnn_cohort \\
        --out outputs/evidence/ds005620_cohort_summary \\
        --include-phase-space --mark-seen \\
        --updated-registry-out outputs/evidence/ds005620_cohort_summary/registry_updated.json

    python -m evidence.export_bundle \\
        --dataset ds000245 --feature-set schaefer100_motcorr \\
        --registry benchmarks/registry_seed.json \\
        --source contracts/fmri_tda/ds000245 \\
        --out outputs/evidence/ds000245_schaefer100_motcorr \\
        --include-phase-space

`--registry` is effectively required (validation fails closed on missing
registry context) unless `--no-registry` is explicitly given for legacy,
unauthorized-use exploration. This is the package's only CLI entry point;
`evidence.bundle`/`evidence.builder`/`evidence.store`/`evidence.validation`
are library-only, matching `transitions.record`/`benchmarks.dataset_registry`'s
precedent of having no CLI of their own.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from evidence.builder import DISPATCH, BuildError, build_evidence_bundle  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", required=True, choices=sorted({d for d, _ in DISPATCH}))
    parser.add_argument("--feature-set", required=True, help="see --dataset's supported feature sets in module docs")
    parser.add_argument("--source", required=True, type=Path, help="source artifact directory to read")
    parser.add_argument("--out", required=True, type=Path, help="output directory for the evidence bundle")
    parser.add_argument("--registry", type=Path, default=None, help="benchmarks.export_registry.BenchmarkRegistry JSON path")
    parser.add_argument("--no-registry", action="store_true", help="explicit legacy mode: build without registry authorization")
    parser.add_argument("--requested-use", default="transition_export")
    parser.add_argument("--claim-family", default=None)
    parser.add_argument("--include-phase-space", action="store_true")
    parser.add_argument("--normalization-mode", default="within_record")
    parser.add_argument("--mark-seen", action="store_true")
    parser.add_argument("--seen-by", default="exploration", choices=("exploration", "llm", "theory_generation", "model_selection"))
    parser.add_argument("--updated-registry-out", type=Path, default=None)
    parser.add_argument(
        "--include-report", action="store_true",
        help="after building the bundle, also generate an EvidenceReportV1 (Markdown+JSON) "
             "from it via reports.evidence_report.build_report -- default: no report generated",
    )
    parser.add_argument(
        "--report-out", type=Path, default=None,
        help="output directory for the report when --include-report is given "
             "(default: the same directory as --out)",
    )
    args = parser.parse_args()

    try:
        bundle = build_evidence_bundle(
            dataset=args.dataset,
            feature_set=args.feature_set,
            source=args.source,
            out=args.out,
            registry_path=args.registry,
            requested_use=args.requested_use,
            claim_family=args.claim_family,
            include_phase_space=args.include_phase_space,
            normalization_mode=args.normalization_mode,
            mark_seen=args.mark_seen,
            seen_by=args.seen_by,
            updated_registry_out=args.updated_registry_out,
            no_registry=args.no_registry,
            include_report=args.include_report,
            report_out=args.report_out,
        )
    except BuildError as exc:
        print(f"[evidence.export_bundle] FAILED: {exc}")
        return 1

    summary = {
        "bundle_id": bundle.bundle_id,
        "dataset_id": bundle.dataset_id,
        "artifact_ids": bundle.artifact_ids,
        "requested_use": bundle.requested_use,
        "registry_decisions": bundle.registry_decisions,
        "contamination_updates": bundle.contamination_updates,
        "n_transition_records": len(bundle.transition_record_ids),
        "n_phase_space_coordinates": len(bundle.phase_space_coordinate_ids),
        "claim_scope_ceiling": bundle.claim_scope_ceiling,
        "evidence_level_ceiling": bundle.evidence_level_ceiling,
        "generated_claim_scope": bundle.generated_claim_scope,
        "generated_evidence_levels": bundle.generated_evidence_levels,
        "null_control_status": bundle.null_control_summary.get("status"),
        "out_dir": str(args.out),
    }
    if args.include_report:
        summary["report"] = bundle.metadata.get("report")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
