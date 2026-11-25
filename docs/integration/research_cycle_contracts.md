# Research-cycle file/contract chain

Black-box integration tests in `tests/integration/research_cycle/` consume
versioned JSON stage files. They do not implement Batch 1 producers, do not
modify production code, and do not treat synthetic fixtures as scientific
evidence.

Pipeline contract: `NeuroTopologySim.ResearchCyclePipeline.v1`

```
literature/source manifest
  → research-plan audit
  → hypothesis/experiment manifest
  → simulation run manifest
  → artifact manifest
  → validation report
  → evidence graph
  → release-evidence report
```

Every stage file is an envelope:

| Field | Role |
| --- | --- |
| `schema_version` | Producer-declared schema. Consumers reject anything outside the compatible set. |
| `pipeline_contract` | Must be `NeuroTopologySim.ResearchCyclePipeline.v1`. |
| `stage` | One of the eight stage ids above. |
| `record_id` | Stable identity. Duplicate ids are an error. |
| `checksum` | SHA-256 of canonical JSON with the `checksum` field excluded. |
| `parent_ids` / `parent_checksums` | Provenance links to the previous stage. |
| `data_mode` | `synthetic` \| `proxy` \| `empirical` \| `unknown`. Never silently rewritten. |
| `evidence_class` | Epistemic label. Synthetic stays synthetic. |
| `status` | `COMPLETE` \| `PARTIAL` \| `FAILED` \| `BLOCKED` \| `INCOMPLETE` \| `PENDING` \| `CONFLICTING`. |
| `scientific_verdict` | Never `PASS` for synthetic/proxy fixtures. |
| `payload` | Native producer body (or the declared fixture shape when the producer is missing). |
| `diagnostics` | Missing artifacts, duplicates, upstream failures. |

Checksums use RFC-8259 JSON (`allow_nan=False`, sorted keys, compact separators), matching `tools.research_cycle.serialization.compute_record_checksum`.

Path fields accept Windows (`runs\cycle\metrics.json`, `C:\research\cycle\metrics.json`) and POSIX (`runs/cycle/metrics.json`) forms. Consumers compare POSIX-normalized relative paths.

Finite JSON: NaN/Inf are rejected on load. Serialization never emits those tokens. Missing numeric metrics stay `null`; they are never fabricated as `0`.

---

## Contracts on origin/main vs missing producers

Inspected at `origin/main` (`618ca081039759510d27a7a772cd47c95985600f`) plus open Batch 1 PRs dated 2026-09-10.

