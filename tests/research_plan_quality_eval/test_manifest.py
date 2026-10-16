from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from tools.research_plan_quality_eval.errors import ManifestError
from tools.research_plan_quality_eval.harness import DEFAULT_MANIFEST
from tools.research_plan_quality_eval.manifest import (
    load_labels,
    load_manifest,
    load_plan_records,
    rubric_dimensions_sha256,
    rubric_source_sha256,
)

from .conftest import rehash_labels, rehash_plan, rewrite_json


def test_shipped_manifest_verifies_every_file_hash_and_rubric_identity():
    manifest = load_manifest(DEFAULT_MANIFEST)
    assert manifest.fixture_set_version == "v1"
    assert len(manifest.entries) == 10
    assert manifest.rubric_dimensions_sha256 == rubric_dimensions_sha256()
    assert manifest.rubric_source_sha256 == rubric_source_sha256()


def test_tampered_plan_file_is_rejected(copy_fixture_tree):
    manifest_path = copy_fixture_tree()
    plan_file = manifest_path.parent / "plans" / "P01.json"
    plan_file.write_text(plan_file.read_text().replace("forty", "forty-one"), encoding="utf-8")
    with pytest.raises(ManifestError, match="hash mismatch"):
        load_manifest(manifest_path)


def test_plan_changed_after_verification_is_rejected_at_record_load(copy_fixture_tree):
    manifest = load_manifest(copy_fixture_tree())
    target = manifest.entries[0].plan_path
    target.write_text(target.read_text().replace("forty", "forty-one"), encoding="utf-8")
    with pytest.raises(ManifestError, match="changed after the manifest was verified"):
        load_plan_records(manifest)


def test_missing_plan_file_is_rejected(copy_fixture_tree):
    manifest_path = copy_fixture_tree()
    (manifest_path.parent / "plans" / "P05.json").unlink()
    with pytest.raises(ManifestError, match="missing"):
        load_manifest(manifest_path)


def test_labels_are_not_verified_on_the_evaluation_path(copy_fixture_tree):
    manifest_path = copy_fixture_tree()
    (manifest_path.parent / "labels.json").write_text("{}", encoding="utf-8")
    manifest = load_manifest(manifest_path)
    assert len(load_plan_records(manifest)) == 10
    with pytest.raises(ManifestError, match="hash mismatch"):
        load_labels(manifest)


def test_plan_loading_never_opens_the_label_file(copy_fixture_tree):
    manifest = load_manifest(copy_fixture_tree())
    unreadable = dataclasses.replace(manifest, labels_path=Path("/nonexistent/labels.json"))
    assert len(load_plan_records(unreadable)) == 10


def test_duplicate_fixture_id_is_rejected(copy_fixture_tree):
    manifest_path = copy_fixture_tree()
    rewrite_json(manifest_path, lambda d: d["records"][1].update(fixture_id=d["records"][0]["fixture_id"]))
    with pytest.raises(ManifestError, match="duplicate fixture_id"):
        load_manifest(manifest_path)


def test_unknown_split_role_is_rejected(copy_fixture_tree):
    manifest_path = copy_fixture_tree()
    rewrite_json(manifest_path, lambda d: d["records"][0].update(split="test_set"))
    with pytest.raises(ManifestError, match="split must be one of"):
        load_manifest(manifest_path)


def test_group_spanning_both_splits_is_rejected(copy_fixture_tree):
    manifest_path = copy_fixture_tree()
    rewrite_json(manifest_path, lambda d: d["records"][0].update(group_id=d["records"][9]["group_id"]))
    with pytest.raises(ManifestError, match="assigned to both"):
        load_manifest(manifest_path)


@pytest.mark.parametrize("bad_path", ["../P01.json", "/etc/passwd", "plans/../../escape.json", ""])
def test_paths_escaping_the_fixture_root_are_rejected(copy_fixture_tree, bad_path):
    manifest_path = copy_fixture_tree()
    rewrite_json(manifest_path, lambda d: d["records"][0].update(plan_file=bad_path))
    with pytest.raises(ManifestError):
        load_manifest(manifest_path)


def test_rubric_source_drift_invalidates_the_manifest(copy_fixture_tree):
    manifest_path = copy_fixture_tree()
    rewrite_json(manifest_path, lambda d: d["rubric"].update(source_sha256="0" * 64))
    with pytest.raises(ManifestError, match="rubric source changed"):
        load_manifest(manifest_path)


def test_rubric_dimension_drift_invalidates_the_manifest(copy_fixture_tree):
    manifest_path = copy_fixture_tree()
    rewrite_json(manifest_path, lambda d: d["rubric"].update(dimensions_sha256="0" * 64))
    with pytest.raises(ManifestError, match="dimensions changed"):
        load_manifest(manifest_path)


def test_non_synthetic_manifest_is_rejected(copy_fixture_tree):
    manifest_path = copy_fixture_tree()
    rewrite_json(manifest_path, lambda d: d.update(synthetic=False))
    with pytest.raises(ManifestError, match="synthetic"):
        load_manifest(manifest_path)


def test_malformed_manifest_json_is_rejected(copy_fixture_tree):
    manifest_path = copy_fixture_tree()
    manifest_path.write_text('{"schema_version": NaN}', encoding="utf-8")
    with pytest.raises(ManifestError):
        load_manifest(manifest_path)


def test_wrong_manifest_schema_is_rejected(copy_fixture_tree):
    manifest_path = copy_fixture_tree()
    rewrite_json(manifest_path, lambda d: d.update(schema_version="NTS.Other.v9"))
    with pytest.raises(ManifestError, match="schema_version"):
        load_manifest(manifest_path)


def test_empty_records_list_is_rejected(copy_fixture_tree):
    manifest_path = copy_fixture_tree()
    rewrite_json(manifest_path, lambda d: d.update(records=[]))
    with pytest.raises(ManifestError, match="non-empty"):
        load_manifest(manifest_path)


def test_relabelled_labels_file_is_rejected_on_label_load(copy_fixture_tree):
    manifest_path = copy_fixture_tree()
    labels_path = manifest_path.parent / "labels.json"
    labels = json.loads(labels_path.read_text())
    labels["adjudication"]["independent"] = True
    labels_path.write_text(json.dumps(labels), encoding="utf-8")
    rehash_labels(manifest_path)
    with pytest.raises(ManifestError, match="independent=false"):
        load_labels(load_manifest(manifest_path))


def test_rehashed_fixture_edit_loads_cleanly(copy_fixture_tree):
    manifest_path = copy_fixture_tree()
    plan_file = manifest_path.parent / "plans" / "P02.json"
    plan_file.write_text(plan_file.read_text().replace("thirty-six", "thirty-seven"), encoding="utf-8")
    rehash_plan(manifest_path, "fx-v1-P02")
    assert len(load_manifest(manifest_path).entries) == 10
