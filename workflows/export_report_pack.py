"""CLI for `workflows.report_pipeline`.

    python -m workflows.export_report_pack --spec pipeline_spec.json

    python -m workflows.export_report_pack --spec pipeline_spec.json \\
        --out outputs/report_packs/my-demo --dry-run

    python -m workflows.export_report_pack --spec pipeline_spec.json \\
        --registry benchmarks/registry_seed.json \\
        --include-phase-space --include-evidence-bundle --include-report

Default behavior runs the pipeline exactly as declared in `--spec`.
`--dry-run`/`--out`/`--include-*`/`--registry` override the corresponding
spec field for this invocation only (the spec file on disk is never
mutated). `--updated-registry-out` is accepted for interface parity with
the underlying adapters but is currently informational only -- this
runner always writes registry updates under the deterministic
`<out>/adapter_export/registry_updated.json` path so every artifact a
report pack references stays under one root; see
docs/report_pipeline_runner.md#limitations.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dataset_acquisition.store import TargetRootError
from workflows.report_pipeline import (
    ReportPipelineError,
    ReportPipelineSpecV1,
    ReportPipelineValidationError,
    run_report_pipeline,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spec", type=Path, required=True, help="ReportPipelineSpecV1 JSON file")
    parser.add_argument("--out", type=str, default=None, help="override spec.output_root for this run")
    parser.add_argument("--dry-run", action="store_true", help="override spec.dry_run=True for this run")
    parser.add_argument("--include-phase-space", action="store_true")
    parser.add_argument("--include-evidence-bundle", action="store_true")
    parser.add_argument("--include-report", action="store_true")
    parser.add_argument("--registry", type=str, default=None, help="override spec.registry_path for this run")
    parser.add_argument("--updated-registry-out", type=str, default=None, help="accepted for interface parity; informational only (see module docstring)")
    args = parser.parse_args()

    try:
        spec = ReportPipelineSpecV1.from_json(Path(args.spec).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[workflows.export_report_pack] FAILED: could not read --spec: {exc}")
        return 1

    if args.out is not None:
        spec.output_root = args.out
        spec.pipeline_id = spec.recompute_id()
    if args.dry_run:
        spec.dry_run = True
    if args.include_phase_space:
        spec.include_phase_space = True
    if args.include_evidence_bundle:
        spec.include_evidence_bundle = True
    if args.include_report:
        spec.include_report = True
    if args.registry is not None:
        spec.registry_path = args.registry

    try:
        spec.validate_or_raise()
    except ReportPipelineValidationError as exc:
        print(f"[workflows.export_report_pack] FAILED: {exc}")
        return 1

    try:
        manifest = run_report_pipeline(spec)
    except (ReportPipelineError, ReportPipelineValidationError, TargetRootError) as exc:
        print(f"[workflows.export_report_pack] FAILED: {exc}")
        return 1

    if manifest.execution_status == "failed":
        print(json.dumps({
            "run_id": manifest.run_id, "pipeline_id": manifest.pipeline_id, "input_mode": manifest.input_mode,
            "dataset_id": manifest.dataset_id, "status": manifest.execution_status, "errors": manifest.errors,
        }, indent=2))
        return 1

    summary = {
        "run_id": manifest.run_id,
        "pipeline_id": manifest.pipeline_id,
        "input_mode": manifest.input_mode,
        "dataset_id": manifest.dataset_id,
        "status": manifest.execution_status,
        "steps_completed": manifest.steps_completed,
        "steps_skipped": manifest.steps_skipped,
        "output_root": manifest.output_root,
        "report_pack_path": manifest.report_pack_path,
        "evidence_bundle_paths": manifest.evidence_bundle_paths,
        "evidence_report_paths": manifest.evidence_report_paths,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
