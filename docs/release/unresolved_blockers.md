# Unresolved blocker list

1. GitHub Actions required jobs for PR #236 and inspected source PRs are
   `FAILURE` before usable steps/logs, with runner/billing annotations. This
   is infrastructure-blocked, not CI success and not a local test result.
2. The integration branch and PR #236 must remain open; main must not be
   merged until mandatory checks can start, complete, and pass.
3. The mandated full isolated run has preserved local failures/timeouts from
   the prior evidence (`64 passed, 8 failed, 3 timed out`, exit 124). The
   final mandated run completed `73 passed, 4 failed, 4 timed out` with exit
   code 1. A clean full run remains required for release.
4. Optional `torch`, `cripser`, and `ripser` capability checks and Windows
   symlink privilege (`WinError 1314`) are environment-dependent. Only those
   capability cases are classified as skips; real assertion failures remain
   failures.
5. No complete empirical dataset/provenance package is available; scientific
   status remains `INCONCLUSIVE` and synthetic output remains
   `NOT_SUPPORTED`.

Release recommendation: `HOLD — review open PR #236; do not merge into main`.
