"""ReportPipelineRunManifestV1: dict roundtrip and structural validation.
Synthetic fixtures only.
"""
from __future__ import annotations

from workflows.report_pipeline import ReportPipelineRunManifestV1, ReportPipelineValidationError


def _minimal_manifest(**overrides) -> ReportPipelineRunManifestV1:
    kwargs = dict(
        pipeline_id="pipeline-1", dataset_id="demo_ds", input_mode="mne_bids_derived_features",
        modality="EEG", execution_status="completed",
        limitations=["test"], provenance="unit test fixture",
    )
    kwargs.update(overrides)
    return ReportPipelineRunManifestV1.make(**kwargs)


def test_manifest_dict_roundtrip():
    manifest = _minimal_manifest()
    d = manifest.to_dict()
    manifest2 = ReportPipelineRunManifestV1.from_dict(d)
    assert manifest2.to_dict() == d


def test_manifest_json_roundtrip():
    manifest = _minimal_manifest()
    text = manifest.to_json()
    manifest2 = ReportPipelineRunManifestV1.from_json(text)
    assert manifest2.to_dict() == manifest.to_dict()


def test_manifest_write_json_roundtrip(tmp_path):
    manifest = _minimal_manifest()
    path = manifest.write_json(tmp_path / "manifest.json")
    manifest2 = ReportPipelineRunManifestV1.from_json(path.read_text(encoding="utf-8"))
    assert manifest2.run_id == manifest.run_id


def test_validate_or_raise_raises():
    manifest = _minimal_manifest(limitations=[])
    try:
        manifest.validate_or_raise()
        assert False, "expected ReportPipelineValidationError"
    except ReportPipelineValidationError:
        pass


def test_validation_requires_limitations():
    manifest = _minimal_manifest(limitations=[])
    assert any("limitations" in e for e in manifest.validate())


def test_validation_requires_provenance():
    manifest = _minimal_manifest(provenance="")
    assert any("provenance" in e for e in manifest.validate())


def test_validation_requires_pipeline_id():
    manifest = _minimal_manifest(pipeline_id="")
    assert any("pipeline_id" in e for e in manifest.validate())


def test_validation_requires_known_execution_status():
    manifest = _minimal_manifest(execution_status="not_a_real_status")
    assert any("execution_status" in e for e in manifest.validate())


def test_validation_accepts_every_known_execution_status():
    for status in ("dry_run", "completed", "completed_with_warnings", "failed"):
        manifest = _minimal_manifest(execution_status=status)
        assert manifest.validate() == [], f"{status}: {manifest.validate()}"


def test_manifest_records_steps_completed_and_skipped():
    manifest = _minimal_manifest(
        steps_planned=["a", "b", "c"], steps_completed=["a", "b"], steps_skipped=["c"],
    )
    assert manifest.steps_completed == ["a", "b"]
    assert manifest.steps_skipped == ["c"]


def test_manifest_records_errors_and_warnings():
    manifest = _minimal_manifest(execution_status="failed", errors=["boom"], warnings=["heads up"])
    assert manifest.errors == ["boom"]
    assert manifest.warnings == ["heads up"]


def test_manifest_records_generated_paths():
    manifest = _minimal_manifest(
        generated_feature_paths=["outputs/x/derived_features.csv"],
        generated_mapping_paths=["outputs/x/mapping.json"],
        transition_record_paths=["outputs/x/adapter_export/transitions/t1/TransitionRecord.json"],
        phase_space_paths=["outputs/x/adapter_export/phase_space/t1/PhaseSpaceCoordinates.json"],
        evidence_bundle_paths=["outputs/x/adapter_export/EvidenceBundle.json"],
        evidence_report_paths=["outputs/x/adapter_export/EvidenceReport.md", "outputs/x/adapter_export/EvidenceReport.json"],
        report_pack_path="outputs/x/ReportPack.json",
        registry_updated_path="outputs/x/adapter_export/registry_updated.json",
    )
    assert manifest.generated_feature_paths
    assert manifest.transition_record_paths
    assert manifest.report_pack_path.endswith("ReportPack.json")


def test_banned_phrase_in_provenance_fails():
    manifest = _minimal_manifest(provenance="this run confirms diagnosis beyond doubt")
    assert any("banned phrase" in e for e in manifest.validate())
