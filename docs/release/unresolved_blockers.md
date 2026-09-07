# Unresolved blocker list

1. GitHub Actions required jobs for PR #236 and the inspected source PRs fail
   before any steps or logs become available. This is infrastructure/billing
   blocked; it is not CI success and not evidence of a code failure.
2. The final integration branch must remain open until required checks can
   execute diagnostically and pass.
3. The full isolated runner retains eight failures and three timeouts under
   its bounded policy; focused repairs cleared the scientific, benchmark,
   artifact-path, and batch-runner cases, but a clean full run is still
   required for a release recommendation.
4. Optional `torch`/`cripser` and Windows symlink capability remain environment
   dependent and should be revalidated in the supported CI images.

Release recommendation: `HOLD — review open PR #236; do not merge into main`.
