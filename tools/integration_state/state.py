"""Orchestration: gather every requirement's facts into one
StateLockReport. Read-only, network-free (GitHub facts come from an
already-supplied PRSnapshot, never a live fetch)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from . import ci_classifier, commit_classifier, git_source, merge_verification
from .models import Evidence, PRSnapshot, StateLockReport

REPORT_SCHEMA = "NTS.IntegrationStateLockReport.v1"


def _lifecycle(pr: Optional[PRSnapshot]) -> Evidence:
    if pr is None:
        return Evidence(None, "no PR snapshot supplied")
    if pr.merged is True:
        return Evidence("merged", "pr_snapshot.merged")
    if pr.state == "closed":
        return Evidence("closed", "pr_snapshot.state")
    if pr.draft is True:
        return Evidence("draft", "pr_snapshot.draft")
    if pr.state == "open":
        return Evidence("open", "pr_snapshot.state")
    return Evidence("unknown", "pr_snapshot fields insufficient to classify")


def build_state_lock_report(
    repo_path: Path,
    integration_branch_ref: str,
    main_ref: str,
    local_worktree_ref: str = "HEAD",
    pr_snapshot: Optional[PRSnapshot] = None,
    handoff_claims: Optional[dict[str, str]] = None,
) -> StateLockReport:
    handoff_claims = handoff_claims or {}

    authoritative_head_commit = (
        pr_snapshot.head_sha if pr_snapshot is not None and pr_snapshot.head_sha
        else git_source.resolve_commit(repo_path, integration_branch_ref)
    )
    authoritative_head_source = (
        "pr_snapshot.head_sha (authoritative GitHub metadata)"
        if pr_snapshot is not None and pr_snapshot.head_sha
        else f"git rev-parse {integration_branch_ref} (no PR snapshot head_sha supplied)"
    )

    # Cross-check: if both a PR snapshot head_sha AND a locally resolvable
    # branch ref are available and disagree, that disagreement itself is
    # evidence worth a note (e.g. a stale local fetch).
    notes: list[str] = []
    local_branch_commit = git_source.resolve_commit(repo_path, integration_branch_ref)
    if (
        pr_snapshot is not None and pr_snapshot.head_sha and local_branch_commit
        and pr_snapshot.head_sha != local_branch_commit
    ):
        notes.append(
            f"PR snapshot head_sha ({pr_snapshot.head_sha}) differs from the locally resolvable "
            f"{integration_branch_ref} ({local_branch_commit}) -- re-fetch before trusting local git facts"
        )

    main_tip = git_source.resolve_commit(repo_path, main_ref)
    local_worktree_tip = git_source.resolve_commit(repo_path, local_worktree_ref)
    merge_base = None
    is_ancestor_of_main = None
    if authoritative_head_commit is not None and main_tip is not None:
        merge_base = git_source.merge_base(repo_path, authoritative_head_commit, main_tip)
        is_ancestor_of_main = git_source.is_ancestor(repo_path, authoritative_head_commit, main_tip)

    handoff_verifications = []
    contradictory = False
    contradiction_detail = None
    if authoritative_head_commit is not None:
        handoff_verifications = commit_classifier.classify_all(repo_path, handoff_claims, authoritative_head_commit)
        contradictory, contradiction_detail = commit_classifier.detect_contradictory_handoffs(handoff_verifications)
    elif handoff_claims:
        notes.append("no authoritative head commit could be resolved; handoff claims were not classified")

    integrated_pr_findings: list[dict] = []
    if pr_snapshot is not None and pr_snapshot.integrated_pr_numbers:
        integrated_pr_findings = merge_verification.verify_integrated_pr_history(
            repo_path, integration_branch_ref, pr_snapshot.integrated_pr_numbers
        )

    merged_into_main = merge_verification.check_merged_into_main(repo_path, integration_branch_ref, main_ref, pr_snapshot)

    check_classifications: dict[str, str] = {}
    if pr_snapshot is not None and pr_snapshot.checks:
        check_classifications = ci_classifier.as_state_map(ci_classifier.classify_all(pr_snapshot.checks))

    if pr_snapshot is not None and pr_snapshot.body_final_commit_claim and authoritative_head_commit is not None:
        body_claim_verification = commit_classifier.classify_all(
            repo_path, {"PR body 'Final commit' claim": pr_snapshot.body_final_commit_claim}, authoritative_head_commit
        )
        handoff_verifications = list(handoff_verifications) + body_claim_verification
        contradictory, contradiction_detail = commit_classifier.detect_contradictory_handoffs(handoff_verifications)

    return StateLockReport(
        schema=REPORT_SCHEMA,
        target_repo_path=str(repo_path),
        authoritative_head=Evidence(authoritative_head_commit, authoritative_head_source),
        main_tip=Evidence(main_tip, f"git rev-parse {main_ref}"),
        local_worktree_tip=Evidence(local_worktree_tip, f"git rev-parse {local_worktree_ref}"),
        merge_base_head_and_main=Evidence(merge_base, "git merge-base(authoritative_head, main_tip)"),
        is_head_ancestor_of_main=Evidence(is_ancestor_of_main, "git merge-base --is-ancestor(authoritative_head, main_tip)"),
        pr_number=Evidence(pr_snapshot.number if pr_snapshot else None, "pr_snapshot.number"),
        pr_state=Evidence(pr_snapshot.state if pr_snapshot else None, "pr_snapshot.state"),
        pr_draft=Evidence(pr_snapshot.draft if pr_snapshot else None, "pr_snapshot.draft"),
        pr_merged=merged_into_main,
        pr_lifecycle=_lifecycle(pr_snapshot),
        handoff_verifications=handoff_verifications,
        contradictory_handoffs=contradictory,
        contradiction_detail=contradiction_detail,
        integrated_pr_history_findings=integrated_pr_findings,
        check_classifications=check_classifications,
        notes=notes,
    )
