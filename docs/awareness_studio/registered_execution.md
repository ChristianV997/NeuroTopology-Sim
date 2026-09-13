# Registered execution through Awareness Studio

`Orchestrator.run_registered(request, registry, preflight_request,
ledger_path=...)` composes the canonical research-cycle preflight, simulation
bridge, bounded executor, artifact extractor, and SQLite ledger. The existing
`Orchestrator.run()` template planning workflow remains available unchanged.

Construct a `BridgeRequest` and `WorkloadRegistry` using the simulation bridge
API. The preflight request must contain the normal research plan plus an
`execution_binding` produced by
`awareness_studio.orchestrator.registered_execution.execution_binding` for the
reviewed request and registry. Store that binding with the reviewed plan before
execution; do not regenerate it automatically after changing the computation.
The binding is an integrity contract, not a digital signature or independent
approval authority.

The orchestrator requires the plan's dataset ID, seed, and code version to match
execution provenance. Synthetic runs require the plan to declare synthetic
evidence. Explicit positive memory and disk budgets are required. The binding
also covers the exact registered command, expected outputs, configuration,
provenance, resource budgets, and output root. Canonical preflight admission and
bridge request validation must both succeed before calling the executor.

Execution still requires `BridgeRequest.authorize_execution=True`. Otherwise an
admitted request produces PLANNING and ledger events without launching a child.
Failed admission returns BLOCKED without creating simulation outputs. Changed
bindings create distinct ledger cycles; repeated unchanged requests use the
same cycle and canonical runner resume validation.

The ledger records the complete preflight decision, execution outcome, verified
artifact hashes and lineage, and a release-review event. The return value uses
`AwarenessStudio.RegisteredExecution.v1`. Scientific PASS remains false, formal
Bayes factor remains null, and release authorization remains false. Execution
success is an engineering outcome; reports still require scientific review.

## Validation and remaining scope

`apps/awareness_studio/tests/research_cycle/test_registered_execution.py` launches
a small synthetic arithmetic fixture through the actual executor and verifies
its result and ledger chain. It covers changed seed/configuration, missing
plans, synthetic-to-empirical mislabeling, absent budgets, planning, and resume.
This is not a numerical neuroscience solver benchmark or an empirical study.

The method does not yet connect literature records and generated hypotheses to
experiment records, project the accepted artifacts into the evidence graph, or
invoke the release evaluator. Its release event explicitly requires review.
It also inherits the canonical runner's resource and network enforcement
limitations documented in the overnight integration report. A Python socket
guard is not an operating-system network sandbox.
