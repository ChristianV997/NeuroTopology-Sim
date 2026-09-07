# Live PR and branch audit — 2026-09-07

Authoritative observations were taken after `git fetch origin --prune` and
`gh pr view/list`. The integration ref was
`af3ac584419148ddcfc57cb565c416eba6328725` at audit start; PR #236 was open
at that head. `origin/main` was
`62aa8fee786abf916ab0aa2b7e7b91c570fee119` and is an ancestor of the
integration branch.

## Recently merged into main

Live state: #209, #210, #211, #212, #213, #214, #215, #216, #217, #218,
#219, #220, and #221 are `MERGED`. This is not inferred from local merge
commits or branch existence.

## Open PR inventory and decision

| PRs | Decision |
|---|---|
| #222–#224, #226–#238 | Integrated-only where listed in `merge_matrix.md`; all remain live-open unless GitHub says otherwise. #225 and #237 are explicitly excluded. |
| #239 | Unintegrated competing research-state report compiler. |
| #240 | Integrated-only lazy local provenance readers. |
| #241–#244 | Unintegrated draft benchmark/triage work. |
| #245–#248 | Integrated-only claim audit, cohort statistics, platform compatibility, and cohort topology. |
| #249 | Excluded duplicate of newer #257’s five-file CI repair. |
| #250–#251 | Integrated-only TDA hardening and regression repair. |
| #252–#253 | Unintegrated mobile report/readiness audit; readiness is not evidence. |
| #254 | Integrated-only timeout-safe process-group runner repair. |
| #255–#256 | Unintegrated draft state-lock/ownership audits. |
| #257 | Integrated-only newer authoritative five-file CI repair. |
| #258–#261 | Integrated-only performance evidence, null calibration, canonical adapter, and admission layers. |
| #262 | Excluded competing duplicate of #246’s cohort-statistics implementation. |
| #263–#264 | Integrated-only reconciliation closure and research-record compiler. |
| #265 | Unintegrated out-of-scope autonomous orchestration. |
| #266–#269 | #266 integrated-only release manifest; #267–#269 unintegrated draft release/platform/performance/preregistration work. |

PR #236 is the open final integration PR. The complete changed-file ownership
snapshot is in `changed_file_ownership.md`; 282 effective paths were present
relative to `origin/main` before the final release-artifact updates.
