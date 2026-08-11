"""CLI for `adapters.mne_bids_feature_recipe`.

    python -m adapters.mne_bids_feature_recipe_cli \\
        --spec recipe_spec.json --epoch-table epoch_table.json \\
        --out outputs/feature_recipes/<recipe_id>

    python -m adapters.mne_bids_feature_recipe_cli \\
        --spec recipe_spec.json --out outputs/feature_recipes/<recipe_id> \\
        --run-mne-bids-adapter --registry benchmarks/registry_seed.json \\
        --updated-registry-out outputs/feature_recipes/<recipe_id>/reg.json \\
        --include-evidence-bundle --include-report

Default behavior only writes `derived_features.csv`/`mapping.json`/
`recipe_manifest.json`/`summary.json` -- `--run-mne-bids-adapter` is
required to continue into `adapters.mne_bids`'s governed chain.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from adapters.mne_bids_feature_recipe import FeatureRecipeError, run_feature_recipe, write_recipe_outputs
from adapters.mne_bids_feature_recipe_schema import FeatureRecipeSpecV1
from adapters.mne_bids_feature_recipe_validation import FeatureRecipeValidationError
from dataset_acquisition.store import TargetRootError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--spec", type=Path, required=True, help="FeatureRecipeSpecV1 JSON file")
    parser.add_argument("--epoch-table", type=Path, default=None, help="epoch table JSON (required when spec.input_kind='epoch_table')")
    parser.add_argument("--out", type=Path, required=True, help="output directory (must be under outputs/ or data/)")
    parser.add_argument("--dry-run", action="store_true", help="validate the spec and print the plan without writing features")

    parser.add_argument("--run-mne-bids-adapter", action="store_true", help="continue into adapters.mne_bids after writing features")
    parser.add_argument("--registry", type=Path, default=None)
    parser.add_argument("--no-registry", action="store_true")
    parser.add_argument("--requested-use", default="transition_export")
    parser.add_argument("--claim-family", default="mne_bids_feature_recipe_transition")
    parser.add_argument("--include-phase-space", action="store_true")
    parser.add_argument("--include-evidence-bundle", action="store_true")
    parser.add_argument("--include-report", action="store_true")
    parser.add_argument("--updated-registry-out", type=Path, default=None)
    args = parser.parse_args()

    try:
        spec = FeatureRecipeSpecV1.from_json(Path(args.spec).read_text(encoding="utf-8"))
        spec.validate_or_raise()
    except (OSError, json.JSONDecodeError, FeatureRecipeValidationError) as exc:
        print(f"[adapters.mne_bids_feature_recipe_cli] FAILED: {exc}")
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
            "max_subjects": spec.max_subjects,
            "max_runs": spec.max_runs,
            "max_epochs_per_state": spec.max_epochs_per_state,
            "max_total_epochs": spec.max_total_epochs,
        }, indent=2))
        return 0

    try:
        result = run_feature_recipe(spec, epoch_table_path=args.epoch_table)
        features_path, mapping_path, manifest, summary_path = write_recipe_outputs(spec, result, args.out)
    except (FeatureRecipeError, FeatureRecipeValidationError, TargetRootError) as exc:
        print(f"[adapters.mne_bids_feature_recipe_cli] FAILED: {exc}")
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
        "skipped_runs": len(manifest.skipped_runs),
        "skipped_events": len(manifest.skipped_events),
        "output_features_path": manifest.output_features_path,
        "output_mapping_path": manifest.output_mapping_path,
        "output_summary_path": manifest.output_summary_path,
    }

    if args.run_mne_bids_adapter:
        from adapters.mne_bids import (
            AdapterDataError,
            AdapterEligibilityError,
            AdapterExportError,
            AdapterRegistryError,
            export_mne_bids_derived_transitions,
        )
        from adapters.validation import AdapterMappingError

        try:
            adapter_result = export_mne_bids_derived_transitions(
                features_path, mapping_path, Path(args.out) / "adapter_export",
                registry_path=args.registry, no_registry=args.no_registry,
                requested_use=args.requested_use, claim_family=args.claim_family,
                include_phase_space=args.include_phase_space,
                include_evidence_bundle=args.include_evidence_bundle,
                include_report=args.include_report,
                updated_registry_out=args.updated_registry_out,
            )
        except (AdapterEligibilityError, AdapterMappingError, AdapterDataError, AdapterExportError, AdapterRegistryError) as exc:
            print(f"[adapters.mne_bids_feature_recipe_cli] FAILED: --run-mne-bids-adapter: {exc}")
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
