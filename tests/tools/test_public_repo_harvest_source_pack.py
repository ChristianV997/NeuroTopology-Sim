"""Offline, synthetic tests for the fail-closed public source packer."""
from __future__ import annotations

import ast
import hashlib
import io
import json
import stat
import zipfile
from pathlib import Path
import tarfile

import pytest

from tools.public_repo_harvest.external_systems_scorecard import scorecard_record
from tools.public_repo_harvest.license_scanner import rec as scan_license_record
from tools.public_repo_harvest.pattern_classifier import pattern_copy_mode
from tools.public_repo_harvest import source_pack
from tools.public_repo_harvest.source_pack import (
    PACK_MANIFEST_PATH,
    PACKER_VERSION,
    SOURCE_MANIFEST_SCHEMA,
    SourcePackError,
    SourcePackLimits,
    load_source_manifest,
    main as source_pack_main,
    pack_static_source,
    validate_source_manifest,
)


COMMIT = "a" * 40


def source_manifest(paths: list[str], **overrides) -> dict:
    result = {
        "schema_version": SOURCE_MANIFEST_SCHEMA,
        "source_url": "https://github.com/ExampleOrg/ExampleRepo.git/",
        "source_commit": COMMIT,
        "selected_paths": paths,
    }
    result.update(overrides)
    return result


def make_tree(root: Path, files: dict[str, bytes]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for relative, data in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return root


def read_pack(path: Path) -> tuple[dict, list[str]]:
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read(PACK_MANIFEST_PATH))
        return manifest, archive.namelist()


def test_directory_pack_is_deterministic_and_records_provenance_and_hashes(tmp_path):
    marker = tmp_path / "should-not-execute.txt"
    source = make_tree(
        tmp_path / "source",
        {"src/inert.py": f"from pathlib import Path\nPath({str(marker)!r}).write_text('ran')\n".encode()},
    )
    metadata = source_manifest(["src/inert.py"], access_date="2026-01-02")
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    result = pack_static_source(source, metadata, first)
    pack_static_source(source, metadata, second)

    assert first.read_bytes() == second.read_bytes()
    audit, names = read_pack(first)
    assert names == [PACK_MANIFEST_PATH, "src/inert.py"]
    assert audit["packer_version"] == PACKER_VERSION
    assert audit["provenance"] == {
        "canonical_source_url": "https://github.com/exampleorg/examplerepo",
        "source_commit": COMMIT,
        "access_date": "2026-01-02",
        "assertion_status": "caller_supplied_not_verified_offline",
    }
    assert audit["selected_paths"] == ["src/inert.py"]
    assert audit["files"][0]["sha256"] == hashlib.sha256(source.joinpath("src/inert.py").read_bytes()).hexdigest()
    assert audit["reuse_status"] == "blocked"
    assert audit["content_excluded"] is True  # Directory inputs do not enumerate unselected files.
    assert result == audit
    assert not marker.exists()  # The synthetic Python source was packed as bytes, never executed.


