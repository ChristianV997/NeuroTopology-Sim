"""scripts/verify_integration_reconciliation.py exercised as a real
subprocess against a local git fixture repo -- confirms the CLI wiring
itself, not just the library functions."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "verify_integration_reconciliation.py"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        capture_output=True, text=True, timeout=60,
    )


def test_cli_runs_without_a_snapshot_and_exits_zero(git_fixture_repo):
    result = _run_cli("--repo-path", str(git_fixture_repo), "--target-ref", "origin/main",
                       "--dashboard-src", str(git_fixture_repo / "no_such_dashboard"))
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema"].startswith("NTS.IntegrationReconciliationReport")


def test_cli_writes_json_and_markdown_to_output_dir(git_fixture_repo, tmp_path):
    out_dir = tmp_path / "out"
    result = _run_cli(
        "--repo-path", str(git_fixture_repo), "--target-ref", "origin/main",
        "--dashboard-src", str(git_fixture_repo / "no_such_dashboard"),
        "--output-dir", str(out_dir),
    )
    assert result.returncode == 0, result.stderr
    assert (out_dir / "report.json").exists()
    assert (out_dir / "report.md").exists()
    payload = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    assert "entries" in payload


def test_cli_accepts_a_github_snapshot_file(git_fixture_repo, tmp_path):
    snapshot = {
        "schema": "NTS.GitHubReconciliationSnapshot.v1",
        "pull_requests": [
            {"number": 1, "head_ref": "feature-a", "state": "open", "draft": False,
             "merged": False, "mergeable_state": "clean", "checks": {"tests": "success"}},
        ],
    }
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    out_dir = tmp_path / "out"
    result = _run_cli(
        "--repo-path", str(git_fixture_repo), "--target-ref", "origin/main",
        "--github-snapshot", str(snapshot_path),
        "--dashboard-src", str(git_fixture_repo / "no_such_dashboard"),
        "--output-dir", str(out_dir),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    # This CLI run uses the real default_registry(), not the fixture repo's
    # own branch names -- so no work order here matches "feature-a". This
    # test only proves the snapshot file is accepted and parsed without
    # error; PR-matching semantics are covered by test_reconcile.py against
    # a work-order tuple built for the fixture repo's own branches.
    assert len(payload["entries"]) == 12
