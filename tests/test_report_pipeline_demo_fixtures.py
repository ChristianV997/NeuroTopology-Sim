"""Tests for `tests/fixtures/report_pipeline_demo.py`: every demo spec
this fixture module produces must itself validate, stay small, and never
reference a raw external dataset. Also runs the claim-guardrail scanner
over the demo fixture module's own source.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from tests.fixtures import report_pipeline_demo as demo

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MAX_FIXTURE_BYTES = 200_000  # generous ceiling for a "tiny" demo fixture


def test_mne_bids_epoch_table_recipe_demo_validates(tmp_path):
    from adapters.mne_bids_feature_recipe_schema import FeatureRecipeSpecV1

    spec_path, epoch_table_path = demo.write_mne_bids_epoch_table_recipe_demo(tmp_path)
    spec = FeatureRecipeSpecV1.from_json(spec_path.read_text(encoding="utf-8"))
    assert spec.validate() == []
    assert epoch_table_path.exists()
    assert epoch_table_path.stat().st_size < _MAX_FIXTURE_BYTES


def test_mne_bids_derived_features_demo_validates():
    with_tmp = Path(__file__).resolve().parent / "_tmp_demo_check"
    with_tmp.mkdir(exist_ok=True)
    try:
        features_path, mapping_path = demo.write_mne_bids_derived_features_demo(with_tmp)
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        from adapters.validation import validate_mapping

        assert validate_mapping(mapping) == []
        assert features_path.stat().st_size < _MAX_FIXTURE_BYTES
    finally:
        shutil.rmtree(with_tmp, ignore_errors=True)


def test_fmri_timeseries_recipe_demo_validates(tmp_path):
    from adapters.fmri_derivatives_feature_recipe_schema import FmriFeatureRecipeSpecV1

    spec_path, table_path = demo.write_fmri_timeseries_recipe_demo(tmp_path)
    spec = FmriFeatureRecipeSpecV1.from_json(spec_path.read_text(encoding="utf-8"))
    assert spec.validate() == []
    assert table_path.exists()
    assert table_path.stat().st_size < _MAX_FIXTURE_BYTES


def test_fmri_graph_summary_recipe_demo_validates(tmp_path):
    from adapters.fmri_derivatives_feature_recipe_schema import FmriFeatureRecipeSpecV1

    spec_path, gs_path = demo.write_fmri_graph_summary_recipe_demo(tmp_path)
    spec = FmriFeatureRecipeSpecV1.from_json(spec_path.read_text(encoding="utf-8"))
    assert spec.validate() == []
    assert gs_path.stat().st_size < _MAX_FIXTURE_BYTES


def test_fmri_derived_features_demo_validates(tmp_path):
    from adapters.fmri_derivatives_validation import validate_mapping

    features_path, mapping_path = demo.write_fmri_derived_features_demo(tmp_path)
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    assert validate_mapping(mapping) == []
    assert features_path.stat().st_size < _MAX_FIXTURE_BYTES


def test_existing_evidence_bundle_demo_builds_a_valid_bundle(tmp_path):
    from evidence.bundle import EvidenceBundleV1

    bundle_path = demo.build_existing_evidence_bundle_demo(tmp_path / "bundle_out")
    bundle = EvidenceBundleV1.from_json(bundle_path.read_text(encoding="utf-8"))
    assert bundle.validate(repo_root=_REPO_ROOT) == []
    assert bundle.dataset_id == "ds005620"


def test_no_demo_fixture_output_is_committed_to_tracked_outputs():
    # tests/fixtures/report_pipeline_demo.py only ever writes into a
    # caller-supplied directory (tmp_path in every test above) -- confirm
    # no stray output landed under the repo's own outputs/ tree.
    assert not (_REPO_ROOT / "outputs" / "report_packs" / "_demo_fixtures").exists()


def test_demo_fixture_module_uses_already_committed_ds005620_source_not_a_download():
    source = (_REPO_ROOT / "tests" / "fixtures" / "report_pipeline_demo.py").read_text(encoding="utf-8")
    for banned in ("requests.get(", "urllib.request", "boto3", "s3.download", "nilearn.datasets.fetch"):
        assert banned not in source
    assert "contracts" in source  # reuses already-committed repo artifacts


def test_demo_fixture_module_passes_claim_guardrail_scan():
    result = subprocess.run(
        [sys.executable, "tools/check_claim_guardrails.py", "tests/fixtures/report_pipeline_demo.py"],
        capture_output=True, text=True, cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, result.stdout + result.stderr
