# Stale PR Reconciliation Report

## Scope
This report reconciles PRs #142, #143, #144, and #149 after merge of PR #151.

## Findings

### PR #144
- Current observed state (from manual fixture and merge-context notes): mergeable, open, `0` changed files, `0` additions, `0` deletions.
- No unique commits vs `main` are expected after PR #151 conflict-resolution merge path.
- Recommendation: close as superseded by PR #151 (and effectively superseded by `main`).

### PR #149
- Current observed state (from manual fixture and merge-context notes): mergeable, open, no-op delta.
- Identified as duplicate/superseded by merged PR #150.
- Recommendation: close as superseded by PR #150.

### PR #142
- Branch appears stale by age and workflow history, but fixture lacks commit-diff evidence.
- Recommendation: manual verification and then close if no unique commits/files remain.

### PR #143
- Branch appears stale by age and workflow history, but fixture lacks commit-diff evidence.
- Recommendation: manual verification and then close if no unique commits/files remain.

## CI Consistency Note (Ontology Claim Language)
- Do not relax ontology-language checks for stale/no-op branches.
- Policy path is branch cleanup, not validator weakening.

## Suggested Maintainer Procedure (manual, no auto-close)
1. For each stale PR, compare merge-base against `origin/main` and confirm unique commit count.
2. Confirm workflow-only failures are not caused by missing rebases.
3. Close PRs with `recommended_action` beginning `close_as_*`.
4. Keep `manual_review_required` PRs open until commit/file uniqueness is resolved.