| Stage | Declared schema | On main? | Producer / notes |
| --- | --- | --- | --- |
| literature/source manifest | `NeuroTopologySim.EmpiricalSourceManifest.v1` | **Yes** | `configs.empirical_sources.manifest`. Preregistration identity only; a complete template is not empirical evidence. |
| research-plan audit | `NeuroTopologySim.ResearchPlanAudit.v1` | **No (PENDING)** | Open [PR #302](https://github.com/ChristianV997/NeuroTopology-Sim/pull/302) (`tools.research_plan_quality`). `PlanAuditResult` currently lacks `schema_version`; the envelope supplies the declared integration version. `evidence_class` is always `research_plan_audit`. |
| hypothesis/experiment manifest | `ResearchCycleRegistry.v1` with nested `HypothesisRecord.v1`, `ExperimentPlan.v1`, `PredictionRecord.v1`, `EvidenceUpdate.v1`, `TheoryRevision.v1` | **Yes** | `tools.research_cycle`. Promotion rules A–G remain in force. |
| simulation run manifest | Envelope `NeuroTopologySim.SimulationRunManifest.v1` wrapping `RunRecordV1` (`schema_version` `0.1` general / `1` sim) | **Partial** | `runs.run_record.RunRecordV1` is on main. Lineage extractor `NeuroTopologySim.SimulationArtifactLineage.v1` is only on [PR #304](https://github.com/ChristianV997/NeuroTopology-Sim/pull/304). |
| artifact manifest | `NTS.IntegrationArtifactManifest.v1` (compatible alias: `NeuroTopologySim.SimulationArtifactLineage.v1`) | **Yes** (lineage alias PENDING) | `tools.integration_bridge.artifact_manifest` on main. PR #304 lineage report is fixture-compatible, not imported. |
| validation report | `NeuroTopologySim.ValidationReport.v1` (compatible alias: `awareness-studio-research-cycle.v1`) | **No (PENDING)** | [PR #305](https://github.com/ChristianV997/NeuroTopology-Sim/pull/305) ledger `ValidationReport`. No standalone file producer on main. |
| evidence graph | `NeuroTopologySim.ResearchCycleEvidenceGraph.v1` | **No (PENDING)** | Not present on main. `tools/research_record/graph.py` and `tools/research_report/graph.py` are PR-stacking graphs, not this stage. |
| release-evidence report | `1.0` (`GATE_SCHEMA_VERSION`) | **Yes** | `tools.performance.release_evidence_gate`. Performance evidence only. Incompatible normalization schemas → `NOT_COMPARABLE`. Timeouts never PASS. |

Open Batch 1 PRs used as declared-contract sources (not merged, not imported):

- [#302](https://github.com/ChristianV997/NeuroTopology-Sim/pull/302) research-plan quality rubric
- [#304](https://github.com/ChristianV997/NeuroTopology-Sim/pull/304) simulation artifact lineage
- [#305](https://github.com/ChristianV997/NeuroTopology-Sim/pull/305) Awareness Studio research-cycle ledger
- [#303](https://github.com/ChristianV997/NeuroTopology-Sim/pull/303) resource benchmarks (out of this file-chain; not consumed)

When a producer is PENDING, tests ship a fixture that matches the declared envelope + payload shape and mark the implementation missing. Tests do not add production modules.

---

## Consumer rules (the 15 requirements)

1. Every producer envelope declares `schema_version`. Nested registry records declare theirs too.
2. The test consumer rejects missing versions, foreign `pipeline_contract`s, and schemas outside the compatible set. `evaluate_release_evidence` independently returns `NOT_COMPARABLE` for unsupported normalization schemas.
3. `record_id` and SHA-256 checksums are stable across canonical serialization.
4. Each non-root stage names `parent_ids` and matching `parent_checksums`.
5. `data_mode` / `evidence_class` / `origin` are not rewritten. Synthetic → empirical is an error.
6. `PARTIAL` stays `PARTIAL` downstream. Completeness is never inferred.
7. Invalid claims stay blocked: synthetic scientific PASS; proxy K as formal Bayes; synthetic biological promotion (Rule B); promotion without human review (Rule G).
8. Missing artifacts are listed in `diagnostics.missing` and the inspection report.
9. Duplicate `record_id` values are detected.
10. Inspection performs no network I/O. Owned sources do not import `socket`/`requests`/`urllib`.
11. Inspection executes no solver. Owned sources do not import numpy/scipy/sklearn/mne/torch/ripser/gudhi.
12. Non-finite JSON is rejected on load; dumps use `allow_nan=False`.
13. Windows and POSIX path forms normalize to the same relative POSIX path.
14. A `FAILED` stage forces downstream `FAILED`/`BLOCKED`/`PARTIAL` with `diagnostics.upstream_failures`.
15. Identical fixtures produce byte-identical files and identical inspection reports.

---

## Scientific guardrails

- No scientific PASS from synthetic fixtures.
- Proxy K is not formal Bayes.
- Synthetic is not empirical.
- Missing provenance is not evidence.
- A research-plan audit score is not confirmation (`evidence_class=research_plan_audit`).
- Release-evidence `EVIDENCE_READY` is performance scaffolding only.

---

## How to run

```bash
PYTHONPATH=. python -m pytest tests/integration/research_cycle -q
PYTHONPATH=. python scripts/run_tests_isolated.py --root tests/integration/research_cycle --batch-size 4 --timeout-s 120
python -m compileall -q tests/integration/research_cycle docs/integration
python -m governance.validate
git diff --check
```

Do not download datasets. Do not run long simulations. Do not merge on the basis of these fixtures.
