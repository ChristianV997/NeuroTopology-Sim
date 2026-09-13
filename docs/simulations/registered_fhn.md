# Registered FHN numerical workload

`tools.simulation_execution.fhn_workload.prepare_spec` writes an explicit
synthetic specification and returns an exact-argv `RegisteredWorkload` plus the
specification SHA-256. Supply the returned workload to a `WorkloadRegistry` and
construct a `BridgeRequest` with the same run ID, revision, configuration, and
seed. Use the checksum as input identity and the module's `SOURCE` and
`DATASET_ID` constants with data mode `synthetic`. The plan must declare matching
identity, revision, seed, and synthetic evidence, then include its reviewed
execution binding before calling `Orchestrator.run_registered`.

All five `FHNConfig` parameters must be explicit finite numbers. Duration and
timestep must be positive; at most 4096 integration steps are admitted. The
worker reads at most 64 KiB of specification data and hashes the exact bytes
that it parses. Changed specs fail before solver import and output creation.
Preparation refuses to overwrite an existing reviewed spec.

The worker reuses `sim.pitnn.hodgkin_huxley_ciss.simulate_fhn` without modifying
its equations. It writes finite `trajectory.json`, `summary.json`, the canonical
RunRecordV1 base schema with explicit execution provenance extensions, and a
completion manifest written last. Outputs include actual computed numerical
metrics, synthetic evidence class, and the model's limitations. No downloads,
external services, or empirical measurements are involved.

The existing solver normalizes voltage by the minimum and maximum of the full
trajectory. This output is therefore unsuitable as a causal online voltage
observation and is not independently calibrated physiological voltage. The
adapter records this limitation explicitly. Its seed is a recorded contract
value; the current deterministic FHN implementation makes no random draws.

Integration testing compares every time, voltage, and recovery sample with a
direct call to the same solver, verifies canonical artifacts and resume, and
rejects a tampered spec. This establishes execution and adapter fidelity; it is
not independent validation of the model's science or numerical convergence.
The release evaluator retains missing source/provenance and other independent
checks as incomplete.
