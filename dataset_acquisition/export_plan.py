"""CLI for `dataset_acquisition`.

    python -m dataset_acquisition.export_plan \\
        --candidate-file <candidates.json> --candidate-id <id> \\
        --target-root outputs/datasets/<id> --requested-action metadata_only \\
        --out outputs/acquisition/<id>_plan.json

    python -m dataset_acquisition.export_plan \\
        --candidate-file <candidates.json> --candidate-id <id> \\
        --target-root outputs/datasets/<id> --requested-action plan_download \\
        --disk-limit-mb 500 --out outputs/acquisition/<id>_plan.json

    python -m dataset_acquisition.export_plan \\
        --plan <plan.json> --execute --allow-network --allow-raw-data \\
        --disk-limit-mb 500 --manifest-out outputs/acquisition/<id>_manifest.json

Never downloads raw data by default. `--execute` alone is insufficient --
`--allow-network` and `--allow-raw-data` must also be passed, matching the
plan's own already-validated safety flags.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from dataset_acquisition.acquisition_plan import DatasetAcquisitionPlanV1
from dataset_acquisition.executor import ExecutorError, execute_acquisition_plan, run_bids_handoff
from dataset_acquisition.planner import PlannerError, plan_from_candidate_file
from dataset_acquisition.store import TargetRootError, validate_target_root
from dataset_acquisition.validation import DatasetAcquisitionValidationError


def _plan_summary(plan: DatasetAcquisitionPlanV1) -> dict[str, Any]:
    return {
        "plan_id": plan.plan_id,
        "candidate_id": plan.candidate_id,
        "requested_action": plan.requested_action,
        "acquisition_mode": plan.acquisition_mode,
        "dry_run": plan.dry_run,
        "target_root": plan.target_root,
        "estimated_size_bytes": plan.estimated_size_bytes,
        "disk_limit_bytes": plan.disk_limit_bytes,
        "blocked_reasons": list(plan.blocked_reasons),
    }


def _manifest_summary(manifest) -> dict[str, Any]:
    return {
        "manifest_id": manifest.manifest_id,
        "plan_id": manifest.plan_id,
        "execution_status": manifest.execution_status,
        "acquired_file_count": manifest.acquired_file_count,
        "acquired_size_bytes": manifest.acquired_size_bytes,
        "errors": list(manifest.errors),
    }


def _cmd_plan(args: argparse.Namespace) -> int:
    disk_limit_bytes: Optional[int] = int(args.disk_limit_mb * 1024 * 1024) if args.disk_limit_mb is not None else None

    try:
        plan = plan_from_candidate_file(
            args.candidate_file,
            args.candidate_id,
            target_root=args.target_root,
            requested_action=args.requested_action,
            disk_limit_bytes=disk_limit_bytes,
            allow_network=bool(args.allow_network),
            allow_raw_data=bool(args.allow_raw_data),
            acquisition_mode=args.acquisition_mode,
            force_unknown_size=bool(args.force_unknown_size),
            explicit_execute_confirmed=bool(args.execute),
        )
    except (PlannerError, TargetRootError, DatasetAcquisitionValidationError) as exc:
        print(f"[dataset_acquisition.export_plan] FAILED: {exc}")
        return 1

    summary = _plan_summary(plan)
    if args.out:
        plan.write_json(args.out)
        summary["out"] = str(args.out)
    print(json.dumps(summary, indent=2))
    return 0


def _cmd_execute(args: argparse.Namespace) -> int:
    plan = DatasetAcquisitionPlanV1.from_json(Path(args.plan).read_text(encoding="utf-8"))

    try:
        manifest = execute_acquisition_plan(
            plan,
            execute=bool(args.execute),
            allow_network=bool(args.allow_network),
            allow_raw_data=bool(args.allow_raw_data),
            force_unknown_size=bool(args.force_unknown_size),
        )
    except ExecutorError as exc:
        print(f"[dataset_acquisition.export_plan] FAILED: {exc}")
        return 1

    summary = _manifest_summary(manifest)

    if args.scan_bids_after_acquisition:
        if manifest.execution_status not in ("acquired", "verified_existing"):
            print(
                "[dataset_acquisition.export_plan] FAILED: --scan-bids-after-acquisition requires a "
                f"local acquired/verified manifest, got execution_status='{manifest.execution_status}'"
            )
            return 1
        try:
            handoff = run_bids_handoff(manifest, target_root=plan.target_root)
        except ExecutorError as exc:
            print(f"[dataset_acquisition.export_plan] FAILED: {exc}")
            return 1
        manifest.bids_metadata_summary = handoff["bids_metadata_summary"]
        summary["bids_metadata_summary"] = handoff["bids_metadata_summary"]
        summary["n_artifact_records"] = len(handoff["artifact_records"])

    if args.manifest_out:
        manifest.write_json(args.manifest_out)
        summary["manifest_out"] = str(args.manifest_out)

    print(json.dumps(summary, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidate-file", type=Path, default=None, help="DatasetCandidateRecordV1 export JSON (dataset_importers output)")
    parser.add_argument("--candidate-id", default=None, help="candidate_id to plan for")
    parser.add_argument("--target-root", default=None, help="relative repo path under outputs/ or data/")
    parser.add_argument(
        "--requested-action",
        choices=["metadata_only", "plan_download", "execute_download", "scan_existing_local", "verify_existing_local"],
        default="metadata_only",
    )
    parser.add_argument("--acquisition-mode", default=None)
    parser.add_argument("--disk-limit-mb", type=float, default=None)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--allow-raw-data", action="store_true")
    parser.add_argument("--force-unknown-size", action="store_true")
    parser.add_argument("--out", type=Path, default=None, help="write the plan JSON here")

    parser.add_argument("--plan", type=Path, default=None, help="an existing plan JSON to execute")
    parser.add_argument("--execute", action="store_true", help="actually execute the plan (default: dry-run)")
    parser.add_argument("--manifest-out", type=Path, default=None, help="write the resulting manifest JSON here")
    parser.add_argument(
        "--scan-bids-after-acquisition",
        action="store_true",
        help="after a local acquired/verified execution, run adapters.mne_bids's metadata scan over target_root",
    )
    args = parser.parse_args()

    if args.plan:
        return _cmd_execute(args)

    if not args.candidate_file or not args.candidate_id or not args.target_root:
        print(
            "[dataset_acquisition.export_plan] FAILED: --candidate-file, --candidate-id, and --target-root "
            "are required unless --plan is given"
        )
        return 1
    return _cmd_plan(args)


if __name__ == "__main__":
    sys.exit(main())
