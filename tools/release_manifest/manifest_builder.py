"""Assembles a ReleaseCandidateManifest from git facts, an optional PR
snapshot, CI classification, scientific-gate input, and changed-file
ownership data. The single orchestration point of this package --
depends only on sibling modules within tools/release_manifest.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from . import ci_classifier, git_source, github_source, ownership, scientific_gate
from .merge_state import MergeStateContext, classify_merge_state, classify_release_state
from .models import (
    ChangedFileOwnership,
    Evidence,
    PRSnapshot,
    ReleaseCandidateManifest,
    ScientificGateInput,
)


def build_manifest(
    *,
    repo_path: Path,
    repository: str,
    target_branch: str,
    integration_branch: str,
    source_commit: str,
    pr_snapshot_path: Optional[Path] = None,
    scientific_gate_input: Optional[ScientificGateInput] = None,
    other_ownerships: Sequence[ChangedFileOwnership] = (),
    dependency_blockers: Sequence[str] = (),
    include_generated_at: bool = False,
    generated_at_value: Optional[str] = None,
) -> ReleaseCandidateManifest:
    manifest = ReleaseCandidateManifest(
        repository=repository,
        target_branch=target_branch,
        integration_branch=integration_branch,
        source_commit=source_commit,
    )

    pr_snapshot: Optional[PRSnapshot] = github_source.load_pr_snapshot(pr_snapshot_path)
    manifest.github_state = github_source.github_state_of(pr_snapshot)

    resolved = git_source.resolve_commit(repo_path, source_commit)
    commit_resolves = resolved is not None
    if commit_resolves:
        manifest.verified_head_commit = Evidence(resolved, f"git rev-parse --verify {source_commit}^{{commit}}")
    else:
        manifest.verified_head_commit = Evidence(
            None, f"{source_commit!r} does not resolve to any real git object in this repository"
        )

    is_head_of_target = commit_resolves and git_source.resolve_commit(repo_path, target_branch) == resolved
    is_ancestor_of_target = (
        commit_resolves and not is_head_of_target
        and bool(git_source.is_ancestor(repo_path, resolved, target_branch))
    )
    is_head_of_integration = commit_resolves and git_source.resolve_commit(repo_path, integration_branch) == resolved
    is_ancestor_of_integration = (
        commit_resolves and not is_head_of_integration
        and bool(git_source.is_ancestor(repo_path, resolved, integration_branch))
    )

    manifest.branch_ancestry = {
        "target_branch": target_branch,
        "integration_branch": integration_branch,
        "is_current_head_of_target": is_head_of_target,
        "is_ancestor_of_target": is_ancestor_of_target,
        "is_current_head_of_integration": is_head_of_integration,
        "is_ancestor_of_integration": is_ancestor_of_integration,
    }

    this_changed_files = ()
    if commit_resolves:
        found = git_source.changed_files(repo_path, target_branch, resolved)
        this_changed_files = found or ()
    this_ownership = ChangedFileOwnership(label=repository, changed_files=tuple(this_changed_files))
    all_ownerships = [this_ownership, *other_ownerships]
    manifest.changed_file_ownership = ownership.ownership_to_dict(all_ownerships)
    duplicate_findings = ownership.find_duplicate_ownership(all_ownerships)
    manifest.duplicate_file_findings = duplicate_findings
    this_duplicates = tuple(
        f"{d['labels']}" for d in duplicate_findings if this_ownership.label in d["labels"]
    )

    if pr_snapshot is not None:
        manifest.pr_number = Evidence(pr_snapshot.number, "github snapshot")
        manifest.pr_status = Evidence(pr_snapshot.state, "github snapshot")
        manifest.draft_status = Evidence(pr_snapshot.draft, "github snapshot")
        classified_checks = ci_classifier.classify_all_checks(pr_snapshot.checks)
    else:
        manifest.pr_number = Evidence(None, "no github snapshot supplied")
        manifest.pr_status = Evidence(None, "no github snapshot supplied")
        manifest.draft_status = Evidence(None, "no github snapshot supplied")
        classified_checks = {}
    manifest.ci_classifications = classified_checks
    worst_ci_state = ci_classifier.worst_check_state(classified_checks)

    sci_evidence, sci_blocking, sci_findings = scientific_gate.evaluate_scientific_gate(scientific_gate_input)
    manifest.scientific_gate_status = sci_evidence

    ctx = MergeStateContext(
        commit_resolves=commit_resolves,
        source_commit=resolved,
        target_branch=target_branch,
        is_current_head_of_target=is_head_of_target,
        is_ancestor_of_target=is_ancestor_of_target,
        is_current_head_of_integration=is_head_of_integration,
        is_ancestor_of_integration=is_ancestor_of_integration,
        pr_snapshot=pr_snapshot,
        worst_ci_state=worst_ci_state,
        scientific_blocking=sci_blocking,
        duplicate_findings=this_duplicates,
        dependency_blockers=tuple(dependency_blockers),
    )
    merge_state, blockers = classify_merge_state(ctx)
    release_state, release_blockers = classify_release_state(
        ctx,
        merge_state=merge_state,
        scientific_gate_value=sci_evidence.value,
    )
    manifest.merge_state = merge_state
    manifest.release_state = release_state
    manifest.blockers = list(dict.fromkeys([*blockers, *sci_findings, *release_blockers]))
    # This legacy field is only a technical ancestry fact.  Use
    # release_eligibility for a decision to publish or call a release ready.
    manifest.merge_eligibility = merge_state == "merged_into_main"
    manifest.release_eligibility = release_state == "ready_for_release"

    manifest.governance_status = Evidence("not evaluated by this tool", "out of scope for release_manifest")
    manifest.dashboard_isolation_status = Evidence("not evaluated by this tool", "out of scope for release_manifest")
    manifest.memory_timeout_status = Evidence("not evaluated by this tool", "out of scope for release_manifest")

    manifest.provenance = {
        "tool": "tools.release_manifest",
        "schema": manifest.schema,
        "git_source": "local repository at build time, read-only",
        "github_source": "pre-fetched snapshot file" if pr_snapshot is not None else "unavailable",
    }
    manifest.generated_at = generated_at_value if include_generated_at else None

    return manifest
