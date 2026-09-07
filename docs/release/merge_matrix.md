# Final integration merge matrix — live audit 2026-09-07

| PR/group | Decision | Reason |
|---|---|---|
| #209–#221 except #222 | Merged into main | Live GitHub state is `MERGED`; `origin/main` is `62aa8fee…`. |
| #222, #227 | Integrated-only via validated CI lineage | #227 contains dependency-profile/install policy; #222 is an earlier competing repair. Both live PRs remain open. |
| #223 | Integrated | Additive capability snapshot on #217; deterministic sidecar and focused tests. |
| #224, #232 | Integrated | Stacked bounded-stream planner and checkpoint/replay layers; no dense trajectory materialization. |
| #226, #234 | Integrated | Consumer-facing proxy/formal semantics and artifact migration; no naked proxy PASS. |
| #227 | Integrated with manual conflict resolution | CPU/base dependency policy and bounded installation adopted; existing useful jobs preserved. |
| #228, #229, #230, #231 | Integrated | Deterministic merge gate, provenance, performance policy, and read-only CI evidence diagnostics. |
| #233, #235, #238 | Integrated | Interop conformance, paired-cohort readiness, and optional TDA adapters. |
| #225 | Unmerged / duplicate release inventory | #216 is live-merged and remains schema/compiler authority; #225 explicitly says not to merge. |
| #216 | Merged into main | Live GitHub metadata says merged; it remains the release schema/compiler authority. |
| #206, #207, #208, #239, #241–#244, #252, #253, #255, #256, #262, #265, #267–#269 | Unmerged | Draft, audit-only, competing, independent, or review-only. |
| #237 | Unmerged | Explicit lead-only retirement inventory; PR body says do not merge or close PRs. |
| #240, #245–#248, #250–#251, #254, #257–#261, #263–#264, #266 | Integrated-only | Additive provenance, cohort, platform, TDA, runner, CI, performance, scientific, and release layers; focused validation recorded in the decision log. |
| #249 | Excluded as duplicate | Same five-file effective CI repair as #257, but older head. |
| `codex/scientific-falsification-contract` | Partially integrated | Topology-contract additions retained; overlapping Bayesian implementation rejected in favor of #219. |

Integration branch: `codex/integration-all-open-prs`.
