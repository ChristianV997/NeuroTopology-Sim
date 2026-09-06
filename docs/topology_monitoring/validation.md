# Topology Monitoring Validation

The `topo_monitor.validation` harness rigorously validates the core scientific requirements of the graph-persistence and spatial-phase pipelines in a bounded, offline-capable streaming context.

## Scientific Assertions Guaranteed

1. **Separation of Metrics:** Graph beta-1 (number of independent cycles in adjacency) and spatial topological charge (winding number of the phase field) are strictly separated and evaluated independently to avoid false equivalence.
2. **Invariance:** Node permutations on adjacency arrays strictly preserve the computed Betti-1 Betti curve and Persistence Landscapes.
3. **Thresholding & Sweeps:** Filtration thresholds `[0.1, 0.9]` evaluated on PLV matrices yield bounded, finite, deterministic outputs (never returning NaN or Infinity).
4. **Vortex Geometry:** Analytic phase vortex fixtures map to the exactly predicted integer winding sign and magnitude, while flat fields guarantee exactly 0.0 charge.
5. **Fail-Closed Availability:** Missing spatial coordinates seamlessly degrade into an explicit unavailable state (`null` JSON emission) without crashing the stream.

## Memory & Performance Assertions Guaranteed

1. **Rolling History:** Bounded buffers (max `50` elements) are used for change-point anomaly detection to avoid unbounded heap growth.
2. **Physical Constraints:** Full stream materialization is avoided via standard Python generator blocks. Memory traces (`tracemalloc`) guarantee a flat RSS plateau regardless of infinite stream lengths.
3. **Fallback:** Absence of optional TDA engines (e.g. `ripser`) gracefully yields unavailable topologies rather than throwing unhandled exceptions mid-stream.

## Executing the Validator

Run the standalone bounded generator manually:

```bash
# Markdown report
python scripts/validate_topology_streaming.py --format markdown --steps 20

# JSON payload
python scripts/validate_topology_streaming.py --format json --steps 10
```

*Note: All synthetic data sources are hardcoded inside `topo_monitor.validation.fixtures` and are prominently labeled `demonstration-only`. They must never be injected as empirical evidence into Bayesian falsification modules.*
