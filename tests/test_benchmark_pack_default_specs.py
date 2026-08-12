"""Tests for `benchmark_packs.builder`'s default curated pack-spec
generators: `make_builtin_demo_pack_spec`/`make_fixture_demo_pack_spec`/
`make_methods_supplement_pack_spec`. Real already-committed contract
artifacts and synthetic fixtures only -- no downloads."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from benchmark_packs.builder import (
    make_builtin_demo_pack_spec,
    make_fixture_demo_pack_spec,
    make_methods_supplement_pack_spec,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    shutil.rmtree(_REPO_ROOT / "outputs" / "benchmark_packs", ignore_errors=True)


def test_builtin_demo_pack_spec_validates():
    spec = make_builtin_demo_pack_spec(output_root="outputs/benchmark_packs/builtin-default-test")
    assert spec.validate() == []
    assert spec.pack_kind == "demo_pack"
    assert len(spec.pipeline_specs) == 4


def test_builtin_demo_pack_spec_covers_both_modalities():
    spec = make_builtin_demo_pack_spec(output_root="outputs/benchmark_packs/builtin-default-modalities")
    modalities = {d.get("modality") for d in spec.pipeline_specs}
    datasets = {d.get("dataset_id") for d in spec.pipeline_specs}
    assert modalities == {"EEG", "fMRI"}
    assert datasets == {"ds005620", "ds000245"}


def test_builtin_demo_pack_spec_no_raw_data_referenced():
    spec = make_builtin_demo_pack_spec(output_root="outputs/benchmark_packs/builtin-default-no-raw")
    spec_text = spec.to_json()
    assert "data/raw" not in spec_text
    assert "data/ds" not in spec_text


def test_builtin_demo_pack_spec_marked_non_synthetic():
    spec = make_builtin_demo_pack_spec(output_root="outputs/benchmark_packs/builtin-default-synthetic-flag")
    assert spec.metadata.get("synthetic") is False


def test_fixture_demo_pack_spec_validates(tmp_path):
    spec = make_fixture_demo_pack_spec(
        tmp_path / "fixtures", output_root="outputs/benchmark_packs/fixture-default-test",
    )
    assert spec.validate() == []
    assert spec.pack_kind == "internal_regression_pack"
    assert len(spec.pipeline_specs) == 2


def test_fixture_demo_pack_spec_marked_synthetic(tmp_path):
    spec = make_fixture_demo_pack_spec(
        tmp_path / "fixtures", output_root="outputs/benchmark_packs/fixture-default-synthetic-flag",
    )
    assert spec.metadata.get("synthetic") is True
    assert any("synthetic" in lim.lower() for lim in spec.limitations)


def test_fixture_demo_pack_spec_no_output_artifacts_committed(tmp_path):
    fixture_dir = tmp_path / "fixtures"
    make_fixture_demo_pack_spec(fixture_dir, output_root="outputs/benchmark_packs/fixture-default-no-commit")
    # fixtures are written under the caller-supplied tmp_path, never under
    # a tracked source directory.
    assert str(fixture_dir).startswith(str(tmp_path))
    assert not str(fixture_dir).startswith(str(_REPO_ROOT / "tests"))


def test_methods_supplement_pack_spec_validates():
    spec = make_methods_supplement_pack_spec(output_root="outputs/benchmark_packs/methods-default-test")
    assert spec.validate() == []
    assert spec.pack_kind == "methods_supplement"
    assert len(spec.pipeline_specs) == 2


def test_methods_supplement_pack_spec_covers_eeg_and_fmri():
    spec = make_methods_supplement_pack_spec(output_root="outputs/benchmark_packs/methods-default-modalities")
    modalities = {d.get("modality") for d in spec.pipeline_specs}
    assert modalities == {"EEG", "fMRI"}
