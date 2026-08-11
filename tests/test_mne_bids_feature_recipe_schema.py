"""FeatureRecipeSpecV1 / DerivedFeatureRecipeManifestV1: dict roundtrip and
deterministic ID behavior. Synthetic fixtures only.
"""
from __future__ import annotations

from adapters.mne_bids_feature_recipe_schema import (
    DerivedFeatureRecipeManifestV1,
    FeatureRecipeSpecV1,
    compute_recipe_id,
)


def _minimal_spec(**overrides) -> FeatureRecipeSpecV1:
    kwargs = dict(
        dataset_id="demo_bids_eeg",
        feature_set_id="mne_bids_spectral_v1",
        source_state="rest",
        target_state="task",
        requested_features=["spectral.alpha_power"],
        max_subjects=5,
        max_runs=5,
        max_epochs_per_state=10,
        max_total_epochs=100,
        event_state_mapping={"rest_marker": "rest", "task_marker": "task"},
        feature_definitions={"spectral.alpha_power": "Mean relative alpha-band power over valid epochs."},
        limitations=["test"],
        provenance="unit test fixture",
    )
    kwargs.update(overrides)
    return FeatureRecipeSpecV1.make(**kwargs)


def test_spec_dict_roundtrip():
    spec = _minimal_spec()
    d = spec.to_dict()
    spec2 = FeatureRecipeSpecV1.from_dict(d)
    assert spec2.to_dict() == d


def test_spec_json_roundtrip():
    spec = _minimal_spec()
    text = spec.to_json()
    spec2 = FeatureRecipeSpecV1.from_json(text)
    assert spec2.to_dict() == spec.to_dict()


def test_spec_write_json_roundtrip(tmp_path):
    spec = _minimal_spec()
    path = spec.write_json(tmp_path / "spec.json")
    spec2 = FeatureRecipeSpecV1.from_json(path.read_text(encoding="utf-8"))
    assert spec2.recipe_id == spec.recipe_id


def test_recipe_id_deterministic():
    spec_a = _minimal_spec()
    spec_b = _minimal_spec(recipe_name="a totally different display name")
    assert spec_a.recipe_id == spec_b.recipe_id
    assert spec_a.recipe_id == compute_recipe_id(
        dataset_id="demo_bids_eeg", feature_set_id="mne_bids_spectral_v1", source_state="rest", target_state="task",
        requested_features=["spectral.alpha_power"], max_subjects=5, max_runs=5, max_epochs_per_state=10, max_total_epochs=100,
    )


def test_recipe_id_differs_across_identity_fields():
    base = _minimal_spec()
    other_state = _minimal_spec(target_state="sleep", event_state_mapping={"rest_marker": "rest", "sleep_marker": "sleep"})
    other_bound = _minimal_spec(max_subjects=10)
    assert base.recipe_id != other_state.recipe_id
    assert base.recipe_id != other_bound.recipe_id


def test_created_at_excluded_from_recipe_id():
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    later = now + timedelta(days=365)
    spec_now = _minimal_spec(_now=now)
    spec_later = _minimal_spec(_now=later)
    assert spec_now.created_at != spec_later.created_at
    assert spec_now.recipe_id == spec_later.recipe_id


def test_default_frequency_bands_and_epoch_window_present():
    spec = _minimal_spec()
    assert "alpha" in spec.frequency_bands
    assert spec.epoch_window.get("length_seconds") == 2.0


# ── DerivedFeatureRecipeManifestV1 ────────────────────────────────────────


def _minimal_manifest(**overrides) -> DerivedFeatureRecipeManifestV1:
    kwargs = dict(
        recipe_id="recipe-1",
        dataset_id="demo_bids_eeg",
        limitations=["l"],
        provenance="unit test fixture",
    )
    kwargs.update(overrides)
    return DerivedFeatureRecipeManifestV1.make(**kwargs)


def test_manifest_dict_roundtrip():
    manifest = _minimal_manifest()
    d = manifest.to_dict()
    manifest2 = DerivedFeatureRecipeManifestV1.from_dict(d)
    assert manifest2.to_dict() == d


def test_manifest_json_roundtrip():
    manifest = _minimal_manifest()
    text = manifest.to_json()
    manifest2 = DerivedFeatureRecipeManifestV1.from_json(text)
    assert manifest2.to_dict() == manifest.to_dict()


def test_manifest_id_deterministic_for_identical_content():
    from datetime import datetime, timezone

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    m1 = _minimal_manifest(_now=now, features_written=4)
    m2 = _minimal_manifest(_now=now, features_written=4)
    assert m1.manifest_id == m2.manifest_id


def test_manifest_records_output_paths():
    manifest = _minimal_manifest(
        output_features_path="outputs/feature_recipes/x/derived_features.csv",
        output_mapping_path="outputs/feature_recipes/x/mapping.json",
        output_summary_path="outputs/feature_recipes/x/summary.json",
    )
    assert manifest.output_features_path.endswith("derived_features.csv")
    assert manifest.output_mapping_path.endswith("mapping.json")


def test_manifest_records_skipped_events_and_runs():
    manifest = _minimal_manifest(
        skipped_runs=[{"file": "sub-02/eeg/sub-02_task-x_events.tsv", "reason": "no sibling raw EEG file found"}],
        skipped_events=[{"trial_type": "blink", "reason": "not present in event_state_mapping (never inferred)"}],
    )
    assert manifest.skipped_runs
    assert manifest.skipped_events
