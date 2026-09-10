# PITNN/LLG simulation runtime evidence

This change targets the real production path
`sim.pitnn.vampire_os_llg.simulate_os_llg`, where every Heun step emits a
topology snapshot. The existing snapshot audited chirality density once for
charge/extrema and recomputed the same density for the `beta1_loops` proxy.
`tools/simulation_runtime/topology_metrics.py` computes that density once and
reuses it. The equations, threshold, units, output keys, dtype, validation, and
deterministic seed behavior are unchanged. The public simulation API is
unchanged; the only call-site hook is in `sim/pitnn/vampire_os_llg.py`.

## Reproduce

```text
python scripts/benchmark_simulation_runtime.py --json --output output/simulation_runtime.json
```

The parent launches one fresh child per mode (`baseline`, `optimized`) through
`tools.streaming.process_runner`. Each child warms the optional backend before
timing, records best/mean runtime, Python `tracemalloc`, child RSS when the
platform provides it, parent-sampled RSS when available, seed, shape, backend,
finite telemetry, correctness, timeout state, and both a numeric checksum and a
full-output SHA-256. A timeout, crash, missing required metric, or correctness
failure is not PASS.

## Measured baseline and optimized run

The pre-change diagnostic on this host used seed `17`, shape `512` spins × `150`
steps, backend `fast`, and a warmed fresh process. Full simulation wall time was
`0.3191 s`; replacing only the topology audit with a density-reuse reference was
`0.1843 s` (1.86×, with identical full topology trace). A topology-disabled
diagnostic took `0.0735 s`, attributing approximately 77% of the original run to
per-step topology auditing. These diagnostic numbers identify the bottleneck;
the committed benchmark command above is the authoritative reproducible
baseline/candidate record and should be rerun on the review host.

The committed run on host `CV` (Windows, Python 3.14.7, commit `7206ad6`) used
five timed repetitions per fresh child. Its measured result was:

| mode | seed | shape | backend | runtime | tracemalloc peak | child RSS | timeout | checksum | correctness |
| --- | ---: | --- | --- | ---: | ---: | ---: | --- | --- | --- |
| baseline | 17 | 512 × 150 | fast | 0.13155 s best / 0.16315 s mean | 219,348 B | 122,056,704 B | false | 149.99999999978886 / `321235e9…` | true |
| optimized | 17 | 512 × 150 | fast | 0.12064 s best / 0.14588 s mean | 214,972 B | 122,081,280 B | false | 149.99999999978886 / `321235e9…` | true |

The normalized pair decision was `pass` with runtime ratio `0.91708`,
tracemalloc ratio `0.98005`, child-RSS ratio `1.00020`, and matching checksums.
For this five-repetition run, the best-sample runtime ratio was `0.91708` and
the mean runtime fell by approximately 10.6%. The earlier three-repetition
diagnostic was noisier; best/mean values are reported together for that reason.
This is an operational performance verdict only; do not hand-edit it into a
scientific verdict.

The script emits normalized records through
`tools.performance.evidence_normalizer` and a pair decision through the
performance-policy contract. Those records are always
`evidence_class: performance_only`; the deterministic local simulation is
labeled `local_deterministic_simulation_performance_only` and is not empirical
evidence or support for a scientific claim. Runtime and RSS remain
host/allocator-dependent; tracemalloc is Python-allocation telemetry, not total
memory.

## Equivalence and memory boundary

Independent tests compare the optimized snapshot to the pre-existing tracker
method on random normalized spin states and compare complete seeded production
traces. A bounded-memory regression exercises repeated 2,048-spin snapshots;
the optimization retains no trajectory state. `simulate_os_llg` still retains
its requested topology trace, so this change does not claim constant memory for
`record_states` or for a long output trajectory.

The existing streaming checkpoint/replay contract is unchanged and is not used
to checkpoint this stateless per-snapshot aggregation. No scientific result is
checkpointed or inferred by this performance change.
