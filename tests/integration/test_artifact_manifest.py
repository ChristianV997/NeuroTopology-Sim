"""Deterministic manifest generation.

Determinism claim, precisely: given the same artifact bytes and the same
declared metadata, `artifact_manifest.build_manifest`/`ArtifactManifest.
to_dict()` produce byte-identical JSON, regardless of filesystem iteration
order. This is tested at the manifest-builder level with fixed byte
content rather than through two full `assemble_ecosystem_run.assemble()`
calls, because a full run's `RunRecord.json` legitimately contains a
wall-clock `created_at` field (RunRecordV1 is canonical and untouched by
this integration -- see docs/integration_acceptance.md, "Artifact
contract"), so two real runs' manifests will differ in that one hash even
though the manifest *builder* itself is fully deterministic.
"""
from __future__ import annotations

import json

from tools.integration_bridge import artifact_manifest


def _write_fixture_artifacts(output_dir):
    (output_dir / "b.json").write_text('{"b": 2}\n', encoding="utf-8")
    (output_dir / "a.json").write_text('{"a": 1}\n', encoding="utf-8")


def test_manifest_is_byte_identical_across_two_builds(tmp_path):
    out1 = tmp_path / "run1"
    out1.mkdir()
    _write_fixture_artifacts(out1)
    out2 = tmp_path / "run2"
    out2.mkdir()
    _write_fixture_artifacts(out2)

    manifest1 = artifact_manifest.build_manifest(
        run_id="fixed-run-id", output_dir=out1,
        artifact_relative_paths=["b.json", "a.json"],  # deliberately unsorted input order
        metadata={"z": 1, "a": 2},
    )
    manifest2 = artifact_manifest.build_manifest(
        run_id="fixed-run-id", output_dir=out2,
        artifact_relative_paths=["a.json", "b.json"],  # different input order
        metadata={"a": 2, "z": 1},  # different dict insertion order
    )
    assert manifest1.to_json() == manifest2.to_json()


def test_manifest_entries_are_sorted_by_relative_path(tmp_path):
    out = tmp_path / "run"
    out.mkdir()
    _write_fixture_artifacts(out)
    manifest = artifact_manifest.build_manifest(
        run_id="r", output_dir=out, artifact_relative_paths=["b.json", "a.json"], metadata={},
    )
    paths = [entry["relative_path"] for entry in manifest.to_dict()["artifacts"]]
    assert paths == sorted(paths)


def test_manifest_hash_changes_if_artifact_bytes_change(tmp_path):
    out = tmp_path / "run"
    out.mkdir()
    (out / "a.json").write_text('{"a": 1}\n', encoding="utf-8")
    manifest1 = artifact_manifest.build_manifest(
        run_id="r", output_dir=out, artifact_relative_paths=["a.json"], metadata={},
    )
    (out / "a.json").write_text('{"a": 2}\n', encoding="utf-8")
    manifest2 = artifact_manifest.build_manifest(
        run_id="r", output_dir=out, artifact_relative_paths=["a.json"], metadata={},
    )
    assert manifest1.to_dict()["artifacts"][0]["sha256"] != manifest2.to_dict()["artifacts"][0]["sha256"]


def test_write_manifest_round_trips_through_json(tmp_path):
    out = tmp_path / "run"
    out.mkdir()
    _write_fixture_artifacts(out)
    manifest = artifact_manifest.build_manifest(
        run_id="r", output_dir=out, artifact_relative_paths=["a.json", "b.json"], metadata={"k": "v"},
    )
    path = artifact_manifest.write_manifest(manifest, out / "manifest.json")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded == manifest.to_dict()
