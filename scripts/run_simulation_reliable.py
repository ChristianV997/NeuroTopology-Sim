#!/usr/bin/env python3
"""Reliable simulation campaign runner CLI.

Executes a bounded, resumable simulation campaign from a validated manifest,
preventing silent partial success and enforcing resource constraints.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.simulation_runtime.atomic_io import (
    compute_config_hash,
    get_git_commit,
    json_safe,
    load_json,
    write_atomic_json,
)
from tools.simulation_runtime.checkpoint import (
    CheckpointCorruptError,
    CheckpointMismatchError,
)
from tools.simulation_runtime.guards import (
    check_dependencies,
    check_disk_budget,
    check_memory_budget,
)
from tools.simulation_runtime.runner import (
    SimulationCampaignRunner,
    run_campaign_manifest,
)
from tools.simulation_runtime.types import (
    CampaignManifest,
    Outcome,
    ResourcePolicy,
    WorkUnit,
    capture_environment_metadata,
)


def generate_synthetic_manifest(
    output_path: Path,
    num_units: int = 3,
    seed: int = 42,
) -> CampaignManifest:
    """Generate a valid synthetic manifest for testing or demonstration."""
    units: list[WorkUnit] = []
    for i in range(num_units):
        unit_id = f"sub-{i+1:02d}_ses-01_run-01_win-000"
        # Synthetic unit uses Python -c to simulate a quick work unit
        cmd = [
            sys.executable,
            "-c",
            f"import time; print('Processed unit {unit_id}'); time.sleep(0.01)",
        ]
        units.append(
            WorkUnit(
                unit_id=unit_id,
                command=cmd,
                subject_id=f"sub-{i+1:02d}",
                session_id="ses-01",
                run_id="run-01",
                window_id="win-000",
                parameter_case={"seed": seed + i, "synthetic": True},
                expected_outputs=[],
                timeout_s=15.0,
                dependencies=[],
                estimated_disk_mb=1.0,
                estimated_memory_mb=64.0,
                retryable=True,
                max_retries=2,
            )
        )

    policy = ResourcePolicy(
        max_workers=1,
        concurrency_cap=4,
        min_disk_free_mb=100.0,
        max_memory_mb=2048.0,
        max_retries_per_unit=2,
        default_timeout_s=30.0,
    )

    manifest_dict = {
        "campaign_id": f"campaign_synthetic_{seed}",
        "seed": seed,
        "units": [u.to_dict() for u in units],
        "resource_policy": policy.to_dict(),
    }
    cfg_hash = compute_config_hash(manifest_dict)

    manifest = CampaignManifest(
        schema_version="simulation_campaign_manifest_v1",
        campaign_id=f"campaign_synthetic_{seed}",
        created_at=datetime.now(timezone.utc).isoformat(),
        code_commit=get_git_commit(REPO_ROOT),
        configuration_hash=cfg_hash,
        seed=seed,
        units=units,
        environment=capture_environment_metadata(),
        resource_policy=policy,
    )

    write_atomic_json(output_path, manifest.to_dict())
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a bounded, reliable simulation campaign from manifest."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Path to campaign manifest JSON file.",
    )
    parser.add_argument(
        "--generate-synthetic-manifest",
        type=Path,
        help="Generate a valid synthetic manifest and save to path.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/simulation_campaigns/default"),
        help="Directory where unit outputs, checkpoints, and summaries are written.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="Number of concurrent workers (capped by resource policy and physical cores).",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore existing checkpoints and start a fresh run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate manifest and resource budgets without executing work units.",
    )
    parser.add_argument(
        "--format",
        choices=["summary", "json"],
        default="summary",
        help="Output format to display upon completion.",
    )

    args = parser.parse_args(argv)

    if args.generate_synthetic_manifest:
        gen_path = args.generate_synthetic_manifest.resolve()
        manifest = generate_synthetic_manifest(gen_path)
        print(f"Generated synthetic manifest at: {gen_path}")
        if not args.manifest:
            return 0
        args.manifest = gen_path

    if not args.manifest:
        parser.error("Either --manifest or --generate-synthetic-manifest is required.")

    manifest_path = args.manifest.resolve()
    if not manifest_path.exists():
        print(f"Error: Manifest not found: {manifest_path}", file=sys.stderr)
        return 1

    try:
        raw_manifest = load_json(manifest_path)
        manifest = CampaignManifest.from_dict(raw_manifest)
    except Exception as exc:
        print(f"Error loading manifest {manifest_path}: {exc}", file=sys.stderr)
        return 1

    # Override max_workers if specified
    if args.max_workers is not None:
        manifest.resource_policy.max_workers = args.max_workers

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Dry-run validation
    if args.dry_run:
        print(f"--- Dry Run Validation for Campaign: {manifest.campaign_id} ---")
        print(f"Code Commit: {manifest.code_commit}")
        print(f"Units Count: {len(manifest.units)}")
        print(f"Config Hash: {manifest.configuration_hash}")
        disk_ok, disk_reason, free_mb = check_disk_budget(
            output_dir, 10.0, manifest.resource_policy.min_disk_free_mb
        )
        print(f"Disk Check: {'PASS' if disk_ok else 'FAIL'} ({disk_reason})")
        all_deps = [d for u in manifest.units for d in u.dependencies]
        deps_ok, missing = check_dependencies(all_deps)
        print(f"Dependencies Check: {'PASS' if deps_ok else 'FAIL'} (missing: {missing})")
        if not disk_ok or not deps_ok:
            return 2
        print("Dry run validation PASSED. All gates satisfied.")
        return 0

    # Execute campaign
    try:
        runner = SimulationCampaignRunner(manifest=manifest, output_dir=output_dir)
        state = runner.run(resume=not args.no_resume)
    except (CheckpointMismatchError, CheckpointCorruptError) as exc:
        print(f"Checkpoint error: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"Unexpected campaign execution error: {exc}", file=sys.stderr)
        return 4

    summary_file = output_dir / "campaign_summary.json"
    if args.format == "json" and summary_file.exists():
        print(summary_file.read_text(encoding="utf-8"))
    else:
        md_file = output_dir / "campaign_summary.md"
        if md_file.exists():
            print(md_file.read_text(encoding="utf-8"))

    # Return 0 only if 100% of units passed
    summary = state.summary
    total = len(manifest.units)
    passed = summary.get(Outcome.PASS.value, 0)

    if state.is_complete and passed == total:
        return 0
    else:
        print(
            f"Campaign finished with non-passing status: "
            f"{passed}/{total} units passed (is_complete={state.is_complete}, is_partial={state.is_partial})",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
