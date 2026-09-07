# Final integration merge matrix

| PR/group | Decision | Reason |
|---|---|---|
| #209, #210, #211, #212, #213, #214, #215, #217, #218, #219, #220, #221, #222 | Integrated | Validated foundational, streaming, interop, scientific, tooling, and CI groups. |
| #223 | Integrated | Additive capability snapshot on #217; deterministic sidecar and focused tests. |
| #224, #232 | Integrated | Stacked bounded-stream planner and checkpoint/replay layers; no dense trajectory materialization. |
| #226, #234 | Integrated | Consumer-facing proxy/formal semantics and artifact migration; no naked proxy PASS. |
| #227 | Integrated with manual conflict resolution | CPU/base dependency policy and bounded installation adopted; existing useful jobs preserved. |
| #228, #229, #230, #231 | Integrated | Deterministic merge gate, provenance, performance policy, and read-only CI evidence diagnostics. |
| #233, #235, #238 | Integrated | Interop conformance, paired-cohort readiness, and optional TDA adapters. |
| #225 | Integrated | Release-state classification; supersedes #216 inventory. |
| #206, #207, #208 | Unmerged | Draft/review-only or outside the validated dependency graph. |
| #216 | Superseded | Release inventory superseded by #225; no duplicate evidence compiler retained. |
| #237 | Unmerged | Explicit lead-only retirement inventory; PR body says do not merge or close PRs. |
| `codex/scientific-falsification-contract` | Partially integrated | Topology-contract additions retained; overlapping Bayesian implementation rejected in favor of #219. |

Integration branch: `codex/integration-all-open-prs`.
