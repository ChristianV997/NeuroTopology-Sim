import json

import pytest

from research_runtime.envelope import RunEnvelope, build_code_manifest, build_input_manifest, canonical_json, sha256_text
from research_runtime.protocol import ProtocolSpec, deterministic_subject_split
from research_runtime.stage_policy import StageLock, StagePolicyError


def test_protocol_and_subject_split_are_deterministic():
    spec = ProtocolSpec("p", "h", "ds003969", "ds003816")
    spec.validate()
    first = deterministic_subject_split("ds003969", ["sub-03", "sub-01", "sub-02"], seed=7, development_fraction=.7)
    second = deterministic_subject_split("ds003969", ["sub-02", "sub-01", "sub-03"], seed=7, development_fraction=.7)
    assert first == second
    assert sorted(first["development"] + first["confirmatory"]) == ["sub-01", "sub-02", "sub-03"]
    assert sha256_text(canonical_json(spec.to_dict())) == sha256_text(canonical_json(spec.to_dict()))


def test_protocol_rejects_cloud_execution():
    with pytest.raises(ValueError, match="cloud"):
        ProtocolSpec("p", "h", "a", "b", cloud_enabled=True).validate()


def test_lock_is_single_use_and_hash_bound():
    lock = StageLock.issue("confirmatory", "protocol-hash", "run-1")
    lock.authorize("protocol-hash", "run-1")
    lock.consume("protocol-hash", "run-1")
    with pytest.raises(StagePolicyError, match="already"):
        lock.consume("protocol-hash", "run-1")
    with pytest.raises(StagePolicyError, match="authorization"):
        StageLock.issue("external", "hash", "run").authorize("other", "run")


def test_input_manifest_hashes_files(tmp_path):
    source = tmp_path / "input.txt"
    source.write_text("stable", encoding="utf-8")
    manifest = build_input_manifest([source], root=tmp_path)
    assert manifest["files"][0]["path"] == "input.txt"
    assert manifest["files"][0]["bytes"] == 6
    code = build_code_manifest([source], root=tmp_path, git_commit="abc", dirty_tree=True)
    assert code["git_commit"] == "abc"
    assert code["dirty_tree"] is True


def test_envelope_is_write_once_and_requires_all_files(tmp_path):
    root = tmp_path / "run"
    envelope = RunEnvelope(root, "development", "run-1", {"protocol": 1}, {"hypothesis": 1})
    envelope.initialize(code_manifest={}, input_manifest={}, stage_lock={})
    with pytest.raises(FileExistsError):
        envelope.write_once("protocol.json", {})
    for name in envelope.REQUIRED_FILES:
        if not (root / name).exists():
            envelope.write_once(name, {})
    envelope.finalize({})
    assert json.loads((root / "protocol.json").read_text()) == {"protocol": 1}
