"""Valid-ref coverage for the stacked reconciliation integration."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from tools.integration_reconciliation import github_source, reconcile
from tools.integration_reconciliation.models import WorkOrder


def _git(repo: Path, *args: str) -> None:
    env = dict(os.environ)
    env.update({
        "GIT_AUTHOR_NAME": "integration-repair",
        "GIT_AUTHOR_EMAIL": "integration-repair@example.invalid",
        "GIT_COMMITTER_NAME": "integration-repair",
        "GIT_COMMITTER_EMAIL": "integration-repair@example.invalid",
    })
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)


def _valid_stacked_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "integration-repair")
    _git(repo, "config", "user.email", "integration-repair@example.invalid")
    (repo / "README.md").write_text("root\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "root")

    _git(repo, "checkout", "-q", "-b", "feature-a")
    (repo / "shared").mkdir()
    (repo / "shared" / "a.py").write_text("value = 1\n", encoding="utf-8")
    _git(repo, "add", "shared/a.py")
    _git(repo, "commit", "-q", "-m", "feature")

    _git(repo, "checkout", "-q", "-b", "stacked-on-feature-a")
    (repo / "stacked_only.py").write_text("stacked = True\n", encoding="utf-8")
    _git(repo, "add", "stacked_only.py")
    _git(repo, "commit", "-q", "-m", "stacked")
    _git(repo, "checkout", "-q", "main")

    for branch in ("main", "feature-a", "stacked-on-feature-a"):
        _git(repo, "update-ref", f"refs/remotes/origin/{branch}", f"refs/heads/{branch}")
    return repo


def test_reconcile_exposes_stack_and_effective_diff_for_valid_refs(tmp_path):
    repo = _valid_stacked_repo(tmp_path)
    snapshot = {
        "schema": github_source.SNAPSHOT_SCHEMA,
        "pull_requests": [
            {
                "number": 1,
                "head_ref": "feature-a",
                "base_ref": "main",
                "state": "open",
                "draft": False,
                "merged": False,
                "mergeable_state": "clean",
                "checks": {"tests": "success"},
            },
            {
                "number": 2,
                "head_ref": "stacked-on-feature-a",
                "base_ref": "feature-a",
                "state": "open",
                "draft": False,
                "merged": False,
                "mergeable_state": "unstable",
                "checks": {"tests": "success"},
            },
        ],
    }
    work_orders = (
        WorkOrder("base", "base", expected_branch="feature-a", reported_pr_number=1),
        WorkOrder(
            "dependent", "dependent", expected_branch="stacked-on-feature-a", reported_pr_number=2
        ),
    )

    report = reconcile.reconcile(repo, work_orders, target_ref="origin/main", github_snapshot=snapshot)
    base = next(entry for entry in report.entries if entry.work_order.work_order_id == "base")
    dependent = next(entry for entry in report.entries if entry.work_order.work_order_id == "dependent")

    assert dependent.stack is not None
    assert dependent.stack.is_stacked.value is True
    assert dependent.stack.base_work_order_id.value == "base"
    assert dependent.effective_changed_files is not None
    assert dependent.effective_changed_files.value == ["stacked_only.py"]
    assert dependent.branch.changed_files.value == ["shared/a.py", "stacked_only.py"]
    assert base.stack is not None
    assert base.stack.dependents.value == ["dependent"]
    assert report.possible_duplicates == []
    assert report.superseded_work == []
