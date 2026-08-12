"""Deterministic output-directory layout for one report-pipeline run.

Reuses `dataset_acquisition.store.validate_target_root` directly for
output-root safety (the same `outputs/`/`data/`-only, no-`..`-traversal
check every recipe/adapter in this repository already uses) -- this
module adds no new safety logic, only a fixed set of subpaths under an
already-validated root.

Layout (caller supplies the literal target directory via
`ReportPipelineSpecV1.output_root`, matching the convention already
established by `adapters.mne_bids_feature_recipe`/
`adapters.fmri_derivatives_feature_recipe`'s own `--out`; this runner
never auto-nests under a fixed `outputs/report_packs/<pipeline_id>/`
prefix on the caller's behalf)::

    <output_root>/
        PipelineSpec.json
        PipelineRunManifest.json
        ReportPack.json                 (only when evidence was produced/referenced)
        recipe_output/                  (only for *_recipe input modes:
                                          derived_features.csv, mapping.json,
                                          recipe_manifest.json, summary.json --
                                          written by the reused recipe's own
                                          write_recipe_outputs(), unmodified)
        adapter_export/                 (only for modes that reach
                                          TransitionRecordV1: transitions/,
                                          phase_space/, EvidenceBundle.json,
                                          EvidenceReport.md/json,
                                          registry_updated.json -- all written
                                          by the reused adapter/evidence
                                          functions, unmodified)
        reports/                        (existing_evidence_bundle mode only:
                                          EvidenceReport.md/json referencing
                                          the externally-supplied bundle)

This deviates from the illustrative `features/`/`mappings/`/`transitions/`/
`phase_space/`/`evidence/`/`reports/` split sketched in the mission spec,
in favor of never re-implementing the adapters'/recipes' own directory
conventions (this milestone's core principle: never duplicate logic
already implemented elsewhere -- including I/O layout logic). Every
generated path is still recorded explicitly, by relative path, in
`ReportPipelineRunManifestV1`/`ReportPackV1`, so the manifest -- not a
folder name -- is the authoritative index.
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

from dataset_acquisition.store import validate_target_root

_REPO_ROOT = Path(__file__).resolve().parents[1]

SPEC_FILENAME = "PipelineSpec.json"
MANIFEST_FILENAME = "PipelineRunManifest.json"
REPORT_PACK_FILENAME = "ReportPack.json"
RECIPE_OUTPUT_SUBDIR = "recipe_output"
ADAPTER_EXPORT_SUBDIR = "adapter_export"
EXISTING_BUNDLE_REPORT_SUBDIR = "reports"
REGISTRY_UPDATED_FILENAME = "registry_updated.json"


class ReportPackLayout:
    """Resolves and (on `ensure_root()`) creates the deterministic output
    directory for one pipeline run, rooted at `output_root` (a caller
    -supplied path validated via `validate_target_root`)."""

    def __init__(self, output_root: Union[str, Path]) -> None:
        self._output_root_raw = str(output_root)
        self.root = validate_target_root(output_root)

    def ensure_root(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    @property
    def spec_path(self) -> Path:
        return self.root / SPEC_FILENAME

    @property
    def spec_path_relative(self) -> str:
        return self._relative(self.spec_path)

    @property
    def manifest_path(self) -> Path:
        return self.root / MANIFEST_FILENAME

    @property
    def report_pack_path(self) -> Path:
        return self.root / REPORT_PACK_FILENAME

    @property
    def recipe_output_dir(self) -> Path:
        return self.root / RECIPE_OUTPUT_SUBDIR

    @property
    def recipe_output_dir_relative(self) -> str:
        return self._relative(self.recipe_output_dir)

    @property
    def adapter_export_dir(self) -> Path:
        return self.root / ADAPTER_EXPORT_SUBDIR

    @property
    def registry_updated_path(self) -> Path:
        return self.adapter_export_dir / REGISTRY_UPDATED_FILENAME

    @property
    def existing_bundle_report_dir(self) -> Path:
        return self.root / EXISTING_BUNDLE_REPORT_SUBDIR

    @staticmethod
    def _relative(path: Path) -> str:
        try:
            return str(path.resolve().relative_to(_REPO_ROOT))
        except ValueError:
            return str(path)
