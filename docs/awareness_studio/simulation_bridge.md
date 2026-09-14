# Awareness Studio simulation bridge

The `awareness_studio.simulation_bridge` package is an additive adapter to the
canonical local executor in `tools.simulation_execution`. It does not execute
commands itself. A caller must first register an exact workload argv, then
provide a complete `BridgeRequest` containing:

- code commit, configuration, integer seed, and input identity;
- non-placeholder provenance (`dataset_id`, `source`, and `data_mode`);
- an explicit output root; and
- finite timeout, memory, disk, stdout, and stderr budgets.

`SimulationBridge.run()` is planning-only unless `authorize_execution=True`.
The bridge always sets the canonical runner to network-disabled mode and
rejects a request that asks for network-enabled execution. Workload outputs are
returned to Awareness Studio only after the canonical runner reports `PASS`,
all declared files are contained under the output root, checksums match on-disk
bytes, JSON is finite, RunRecord provenance matches the request, and the
read-only artifact-lineage extractor reports `COMPLETE`.

## Workflow states

| State | Meaning |
| --- | --- |
| `PLANNING` | Valid request; no executor was invoked. |
| `EXECUTION_NOT_AVAILABLE` | Invalid policy/request, denied network, or canonical executor unavailable. |
| `EXECUTION_FAILED` | Canonical run failed, timed out, or its outputs failed validation. |
| `ENGINEERING_EXECUTION_COMPLETE` | A synthetic/local engineering run completed and artifacts passed integrity checks. |
| `EVIDENCE_READY_FOR_REVIEW` | Non-synthetic artifacts passed integrity checks and are available for human review. This is not scientific validation. |

The result contract always has `scientific_pass: false`,
`formal_bayes_factor: null`, and `metrics: null`. Missing metrics are not
zero-filled. Synthetic runs use `evidence_class: synthetic_demo_only` and can
never be treated as empirical evidence. The bridge does not contact datasets,
AWS, or external services.

