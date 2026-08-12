"""FmriFeatureRecipeSpecV1 / FmriDerivedFeatureRecipeManifestV1: dict
roundtrip and deterministic ID behavior. Synthetic fixtures only.
"""
from __future__ import annotations

from adapters.fmri_derivatives_feature_recipe_schema import (
    FmriDerivedFeatureRecipeManifestV1,
    FmriFeatureRecipeSpecV1,
    compute_recipe_id,
)


def _minimal_spec(**overrides) -> FmriFeatureRecipeSpecV1:
    kwargs = dict(
        dataset_id="demo_fmri",
        feature_set_id="fmri_connectivity_graph_v1",
        source_state="placebo",
        target_state="drug",
        atlas_or_parcellation="Schaefer100",
        requested_features=["connectivity.mean_connectivity"],
        max_subjects=5,
        max_runs=5,
        max_timepoints_per_state=100,
        max_total_timepoints=1000,
        state_mapping={"placebo_label": "placebo", "drug_label": "drug"},
        feature_definitions={"connectivity.mean_connectivity": "Mean off-diagonal Pearson correlation."},
        confound_policy={"description": "No confounds regression applied."},
        limitations=["test"],
        provenance="unit test fixture",
    )
    kwargs.update(overrides)
    return FmriFeatureRecipeSpecV1.make(**kwargs)


def test_spec_dict_roundtrip():
    spec = _minimal_spec()
    d = spec.to_dict()
    spec2 = FmriFeatureRecipeSpecV1.from_dict(d)
    assert spec2.to_dict() == d


def test_spec_json_roundtrip():
    spec = _minimal_spec()
    text = spec.to_json()
    spec2 = FmriFeatureRecipeSpecV1.from_json(text)
    assert spec2.to_dict() == spec.to_dict()


def test_spec_write_json_roundtrip(tmp_path):
    spec = _minimal_spec()
    path = spec.write_json(tmp_path / "spec.json")
    spec2 = FmriFeatureRecipeSpecV1.from_json(path.read_text(encoding="utf-8"))
    assert spec2.recipe_id == spec.recipe_id


def test_recipe_id_deterministic():
    spec_a = _minimal_spec()
    spec_b = _minimal_spec(recipe_name="a totally different display name")
    assert spec_a.recipe_id == spec_b.recipe_id
    assert spec_a.recipe_id == compute_recipe_id(
        dataset_id="demo_fmri", feature_set_id="fmri_connectivity_graph_v1",
        source_state="placebo", target_state="drug", requested_features=["connectivity.mean_connectivity"],
        atlas_or_parcellation="Schaefer100", max_subjects=5, max_runs=5,
        max_timepoints_per_state=100, max_total_timepoints=1000,
    )


def test_recipe_id_differs_across_identity_fields():
    base = _minimal_spec()
    other_atlas = _minimal_spec(atlas_or_parcellation="AAL")
    other_bound = _minimal_spec(max_subjects=10)
    assert base.recipe_id != other_atlas.recipe_id
    assert base.recipe_id != other_bound.recipe_id


def test_created_at_excluded_from_recipe_id():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    later = now + timedelta(days=365)
    spec_now = _minimal_spec(_now=now)
    spec_later = _minimal_spec(_now=later)
    assert spec_now.created_at != spec_later.created_at
    assert spec_now.recipe_id == spec_later.recipe_id


def test_default_connectivity_and_qc_policy_present():
    spec = _minimal_spec()
    assert spec.connectivity_policy.get("method") == "pearson_correlation"
    assert "confounds_source" in spec.qc_policy


# ── FmriDerivedFeatureRecipeManifestV1 ─────────────────────────────────


def _minimal_manifest(**overrides) -> FmriDerivedFeatureRecipeManifestV1:
    kwargs = dict(recipe_id="recipe-1", dataset_id="demo_fmri", limitations=["l"], provenance="unit test fixture")
    kwargs.update(overrides)
    return FmriDerivedFeatureRecipeManifestV1.make(**kwargs)


def test_manifest_dict_roundtrip():
    manifest = _minimal_manifest()
    d = manifest.to_dict()
    manifest2 = FmriDerivedFeatureRecipeManifestV1.from_dict(d)
    assert manifest2.to_dict() == d


def test_manifest_json_roundtrip():
    manifest = _minimal_manifest()
    text = manifest.to_json()
    manifest2 = FmriDerivedFeatureRecipeManifestV1.from_json(text)
    assert manifest2.to_dict() == manifest.to_dict()


def test_manifest_id_content_addressed():
    from datetime import datetime, timezone

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    m1 = _minimal_manifest(_now=now, features_written=4)
    m2 = _minimal_manifest(_now=now, features_written=4)
    assert m1.manifest_id == m2.manifest_id
    m3 = _minimal_manifest(_now=now, features_written=5)
    assert m1.manifest_id != m3.manifest_id


def test_manifest_records_output_paths():
    manifest = _minimal_manifest(
        output_features_path="outputs/feature_recipes/x/derived_features.csv",
        output_mapping_path="outputs/feature_recipes/x/mapping.json",
        output_summary_path="outputs/feature_recipes/x/summary.json",
    )
    assert manifest.output_features_path.endswith("derived_features.csv")
    assert manifest.output_mapping_path.endswith("mapping.json")


def test_manifest_records_skipped_inputs():
    manifest = _minimal_manifest(
        skipped_inputs=[{"subject_id": "sub-02", "reason": "constant or all-NaN parcel signal -- correlation is undefined"}],
    )
    assert manifest.skipped_inputs
