"""Safety: output-dir, no-network, no-write leak, no solver, read-only git."""

from __future__ import annotations

from pathlib import Path

import pytest

from ops.research_cycle.cli import main as cli_main
from ops.research_cycle.exit_codes import BLOCKED
from ops.research_cycle.safety import (
    SafetyError,
    assert_allowed_command,
    forbidden_reason,
    require_output_dir,
    sanitize_env,
    solver_reason,
)


def test_missing_output_dir_is_blocked():
    with pytest.raises(SafetyError, match="output-dir"):
        require_output_dir(None)
    with pytest.raises(SafetyError, match="output-dir"):
        require_output_dir("")
    assert cli_main(["audit"]) == BLOCKED
    assert cli_main(["audit", "--steps", "repository_state"]) == BLOCKED


def test_output_dir_is_created(tmp_path: Path):
    target = tmp_path / "out"
    resolved = require_output_dir(target)
    assert resolved.is_dir()


def test_write_outside_output_dir_blocked(tmp_path: Path):
    out = tmp_path / "allowed"
    out.mkdir()
    leak = tmp_path / "outside.json"
    with pytest.raises(SafetyError, match="outside"):
        assert_allowed_command(
            ["python", "scripts/validate_research_claims.py", "--output", str(leak)],
            allow_solver=False,
            repo_root=tmp_path,
            output_dir=out,
        )

    leak.write_text("existing", encoding="utf-8")
    with pytest.raises(SafetyError, match="outside"):
        assert_allowed_command(
            ["python", "tool.py", "--output", str(leak)],
            allow_solver=False,
            repo_root=tmp_path,
            output_dir=out,
        )


def test_no_network_default_blocks_urls_and_allow_network():
    assert forbidden_reason(["python", "x.py", "--url", "https://example.com/data"]) is not None
    assert forbidden_reason(["python", "-m", "dataset_acquisition.export_plan", "--allow-network"]) is not None
    assert "wget" in (forbidden_reason(["wget ", "https://x"]) or "").lower() or forbidden_reason(["wget ", "https://x"])


def test_sanitize_env_clears_proxies():
    env = sanitize_env(
        {
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "PATH": "/usr/bin",
        }
    )
    assert "HTTP_PROXY" not in env
    assert "HTTPS_PROXY" not in env
    assert env["NO_NETWORK"] == "1"
    assert env["RCOP_NO_NETWORK"] == "1"


def test_forbidden_git_mutations():
    assert forbidden_reason(["git", "merge", "main"]) is not None
    assert forbidden_reason(["git", "reset", "--hard"]) is not None
    assert forbidden_reason(["git", "push", "--force"]) is not None
    assert forbidden_reason(["git", "-C", "/tmp/repo", "rev-parse", "HEAD"]) is None
    assert forbidden_reason(["git", "-C", "/tmp/repo", "status", "--porcelain"]) is None


def test_solver_requires_opt_in():
    argv = ["python", "scripts/run_research_campaign.py"]
    assert solver_reason(argv, allow_solver=False) is not None
    campaign = ["python", "scripts/run_benchmark_matrix.py", "--matrix", "m.json", "--output", "o"]
    assert solver_reason(campaign, allow_solver=False) is not None
    campaign_dry = campaign + ["--dry-run"]
    assert solver_reason(campaign_dry, allow_solver=False) is None
