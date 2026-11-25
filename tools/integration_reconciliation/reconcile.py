"""Main orchestration: combine git facts + an optional GitHub snapshot into
a ReconciliationReport. Read-only end to end."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from . import (
    artifact_check,
    ci_interpretation,
    common_failures,
    dashboard_isolation,
    duplicate_detection,
    git_source,
    github_source,
    overlap,
    scientific_gates,
    stacking,
)
from .models import (
    BranchFacts,
    CurrentStatus,
    Evidence,
    PRFacts,
    ReconciliationEntry,
    ReconciliationReport,
    StackInfo,
    WorkOrder,
)

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


def _pr_facts(work_order: WorkOrder, snapshot: dict[str, Any]) -> tuple[PRFacts, Optional[dict]]:
    pr = None
    if work_order.expected_branch is not None:
        pr = github_source.find_pr_by_branch(snapshot, work_order.expected_branch)
    if pr is None and work_order.reported_pr_number is not None:
        pr = github_source.find_pr_by_number(snapshot, work_order.reported_pr_number)

    if pr is None:
        absent = Evidence(None, "no matching entry in the supplied GitHub snapshot")
        return PRFacts(absent, absent, absent, absent, absent, absent, absent, absent), None

    source = f"github snapshot entry for PR #{pr.get('number')}"

    def field(key: str) -> Evidence:
        if key not in pr:
            return Evidence(None, f"{source}: field {key!r} absent from snapshot")
        return Evidence(pr[key], source)

    body_excerpt = pr.get("body")
    body_field = (
        Evidence(body_excerpt[:2000], source) if isinstance(body_excerpt, str)
        else Evidence(None, f"{source}: field 'body' absent from snapshot")
    )

    return PRFacts(
        number=field("number"),
        state=field("state"),
        draft=field("draft"),
        merged=field("merged"),
        mergeable_state=field("mergeable_state"),
        head_sha=field("head_sha"),
        base_sha=field("base_sha"),
        checks=field("checks"),
        head_ref=field("head_ref"),
        base_ref=field("base_ref"),
        body_excerpt=body_field,
    ), pr


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


def _lifecycle_state(pr: PRFacts) -> Evidence:
    if pr.number.value is None:
        return Evidence(None, "no PR found")
    if pr.merged.value is True:
        return Evidence("merged", pr.merged.source)
    if pr.state.value == "closed":
        return Evidence("closed", pr.state.source)
    if pr.draft.value is True:
        return Evidence("draft", pr.draft.source)
    if pr.state.value == "open":
        return Evidence("open", pr.state.source)
    return Evidence(None, "PR state/draft/merged fields insufficient to classify")


def _checks_status(pr: PRFacts) -> Evidence:
    raw_checks = pr.checks.value
    if not raw_checks:
        return Evidence("not_run", "no check data available")
    normalized = github_source.normalize_checks(raw_checks)
    classifications = ci_interpretation.classify_all(normalized)
    summary = ci_interpretation.summarize(classifications)
    distinct = set(summary)
    if len(distinct) == 1:
        return Evidence(next(iter(distinct)), pr.checks.source)
    # Precedence when checks disagree: surface the most actionable/urgent
    # state first so a reviewer never mistakes a partially-blocked PR for
    # a merely-pending one.
    for priority in ("billing_blocked", "infrastructure_blocked", "failing", "pending", "passing", "not_run", "unknown"):
        if priority in distinct:
            return Evidence("mixed", f"{pr.checks.source} (mixed: {summary})")
    return Evidence("mixed", f"{pr.checks.source} (mixed: {summary})")


def _mergeability(pr: PRFacts) -> Evidence:
    value = github_source.mergeable_from_state(pr.mergeable_state.value)
    if value is True:
        return Evidence("mergeable", pr.mergeable_state.source)
    if value is False:
        return Evidence("conflicting", pr.mergeable_state.source)
    return Evidence("unknown", pr.mergeable_state.source)


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
    work_order_branches: dict[str, str] = {}
    pr_base_by_work_order: dict[str, Optional[str]] = {}
    raw_pr_by_work_order: dict[str, Optional[dict]] = {}

    for work_order in work_orders:
        branch = _branch_facts(repo_path, work_order, target_ref)
        pr, raw_pr = _pr_facts(work_order, github_snapshot)
        stages = _derive_stages(branch, pr)
        notes = _notes_for(work_order, branch, pr, stages)
        entries.append(ReconciliationEntry(work_order=work_order, branch=branch, pr=pr, stages=stages, notes=notes))

        files = branch.changed_files.value
        changed_files_by_work_order[work_order.work_order_id] = tuple(files) if files is not None else None
        checks_by_work_order[work_order.work_order_id] = pr.checks.value
        raw_pr_by_work_order[work_order.work_order_id] = raw_pr
        if work_order.expected_branch is not None:
            work_order_branches[work_order.work_order_id] = work_order.expected_branch
        pr_base_by_work_order[work_order.work_order_id] = pr.base_ref.value

    # ---- stacked-PR awareness ----
    target_branch_name = target_ref.rsplit("/", 1)[-1]
    stack_relationships = stacking.build_stack_relationships(
        work_order_branches, pr_base_by_work_order, target_branch_name
    )
    effective_files_by_work_order: dict[str, Optional[tuple[str, ...]]] = {}
    for work_order_id, relationship in stack_relationships.items():
        if relationship.is_stacked:
            effective_files_by_work_order[work_order_id] = stacking.effective_changed_files(
                repo_path, relationship, target_ref
            )
        else:
            effective_files_by_work_order[work_order_id] = changed_files_by_work_order.get(work_order_id)
    # Work orders with no branch info at all keep whatever (None) they already had.
    for work_order in work_orders:
        effective_files_by_work_order.setdefault(
            work_order.work_order_id, changed_files_by_work_order.get(work_order.work_order_id)
        )

    stacked_pairs = frozenset(
        (relationship.base_work_order_id, work_order_id)
        for work_order_id, relationship in stack_relationships.items()
        if relationship.base_work_order_id is not None
    )

    # ---- scientific gate hints + current status, per entry ----
    for entry in entries:
        work_order_id = entry.work_order.work_order_id
        relationship = stack_relationships.get(work_order_id)
        if relationship is not None:
            entry.stack = StackInfo(
                is_stacked=Evidence(relationship.is_stacked, "PR base_ref vs. target_ref"),
                base_work_order_id=Evidence(relationship.base_work_order_id, "matched via known work orders' branches"),
                dependents=Evidence(list(relationship.dependents), "other work orders whose PR base_ref is this one's branch"),
            )

        effective_files = effective_files_by_work_order.get(work_order_id)
        entry.effective_changed_files = Evidence(
            list(effective_files) if effective_files is not None else None,
            "diff against immediate PR base (stacked) or target_ref (unstacked)",
        )

        raw_pr = raw_pr_by_work_order.get(work_order_id)
        body_text = raw_pr.get("body") if isinstance(raw_pr, dict) else None
        hints = scientific_gates.evaluate_text(body_text or "")
        touches_science = scientific_gates.touches_scientific_paths(
            tuple(effective_files) if effective_files else None
        )
        hints_dict = hints.to_dict()
        hints_dict["touches_scientific_paths"] = touches_science
        hints_dict["scientific_review_required"] = hints_dict["scientific_review_required"] or touches_science
        entry.scientific_gate_hints = hints_dict

        entry.current_status = CurrentStatus(
            lifecycle_state=_lifecycle_state(entry.pr),
            checks_status=_checks_status(entry.pr),
            mergeability=_mergeability(entry.pr),
            billing_blocked=Evidence(
                _checks_status(entry.pr).value == "billing_blocked", "derived from checks_status"
            ),
            superseded=Evidence(False, "not yet computed"),  # filled in below
            duplicate=Evidence(False, "not yet computed"),  # filled in below
            scientific_review_required=Evidence(
                hints_dict["scientific_review_required"], "scientific_gates text + path hints"
            ),
        )

    # ---- overlap (on EFFECTIVE diffs -- a stacked PR's raw diff against
    # target_ref necessarily repeats its base PR's files, which is
    # expected lineage, not an accidental conflict; the effective diff is
    # each work order's own, non-double-counted contribution) ----
    file_overlaps = overlap.compute_overlaps(effective_files_by_work_order)
    common_check_failures = common_failures.detect_common_check_failures(checks_by_work_order)

    artifact_findings: dict[str, list[str]] = {}
    for work_order_id, files in changed_files_by_work_order.items():
        if files is None:
            continue
        suspects = artifact_check.find_suspect_artifacts(files)
        if suspects:
            artifact_findings[work_order_id] = suspects

    # ---- duplicates (on EFFECTIVE diffs, so a stacked PR's tiny real diff
    # is compared, not double-counted against its base) ----
    possible_duplicates = duplicate_detection.detect_possible_duplicates(
        effective_files_by_work_order, stacked_pairs=stacked_pairs
    )
    duplicated_work_orders = {finding["work_order_a"] for finding in possible_duplicates} | {
        finding["work_order_b"] for finding in possible_duplicates
    }

    # ---- superseded: direct branch-to-branch ancestry among present
    # branches NOT already explained by a known, legitimate stack
    # relationship (a stacked PR's branch is *always* a descendant of its
    # base's branch by construction -- that is deliberate lineage, never
    # evidence one supersedes the other) ----
    ancestry_by_pair: dict[tuple[str, str], Optional[bool]] = {}
    present = [wo for wo in work_orders if work_order_branches.get(wo.work_order_id)]
    for i, wo_a in enumerate(present):
        for wo_b in present[i + 1:]:
            pair = (wo_a.work_order_id, wo_b.work_order_id)
            if pair in stacked_pairs or (pair[1], pair[0]) in stacked_pairs:
                continue
            branch_a = f"origin/{work_order_branches[wo_a.work_order_id]}"
            branch_b = f"origin/{work_order_branches[wo_b.work_order_id]}"
            ancestry_by_pair[pair] = git_source.is_ancestor(repo_path, branch_a, branch_b)
    superseded_work = duplicate_detection.detect_superseded(ancestry_by_pair)
    superseded_work_orders = {finding["superseded_work_order"] for finding in superseded_work}

    for entry in entries:
        work_order_id = entry.work_order.work_order_id
        if entry.current_status is not None:
            entry.current_status = CurrentStatus(
                lifecycle_state=entry.current_status.lifecycle_state,
                checks_status=entry.current_status.checks_status,
                mergeability=entry.current_status.mergeability,
                billing_blocked=entry.current_status.billing_blocked,
                superseded=Evidence(
                    work_order_id in superseded_work_orders, "duplicate_detection.detect_superseded (git ancestry)"
                ),
                duplicate=Evidence(
                    work_order_id in duplicated_work_orders,
                    "duplicate_detection.detect_possible_duplicates (Jaccard similarity of effective diffs)",
                ),
                scientific_review_required=entry.current_status.scientific_review_required,
            )

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
        possible_duplicates=possible_duplicates,
        superseded_work=superseded_work,
    )
