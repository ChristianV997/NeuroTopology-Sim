# Registered FHN local smoke path

The registered FHN workload is a deterministic engineering smoke path for the
existing `sim.pitnn.hodgkin_huxley_ciss.simulate_fhn` implementation. It does
not add or modify solver equations, download data, or make a scientific claim.

`tools.simulation_execution.fhn_workload.prepare_spec` writes an immutable,
finite specification and returns an exact-argv `RegisteredWorkload`. The
Awareness Studio `SimulationBridge` accepts that registration, requires an
explicit code revision, seed, provenance, and resource budgets, and delegates
the child process to `tools.simulation_execution.runner.run_plan`.

The child writes `trajectory.json`, `summary.json`, `RunRecord.json`, and a
completion `unit_manifest.json` last. The bridge imports nothing until the
canonical checksums, output containment, finite JSON, RunRecord identity,
synthetic classification, and read-only `tools.simulation_artifacts.extractor`
lineage report all agree.

The resulting class is always `synthetic_demo_only`. The release evaluator can
therefore return `SYNTHETIC_ONLY` for a complete smoke run, while its report
still emits no scientific PASS, Bayes factor, causal promotion, or empirical
evidence. The model's full-trajectory voltage normalization is recorded as a
limitation in the RunRecord.