def test_secrets_binaries_credentials_git_and_caches_are_excluded(tmp_path):
    source = make_tree(
        tmp_path / "source",
        {
            "README.md": b"static readme\n",
            ".env": b"API_TOKEN=synthetic-only-token-value\n",
            ".git/config": b"[remote]\nurl=synthetic\n",
            ".cache/index.txt": b"cache bytes\n",
            ".aws/credentials": b"aws_access_key_id=synthetic\n",
            "config/private_key.txt": b"private-key placeholder\n",
            "credentials.json": b"{\"token\":\"synthetic\"}",
            "app/settings.py": b'API_KEY = "ghp_syntheticSecretValue0123456789abcdef"\n',
            "assets/logo.png": b"\x89PNG\r\n\x1a\n\x00binary",
        },
    )
    paths = [
        "README.md", ".env", ".git/config", ".cache/index.txt", ".aws/credentials",
        "config/private_key.txt", "credentials.json",
        "app/settings.py", "assets/logo.png",
    ]
    output = tmp_path / "safe.zip"
    result = pack_static_source(source, source_manifest(paths), output)
    audit, names = read_pack(output)

    assert names == [PACK_MANIFEST_PATH, "README.md"]
    assert result["content_excluded"] is True
    reasons = {entry["path"]: entry["reason"] for entry in audit["exclusions"]}
    assert reasons[".env"] == "credential_filename"
    assert reasons[".git/config"] == "cache_or_repository_metadata"
    assert reasons[".cache/index.txt"] == "cache_or_repository_metadata"
    assert reasons[".aws/credentials"] == "credential_directory"
    assert reasons["config/private_key.txt"] == "likely_secret_filename"
    assert reasons["credentials.json"] == "credential_filename"
    assert reasons["app/settings.py"] == "likely_secret_content"
    assert reasons["assets/logo.png"] == "binary_file_type"
    with zipfile.ZipFile(output) as archive:
        packed = b"".join(archive.read(name) for name in archive.namelist())
    assert b"synthetic-only-token-value" not in packed
    assert b"ghp_syntheticSecretValue" not in packed
    assert "assets/logo.png" not in audit["selected_paths"]


def test_source_manifest_rejects_traversal_drives_absolute_and_depth(tmp_path):
    for path in ("../outside.py", "src/../../outside.py", "C:/secret.txt", "/etc/passwd", r"\\server\share\x"):
        with pytest.raises(SourcePackError):
            validate_source_manifest(source_manifest([path]))
    with pytest.raises(SourcePackError, match="directory depth"):
        validate_source_manifest(source_manifest(["a/b/c/file.py"]), max_depth=3)


def test_source_manifest_rejects_duplicate_and_ambiguous_paths():
    with pytest.raises(SourcePackError, match="duplicate or case-ambiguous"):
        validate_source_manifest(source_manifest(["src/Readme.md", "src/readme.md"]))
    with pytest.raises(SourcePackError, match="case-ambiguous"):
        validate_source_manifest(source_manifest(["Readme/one.py", "readme/two.py"]))
    with pytest.raises(SourcePackError, match="unsupported fields"):
        validate_source_manifest(source_manifest(["README.md"], arbitrary="value"))


