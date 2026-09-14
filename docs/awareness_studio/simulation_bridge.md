# Awareness Studio simulation bridge

`awareness_studio.simulation_bridge` is a fail-closed adapter over the
canonical bounded local executor. It is not a solver and does not accept free-
form commands. Callers must register an exact argv and declare every expected
relative output before requesting execution.

Execution requires local-only mode, explicit timeout/memory/disk budgets,
finite configuration, a stable input identity, and non-placeholder provenance.
After the executor reports `PASS`, the bridge verifies every checksum and
finite JSON artifact, binds `RunRecord.json` to the request's run ID, code
revision, seed, configuration, input identity, and provenance, then invokes the
read-only simulation artifact extractor. Any malformed, nonfinite, incomplete,
unexpected, or provenance-inconsistent output is rejected and no artifact is
accepted.

`BridgeResult.release_review()` projects only verified operational facts into
the existing release-evidence evaluator. A successful FHN smoke run remains
`synthetic_demo_only` / `SYNTHETIC_ONLY`; this is engineering execution
evidence, not a scientific result. Network, dataset, streaming, claim, and
literature code are outside this bridge.
