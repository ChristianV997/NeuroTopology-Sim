from pathlib import Path

import pytest

from awareness_studio.web.research_ops import build_research_snapshot, resolve_repository_file


def test_snapshot_uses_only_files_present_in_repository(tmp_path: Path):
    (tmp_path / "outputs" / "command_center" / "mock_payloads").mkdir(parents=True)
    (tmp_path / "outputs" / "run").mkdir(parents=True)
    (tmp_path / "REPORT_ds123456_fixture.md").write_text("# real fixture", encoding="utf-8")
    (tmp_path / "outputs" / "run" / "result.json").write_text("{}", encoding="utf-8")
    (tmp_path / "outputs" / "command_center" / "mock_payloads" / "status.json").write_text("{}", encoding="utf-8")

    snapshot = build_research_snapshot(tmp_path)

    assert snapshot["source"] == "repository_checkout"
    assert snapshot["counts"] == {
        "simulation_reports": 1,
        "output_artifacts": 2,
        "command_center_payloads": 1,
        "rag_artifacts": 0,
    }
    assert snapshot["simulations"][0]["dataset"] == "ds123456"


def test_file_resolution_rejects_path_traversal(tmp_path: Path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    with pytest.raises(ValueError):
        resolve_repository_file("../outside.txt", tmp_path)


def test_file_resolution_requires_existing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        resolve_repository_file("missing.md", tmp_path)