def test_malformed_manifest_duplicate_keys_and_missing_provenance_are_rejected(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(
        '{"schema_version":"PublicRepoSourceManifest.v1","schema_version":"bad"}',
        encoding="utf-8",
    )
    with pytest.raises(SourcePackError, match="duplicate JSON"):
        load_source_manifest(path)
    with pytest.raises(SourcePackError, match="source_commit or explicit access_date"):
        validate_source_manifest(
            {"schema_version": SOURCE_MANIFEST_SCHEMA, "source_url": "https://github.com/a/b", "selected_paths": ["README.md"]}
        )
    with pytest.raises(SourcePackError, match="valid YYYY-MM-DD"):
        validate_source_manifest(source_manifest(["README.md"], source_commit=None, access_date="2026-02-31"))
    date_only = validate_source_manifest(
        {
            "schema_version": SOURCE_MANIFEST_SCHEMA,
            "source_url": "https://github.com/example/project",
            "selected_paths": ["README.md"],
            "access_date": "2026-01-02",
        }
    )
    assert date_only["source_commit"] is None
    assert date_only["access_date"] == "2026-01-02"


def test_directory_symlink_escape_is_rejected_when_symlinks_are_available(tmp_path):
    outside = make_tree(tmp_path / "outside", {"secret.txt": b"outside"})
    source = tmp_path / "source"
    source.mkdir()
    try:
        (source / "escape").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlink creation is unavailable on this host")
    with pytest.raises(SourcePackError, match="symlink or junction"):
        pack_static_source(source, source_manifest(["escape/secret.txt"]), tmp_path / "escape.zip")
    assert not (tmp_path / "escape.zip").exists()


def test_zip_symlink_entry_is_rejected(tmp_path):
    archive_path = tmp_path / "symlink.zip"
    link = zipfile.ZipInfo("escape/link.txt")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(link, "../../outside.txt")
    with pytest.raises(SourcePackError, match="symlink"):
        pack_static_source(archive_path, source_manifest(["escape/link.txt"]), tmp_path / "out.zip")


def test_zip_archive_traversal_and_ambiguous_paths_are_rejected(tmp_path):
    traversal = tmp_path / "traversal.zip"
    with zipfile.ZipFile(traversal, "w") as archive:
        archive.writestr("../outside.txt", b"escape")
        archive.writestr("safe.py", b"pass\n")
    with pytest.raises(SourcePackError, match="traversal"):
        pack_static_source(traversal, source_manifest(["safe.py"]), tmp_path / "traversal-out.zip")

    ambiguous = tmp_path / "ambiguous.zip"
    with zipfile.ZipFile(ambiguous, "w") as archive:
        archive.writestr("src/A.py", b"a")
        archive.writestr("src/a.py", b"b")
    with pytest.raises(SourcePackError, match="case-ambiguous"):
        pack_static_source(ambiguous, source_manifest(["src/A.py"]), tmp_path / "ambiguous-out.zip")


def test_malformed_archive_is_rejected_without_output(tmp_path):
    archive_path = tmp_path / "broken.zip"
    archive_path.write_bytes(b"not a ZIP or TAR archive")
    output = tmp_path / "broken-out.zip"
    with pytest.raises(SourcePackError, match="TAR archive"):
        pack_static_source(archive_path, source_manifest(["README.md"]), output)
    assert not output.exists()


def test_output_is_never_overwritten_and_failed_publish_cleans_temporary_file(tmp_path, monkeypatch):
    source = make_tree(tmp_path / "source", {"README.md": b"safe\n"})
    existing = tmp_path / "existing.zip"
    existing.write_bytes(b"preserve")
    with pytest.raises(SourcePackError, match="already exists"):
        pack_static_source(source, source_manifest(["README.md"]), existing)
    assert existing.read_bytes() == b"preserve"

    def fail_link(source_name, output_name):
        raise OSError("injected no-replace publish failure")

    monkeypatch.setattr(source_pack.os, "link", fail_link)
    output = tmp_path / "failed-publish.zip"
    with pytest.raises(SourcePackError, match="atomically"):
        pack_static_source(source, source_manifest(["README.md"]), output)
    assert not output.exists()
    assert list(tmp_path.glob(".failed-publish.zip.*.tmp")) == []


def test_uncompressed_tar_source_pack_is_supported(tmp_path):
    tar_path = tmp_path / "fixture.tar"
    content = b"synthetic text only\n"
    with tarfile.open(tar_path, mode="w:") as archive:
        info = tarfile.TarInfo("repo/README.md")
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    output = tmp_path / "tar-pack.zip"

    result = pack_static_source(tar_path, source_manifest(["repo/README.md"]), output)

    assert result["source_kind"] == "tar"
    with zipfile.ZipFile(output) as archive:
        assert archive.read("repo/README.md") == content


def test_archive_limits_cover_file_count_compression_and_uncompressed_bytes(tmp_path):
    too_many = tmp_path / "too-many.zip"
    with zipfile.ZipFile(too_many, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("a.txt", b"a")
        archive.writestr("b.txt", b"b")
        archive.writestr("c.txt", b"c")
    with pytest.raises(SourcePackError, match="max_files"):
        pack_static_source(
            too_many,
            source_manifest(["a.txt"]),
            tmp_path / "many-out.zip",
            limits=SourcePackLimits(max_files=2),
        )
    with pytest.raises(SourcePackError, match="max_archive_entries"):
        pack_static_source(
            too_many,
            source_manifest(["a.txt"]),
            tmp_path / "entries-out.zip",
            limits=SourcePackLimits(max_archive_entries=2),
        )
    with pytest.raises(SourcePackError, match="max_archive_bytes"):
        pack_static_source(
            too_many,
            source_manifest(["a.txt"]),
            tmp_path / "archive-size-out.zip",
            limits=SourcePackLimits(max_archive_bytes=1),
        )

    bomb = tmp_path / "compressed.zip"
    with zipfile.ZipFile(bomb, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("repeat.txt", b"A" * 10_000)
    with pytest.raises(SourcePackError, match="compression ratio"):
        pack_static_source(
            bomb,
            source_manifest(["repeat.txt"]),
            tmp_path / "bomb-out.zip",
            limits=SourcePackLimits(max_compression_ratio=5),
        )


def test_file_total_count_depth_and_output_limits_are_enforced(tmp_path):
    source = make_tree(
        tmp_path / "source",
        {"a.txt": b"123", "b.txt": b"456", "deep/a/b/file.txt": b"x", "big.txt": b"12345"},
    )
    with pytest.raises(SourcePackError, match="maximum file count"):
        pack_static_source(
            source,
            source_manifest(["a.txt", "b.txt"]),
            tmp_path / "count.zip",
            limits=SourcePackLimits(max_files=1),
        )
    with pytest.raises(SourcePackError, match="max_file_bytes"):
        pack_static_source(
            source,
            source_manifest(["big.txt"]),
            tmp_path / "size.zip",
            limits=SourcePackLimits(max_file_bytes=4),
        )
    with pytest.raises(SourcePackError, match="max_total_bytes"):
        pack_static_source(
            source,
            source_manifest(["a.txt", "b.txt"]),
            tmp_path / "total.zip",
            limits=SourcePackLimits(max_total_bytes=5),
        )
    with pytest.raises(SourcePackError, match="directory depth"):
        pack_static_source(
            source,
            source_manifest(["deep/a/b/file.txt"]),
            tmp_path / "depth.zip",
            limits=SourcePackLimits(max_depth=3),
        )
    output = tmp_path / "too-small.zip"
    with pytest.raises(SourcePackError, match="max_output_bytes"):
        pack_static_source(
            source,
            source_manifest(["a.txt"]),
            output,
            limits=SourcePackLimits(max_output_bytes=256),
        )
    assert not output.exists()


def test_license_hint_and_found_license_do_not_establish_compatibility():
    hint_only = scan_license_record({"repo": "acme/repo", "likely_license": "MIT"})
    assert hint_only["detected_license"] == "unknown"
    assert hint_only["license_status"] == "unknown"
    assert hint_only["compatibility_status"] == "blocked_license"
    assert hint_only["can_copy_code"] is False
    assert pattern_copy_mode(["acme/repo"], {"acme/repo": hint_only}) == "adapted_reimplementation"

    found = scan_license_record({"repo": "acme/repo", "detected_license": "MIT", "license_spdx": "MIT"})
    assert found["detected_license"] == "MIT"
    assert found["license_status"] == "needs_manual_review"
    assert found["compatibility_status"] == "manual_review_required"
    assert found["can_copy_code"] is False

    conflicting = scan_license_record({"repo": "acme/repo", "detected_licenses": ["MIT", "Apache-2.0"]})
    assert conflicting["conflicting"] is True
    assert conflicting["compatibility_status"] == "blocked_license"
    assert conflicting["can_copy_code"] is False

    score = scorecard_record(
        {"repo": "acme/repo", "domain": "rag", "likely_license": "MIT", "total_priority_score": 80}, 1
    )
    assert score["license_status"] == "unknown"
    assert score["compatibility_status"] == "blocked_license"
    assert score["can_copy_code"] is False
    score_conflict = scorecard_record(
        {
            "repo": "acme/repo",
            "domain": "rag",
            "detected_license": "MIT",
            "license_spdx": "Apache-2.0",
            "license_status": "compatible",
            "compatibility_status": "safe_to_adapt",
            "review_status": "human_reviewed_compatible",
            "can_copy_code": True,
            "manual_review_required": False,
            "total_priority_score": 80,
        },
        2,
    )
    assert score_conflict["conflicting"] is True
    assert score_conflict["compatibility_status"] == "blocked_license"
    assert score_conflict["can_copy_code"] is False

    assert pattern_copy_mode(["acme/repo"], {}) == "adapted_reimplementation"
    assert pattern_copy_mode(
        ["acme/repo"], {"acme/repo": {"compatibility_status": "safe_to_adapt"}}
    ) == "adapted_reimplementation"
    assert pattern_copy_mode(
        ["acme/repo"],
        {
            "acme/repo": {
                "detected_license": "MIT",
                "detected_licenses": ["MIT"],
                "license_spdx": "MIT",
                "license_status": "compatible",
                "compatibility_status": "safe_to_adapt",
                "review_status": "human_reviewed_compatible",
                "can_copy_code": True,
                "manual_review_required": False,
                "conflicting": False,
            }
        },
    ) == "direct_copy_allowed"
    blocked_nonpermissive = {
        "acme/repo": {
            "detected_license": "GPL",
            "detected_licenses": ["GPL"],
            "license_spdx": "GPL",
            "license_status": "compatible",
            "compatibility_status": "safe_to_adapt",
            "review_status": "human_reviewed_compatible",
            "can_copy_code": True,
            "manual_review_required": False,
            "conflicting": False,
        }
    }
    assert pattern_copy_mode(["acme/repo"], blocked_nonpermissive) == "adapted_reimplementation"


def test_only_explicit_human_review_can_mark_license_compatible(tmp_path):
    source = make_tree(tmp_path / "source", {"src/module.py": b"# synthetic source\n"})
    reviewed = {
        "detected_license": "MIT",
        "license_spdx": "MIT",
        "license_status": "compatible",
        "compatibility_status": "safe_to_adapt",
        "review_status": "human_reviewed_compatible",
        "can_copy_code": True,
        "manual_review_required": False,
    }
    manifest = pack_static_source(
        source,
        source_manifest(["src/module.py"], license_record=reviewed),
        tmp_path / "reviewed.zip",
    )
    assert manifest["reuse_status"] == "human_reviewed_compatible"

    conflict = dict(reviewed, detected_licenses=["MIT", "Apache-2.0"])
    blocked = pack_static_source(
        source,
        source_manifest(["src/module.py"], license_record=conflict),
        tmp_path / "conflict.zip",
    )
    assert blocked["reuse_status"] == "blocked"
    assert "conflicting_license_information" in blocked["license_evaluation"]["reuse_block_reasons"]


def test_cli_packs_only_synthetic_local_source_and_reports_status(tmp_path, capsys):
    source = make_tree(tmp_path / "source", {"README.md": b"fixture only\n"})
    manifest_path = tmp_path / "source-manifest.json"
    manifest_path.write_text(json.dumps(source_manifest(["README.md"])), encoding="utf-8")
    output = tmp_path / "cli-pack.zip"

    result = source_pack_main(
        ["--source", str(source), "--source-manifest", str(manifest_path), "--out", str(output)]
    )

    assert result == 0
    assert output.is_file()
    assert "PACKED:" in capsys.readouterr().out


def test_packer_has_no_dynamic_execution_or_network_client_imports():
    tree = ast.parse(Path(source_pack.__file__).read_text(encoding="utf-8"))
    forbidden_modules = {"subprocess", "importlib", "requests", "httpx", "socket"}
    imported = set()
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)

    assert imported.isdisjoint(forbidden_modules)
    assert calls.isdisjoint({"exec", "eval", "system", "popen", "Popen", "run"})
