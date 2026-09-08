"""scripts/verify_integration_state.py exercised as a real subprocess
against the local git fixture repo -- no network."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "verify_integration_state.py"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_SCRIPT), *args], capture_output=True, text=True, timeout=60)


def test_cli_runs_and_exits_zero_with_no_contradictions(state_fixture_repo):
    result = _run_cli(
        "--repo-path", str(state_fixture_repo["repo"]),
        "--integration-branch", "origin/integration", "--main-ref", "origin/main",
        "--handoff-claim", f"round1={state_fixture_repo['round1']}",
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema"].startswith("NTS.IntegrationStateLockReport")
    assert payload["contradictory_handoffs"] is False


def test_cli_exits_nonzero_on_contradictory_handoffs(state_fixture_repo):
    result = _run_cli(
        "--repo-path", str(state_fixture_repo["repo"]),
        "--integration-branch", "origin/integration", "--main-ref", "origin/main",
        "--handoff-claim", f"current={state_fixture_repo['round3']}",
        "--handoff-claim", f"rogue={state_fixture_repo['diverged']}",
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["contradictory_handoffs"] is True


def test_cli_writes_json_and_markdown(state_fixture_repo, tmp_path):
    out_dir = tmp_path / "out"
    result = _run_cli(
        "--repo-path", str(state_fixture_repo["repo"]),
        "--integration-branch", "origin/integration", "--main-ref", "origin/main",
        "--output-dir", str(out_dir),
    )
    assert result.returncode == 0, result.stderr
    assert (out_dir / "report.json").exists()
    assert (out_dir / "report.md").exists()


def test_cli_accepts_a_pr_snapshot_file(state_fixture_repo, tmp_path):
    snapshot_path = tmp_path / "pr.json"
    snapshot_path.write_text(json.dumps({
        "number": 236, "state": "open", "draft": False, "merged": False,
        "head_sha": state_fixture_repo["round3"],
    }), encoding="utf-8")
    result = _run_cli(
        "--repo-path", str(state_fixture_repo["repo"]),
        "--integration-branch", "origin/integration", "--main-ref", "origin/main",
        "--pr-snapshot", str(snapshot_path),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["pr_number"]["value"] == 236
