"""CLI contract for scripts/build_release_manifest.py: the stderr summary names technical reachability and release state."""
import importlib.util
import sys
from pathlib import Path

from tests.release_manifest.conftest import commit_of

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build_release_manifest.py"


def _load_cli():
    spec = importlib.util.spec_from_file_location("build_release_manifest_cli", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_stderr_summary_separates_technical_reachability_from_release_state(git_repo, monkeypatch, capsys, tmp_path):
    head = commit_of(git_repo, "main")
    monkeypatch.setattr(sys, "argv", [
        "build_release_manifest.py",
        "--repo-path", str(git_repo),
        "--repository", "ChristianV997/NeuroTopology-Sim",
        "--target-branch", "main",
        "--integration-branch", "main",
        "--source-commit", head,
        "--json-out", str(tmp_path / "manifest.json"),
    ])

    assert _load_cli().main() == 0

    stderr = capsys.readouterr().err
    assert "merge_state=merged_into_main" in stderr
    assert "technical_target_reachability=True" in stderr
    assert "release_state=inconclusive" in stderr
    assert "release_eligibility=False" in stderr
    assert "merge_eligibility" not in stderr
