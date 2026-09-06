"""Main orchestration: combine git facts + an optional GitHub snapshot into
a ReconciliationReport. Read-only end to end."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from . import artifact_check, common_failures, dashboard_isolation, git_source, github_source, overlap
from .models import BranchFacts, Evidence, PRFacts, ReconciliationEntry, ReconciliationReport, WorkOrder

REPORT_SCHEMA = "NTS.IntegrationReconciliationReport.v1"


def _branch_facts(repo_path: Path, work_order: WorkOrder, target_ref: str) -> BranchFacts:
    if work_order.expected_branch is None:
        no_branch = Evidence(None, "work order declares no expected_branch")
        return BranchFacts(no_branch, no_branch, no_branch, no_branch, no_branch, no_branch)

    branch_ref = f"origin/{work_order.expected_branch}"
    snap = git_source.snapshot_branch(repo_path, branch_ref, target_ref)
    source = f"git rev-parse/merge-base/diff against {branch_ref}"
    if not snap.exists:
        absent = Evidence(False, f"{branch_ref} does not exist in this checkout's remotes")
        absent_none = Evidence(None, f"{branch_ref} does not exist in this checkout's remotes")
        return BranchFacts(absent, absent_none, absent_none, absent_none, absent_none, absent_none)

    return BranchFacts(
        exists=Evidence(True, source),
        commit_sha=Evidence(snap.commit_sha, source),
        merge_base_with_target=Evidence(snap.merge_base_with_target, source),
        is_ancestor_of_target=Evidence(snap.is_ancestor_of_target, source),
        commits_ahead_of_merge_base=Evidence(snap.commits_ahead_of_merge_base, source),
        changed_files=Evidence(
            list(snap.changed_files) if snap.changed_files is not None else None, source
        ),
    )


def _pr_facts(work_order: WorkOrder, snapshot: dict[str, Any]) -> PRFacts:
    pr = None
    if work_order.expected_branch is not None:
        pr = github_source.find_pr_by_branch(snapshot, work_order.expected_branch)
    if pr is None and work_order.reported_pr_number is not None:
        pr = github_source.find_pr_by_number(snapshot, work_order.reported_pr_number)

    if pr is None:
        absent = Evidence(None, "no matching entry in the supplied GitHub snapshot")
        return PRFacts(absent, absent, absent, absent, absent, absent, absent, absent)

    source = f"github snapshot entry for PR #{pr.get('number')}"

    def field(key: str) -> Evidence:
        if key not in pr:
            return Evidence(None, f"{source}: field {key!r} absent from snapshot")
        return Evidence(pr[key], source)

    return PRFacts(
        number=field("number"),
        state=field("state"),
        draft=field("draft"),
        merged=field("merged"),
        mergeable_state=field("mergeable_state"),
        head_sha=field("head_sha"),
        base_sha=field("base_sha"),
        checks=field("checks"),
    )


def _derive_stages(branch: BranchFacts, pr: PRFacts) -> dict[str, Evidence]:
    stages: dict[str, Evidence] = {}
    stages["reported"] = Evidence(True, "work order was supplied to this reconciliation run")
    stages["branch_present"] = Evidence(branch.exists.value, branch.exists.source)
    stages["pr_present"] = Evidence(pr.number.value is not None, pr.number.source)

    checks_value = pr.checks.value
    passing = github_source.checks_all_passing(checks_value)
    stages["checks_passing"] = Evidence(passing, pr.checks.source if checks_value else "no check data available")

    mergeable = github_source.mergeable_from_state(pr.mergeable_state.value)
    stages["mergeable"] = Evidence(mergeable, pr.mergeable_state.source)

    stages["merged"] = Evidence(pr.merged.value, pr.merged.source)
    return stages


def _notes_for(work_order: WorkOrder, branch: BranchFacts, pr: PRFacts, stages: dict[str, Evidence]) -> list[str]:
    notes: list[str] = []
    if work_order.reported_status_note:
        notes.append(f"as reported: {work_order.reported_status_note}")

    branch_present = stages["branch_present"].value
    pr_present = stages["pr_present"].value

    if work_order.reported_pr_number is None and pr_present:
        notes.append(
            f"a PR (#{pr.number.value}) now exists for this branch even though none was "
            "reported at assignment time -- treat the original report as stale"
        )
    if work_order.reported_pr_number is not None and not pr_present:
        notes.append(
            f"reported PR #{work_order.reported_pr_number} was not found in the supplied "
            "GitHub snapshot -- verify the number or re-fetch"
        )
    if branch_present is False and pr_present:
        notes.append(
            "inconsistent: a PR was found but the branch does not exist in this checkout's "
            "remotes -- re-run `git fetch` before trusting this entry"
        )
    if branch_present and not pr_present and work_order.reported_status_note.startswith("PR creation"):
        notes.append("confirms the report: branch exists, no PR -- PR creation still appears blocked")
    return notes


def reconcile(
    repo_path: Path,
    work_orders: tuple[WorkOrder, ...],
    target_ref: str = "origin/main",
    github_snapshot: Optional[dict[str, Any]] = None,
    dashboard_src: Optional[Path] = None,
) -> ReconciliationReport:
    if github_snapshot is None:
        github_snapshot = github_source.empty_snapshot()

    entries: list[ReconciliationEntry] = []
    changed_files_by_work_order: dict[str, Optional[tuple[str, ...]]] = {}
    checks_by_work_order: dict[str, Optional[dict[str, str]]] = {}

    for work_order in work_orders:
        branch = _branch_facts(repo_path, work_order, target_ref)
        pr = _pr_facts(work_order, github_snapshot)
        stages = _derive_stages(branch, pr)
        notes = _notes_for(work_order, branch, pr, stages)
        entries.append(ReconciliationEntry(work_order=work_order, branch=branch, pr=pr, stages=stages, notes=notes))

        files = branch.changed_files.value
        changed_files_by_work_order[work_order.work_order_id] = tuple(files) if files is not None else None
        checks_by_work_order[work_order.work_order_id] = pr.checks.value

    file_overlaps = overlap.compute_overlaps(changed_files_by_work_order)
    common_check_failures = common_failures.detect_common_check_failures(checks_by_work_order)

    artifact_findings: dict[str, list[str]] = {}
    for work_order_id, files in changed_files_by_work_order.items():
        if files is None:
            continue
        suspects = artifact_check.find_suspect_artifacts(files)
        if suspects:
            artifact_findings[work_order_id] = suspects

    dashboard_result = None
    if dashboard_src is not None:
        dashboard_result = dashboard_isolation.check_dashboard_isolation(dashboard_src)

    base_commit = git_source.resolve_commit(repo_path, target_ref)

    return ReconciliationReport(
        schema=REPORT_SCHEMA,
        base_branch=target_ref,
        base_commit=base_commit,
        entries=entries,
        file_overlaps=file_overlaps,
        common_check_failures=common_check_failures,
        dashboard_isolation=dashboard_result,
        artifact_commit_findings=artifact_findings,
    )
