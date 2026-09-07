"""Requirements 10 and 11: whether reported-merged PRs actually appear in
the integration branch's history, and whether integrated changes are
merged into main -- with the explicit rule that a local merge commit's
mere presence is NEVER, by itself, treated as proof a PR's authoritative
`merged` state is true.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from . import git_source
from .models import Evidence, PRSnapshot


def verify_integrated_pr_history(
    repo_path: Path, integration_branch_ref: str, pr_numbers: tuple[int, ...]
) -> list[dict]:
    """For each PR number a handoff claims was integrated, search the
    integration branch's own commit log for a merge commit naming it.
    Finding one is evidence the PR's *code* likely landed on this branch
    -- it is NOT evidence that GitHub itself considers that PR "merged"
    (a PR can be integrated via a squash/manual merge onto a side branch
    without ever being marked merged on GitHub, which is exactly this
    repository's stated situation for PR #236 itself: 'no merge to main
    is claimed'). Each finding says so explicitly.
    """
    findings: list[dict] = []
    for pr_number in pr_numbers:
        merge_commit = git_source.find_merge_commit_for_pr_number(repo_path, integration_branch_ref, pr_number)
        findings.append({
            "pr_number": pr_number,
            "found_in_integration_branch_history": merge_commit is not None,
            "merge_commit": merge_commit,
            "note": (
                "a merge commit naming this PR was found in the integration branch's history -- this is "
                "evidence the PR's code was integrated onto this branch, NOT evidence that GitHub's own "
                "'merged' field for that PR is true"
                if merge_commit is not None else
                "no merge commit naming this PR was found in the integration branch's history"
            ),
        })
    return findings


def check_merged_into_main(
    repo_path: Path, integration_branch_ref: str, main_ref: str, pr_snapshot: Optional[PRSnapshot]
) -> Evidence:
    """Whether the integration branch's changes are merged into main.
    Authoritative source is the PR's own supplied `merged` field (from
    live GitHub metadata) when available; local ancestry
    (`is_ancestor(integration_branch, main)`) is reported as
    *supporting* evidence only, and explicitly never substituted for the
    authoritative field on its own -- an integration branch can be a git
    ancestor of main today and still not correspond to a PR GitHub marks
    merged (e.g. if main independently gained the same changes through a
    different, unrelated commit), and conversely a real GitHub merge can
    occur through a squash that does not preserve a literal ancestor
    relationship in every checkout's view of history.
    """
    ancestor = git_source.is_ancestor(repo_path, integration_branch_ref, main_ref)

    if pr_snapshot is not None and pr_snapshot.merged is not None:
        source = "PR snapshot's own 'merged' field (authoritative)"
        if pr_snapshot.merged and ancestor is False:
            source += " -- NOTE: contradicts local ancestry evidence (branch is not a git ancestor of main), flagged, not silently resolved"
        elif not pr_snapshot.merged and ancestor is True:
            source += " -- NOTE: local ancestry shows the branch IS an ancestor of main even though the PR is not marked merged; do not infer merge completion from this alone"
        return Evidence(pr_snapshot.merged, source)

    return Evidence(
        None,
        "no authoritative PR 'merged' field supplied; local ancestry alone "
        f"(is_ancestor={ancestor}) is not treated as proof of merge completion",
    )
