"""CLI for `adapters.fmri_derivatives_feature_recipe`.

    python -m adapters.fmri_derivatives_feature_recipe_cli \\
        --spec recipe_spec.json --timeseries-table timeseries.json \\
        --out outputs/feature_recipes/<recipe_id>

    python -m adapters.fmri_derivatives_feature_recipe_cli \\
        --spec recipe_spec.json --out outputs/feature_recipes/<recipe_id> \\
        --graph-summary graph_summary.json \\
        --run-fmri-derivatives-adapter --registry benchmarks/registry_seed.json \\
        --updated-registry-out outputs/feature_recipes/<recipe_id>/reg.json \\
        --include-evidence-bundle --include-report

Default behavior only writes `derived_features.csv`/`mapping.json`/
`recipe_manifest.json`/`summary.json` -- `--run-fmri-derivatives-adapter`
is required to continue into `adapters.fmri_derivatives`'s governed chain.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from adapters.fmri_derivatives_feature_recipe import FmriFeatureRecipeError, run_feature_recipe, write_recipe_outputs
from adapters.fmri_derivatives_feature_recipe_schema import FmriFeatureRecipeSpecV1
from adapters.fmri_derivatives_feature_recipe_validation import FmriFeatureRecipeValidationError
from dataset_acquisition.store import TargetRootError


def _resolve_input_path(args: argparse.Namespace) -> Optional[Path]:
    if args.timeseries_table is not None:
        return args.timeseries_table
    if args.connectivity_matrix is not None:
        return args.connectivity_matrix
    if args.graph_summary is not None:
        return args.graph_summary
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spec", type=Path, required=True, help="FmriFeatureRecipeSpecV1 JSON file")
    parser.add_argument("--timeseries-table", type=Path, default=None, help="timeseries_table JSON fixture")
    parser.add_argument("--connectivity-matrix", type=Path, default=None, help="connectivity_matrix JSON fixture")
    parser.add_argument("--graph-summary", type=Path, default=None, help="self-contained format='graph_summary' JSON")
    parser.add_argument("--out", type=Path, required=True, help="output directory (must be under outputs/ or data/)")
    parser.add_argument("--dry-run", action="store_true", help="validate the spec and print the plan without writing features")

    parser.add_argument("--run-fmri-derivatives-adapter", action="store_true", help="continue into adapters.fmri_derivatives after writing features")
    parser.add_argument("--registry", type=Path, default=None)
    parser.add_argument("--no-registry", action="store_true")
    parser.add_argument("--requested-use", default="transition_export")
    parser.add_argument("--claim-family", default="fmri_derivatives_feature_recipe_transition")
    parser.add_argument("--include-phase-space", action="store_true")
    parser.add_argument("--include-evidence-bundle", action="store_true")
    parser.add_argument("--include-report", action="store_true")
    parser.add_argument("--updated-registry-out", type=Path, default=None)
    args = parser.parse_args()

    try:
        spec = FmriFeatureRecipeSpecV1.from_json(Path(args.spec).read_text(encoding="utf-8"))
        spec.validate_or_raise()
    except (OSError, json.JSONDecodeError, FmriFeatureRecipeValidationError) as exc:
        print(f"[adapters.fmri_derivatives_feature_recipe_cli] FAILED: {exc}")
        return 1

    if args.dry_run:
        print(json.dumps({
            "recipe_id": spec.recipe_id,
            "dry_run": True,
            "dataset_id": spec.dataset_id,
            "input_kind": spec.input_kind,
            "source_state": spec.source_state,
            "target_state": spec.target_state,
            "requested_features": spec.requested_features,
            "atlas_or_parcellation": spec.atlas_or_parcellation,
            "max_subjects": spec.max_subjects,
            "max_runs": spec.max_runs,
            "max_timepoints_per_state": spec.max_timepoints_per_state,
            "max_total_timepoints": spec.max_total_timepoints,
        }, indent=2))
        return 0

    input_path = _resolve_input_path(args)
    if input_path is None:
        print("[adapters.fmri_derivatives_feature_recipe_cli] FAILED: one of --timeseries-table/--connectivity-matrix/--graph-summary is required")
        return 1

    try:
        result = run_feature_recipe(spec, input_path=input_path)
        features_path, mapping_path, manifest, summary_path = write_recipe_outputs(spec, result, args.out)
    except (FmriFeatureRecipeError, FmriFeatureRecipeValidationError, TargetRootError) as exc:
        print(f"[adapters.fmri_derivatives_feature_recipe_cli] FAILED: {exc}")
        return 1

    summary_out: dict[str, Any] = {
        "recipe_id": spec.recipe_id,
        "manifest_id": manifest.manifest_id,
        "dataset_id": spec.dataset_id,
        "subjects_used": manifest.subjects_used,
        "states_observed": manifest.states_observed,
        "features_written": manifest.features_written,
        "transitions_exportable": manifest.transitions_exportable,
        "skipped_subjects": len(manifest.skipped_subjects),
        "skipped_inputs": len(manifest.skipped_inputs),
        "output_features_path": manifest.output_features_path,
        "output_mapping_path": manifest.output_mapping_path,
        "output_summary_path": manifest.output_summary_path,
    }

    if args.run_fmri_derivatives_adapter:
        from adapters.fmri_derivatives import (
            AdapterExportError,
            AdapterRegistryError,
            export_fmri_derivative_transitions,
        )
        from adapters.fmri_derivatives_contract import AdapterEligibilityError
        from adapters.fmri_derivatives_features import AdapterDataError
        from adapters.fmri_derivatives_validation import AdapterMappingError

        try:
            adapter_result = export_fmri_derivative_transitions(
                features_path, mapping_path, Path(args.out) / "adapter_export",
                registry_path=args.registry, no_registry=args.no_registry,
                requested_use=args.requested_use, claim_family=args.claim_family,
                include_phase_space=args.include_phase_space,
                include_evidence_bundle=args.include_evidence_bundle,
                include_report=args.include_report,
                updated_registry_out=args.updated_registry_out,
            )
        except (AdapterEligibilityError, AdapterMappingError, AdapterDataError, AdapterExportError, AdapterRegistryError) as exc:
            print(f"[adapters.fmri_derivatives_feature_recipe_cli] FAILED: --run-fmri-derivatives-adapter: {exc}")
            return 1

        summary_out["adapter_n_transitions_written"] = adapter_result["n_written"]
        summary_out["adapter_transitions_dir"] = adapter_result["transitions_dir"]
        if adapter_result["evidence_bundle"] is not None:
            summary_out["adapter_evidence_bundle_id"] = adapter_result["evidence_bundle"].bundle_id
        if adapter_result["report"] is not None:
            summary_out["adapter_report"] = adapter_result["report"]

    print(json.dumps(summary_out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
