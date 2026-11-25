# Dual-Engine Topological Framework

A shared instrumentation layer that runs the **same** topological + non-equilibrium
thermodynamic analysis on two very different kinds of input:

- **Cortical phase maps** from real BIDS EEG (via the merged `data/bids_ingest.py`), and
- **Quantum field grids** from HDF5 (complex scalar / spinor / gauge configurations).

Both are reduced to a common **SU(2) order-parameter field** and analysed identically.

The current adapter is a fixed-axis U(1) phase embedding in SU(2), not a general
three-dimensional SU(2) field. Its reported Q and Q_abs refer to phase-winding
statistics on 2D slices, not the 3D Skyrme degree. A stack of time windows must
not be interpreted as a 3D spatial volume. General SU(2) field construction is
available separately in `field_theory.su2`; no neural interpretation is implied.

> **Reality-first, no equivalence asserted.** This framework computes and reports numbers.
> It does **not** claim that a cortical process and a quantum field are the same system, and
> it does **not** claim any spectral-dimension convergence target. Such claims require real
> datasets and are explicitly out of scope of the code here.

## Modules

| File | Purpose |
|---|---|
| `su2_field_mapper.py` | Lift a phase field `theta(x)` into a genuine SU(2) field `U = exp(i·theta·n̂·σ)` (unitarity + det=1 verified). |
| `topology_engine.py` | Unified `Q`, `Q_abs`, `f_dress` (via `core.topology`) + `beta1` (real persistent homology, `ripser`) + spectral dimension `d_s`. |
| `data_adapters.py` | `DataLoader` ABC; `NeuroBIDSAdapter` (real EEG → Hilbert phase maps) and `QuantumFieldAdapter` (HDF5 → phase-winding field). |
| `action_auditor.py` | Landau–Ginzburg free energy `F`, entropy-production rate `Σ̇` (stochastic-area irreversibility estimator), generalized action `S_Ω` trend. |
| `benchmark.py` | Side-by-side collision benchmark on **synthetic** proxies; emits provenance-stamped JSON + figure. |

Every field and output carries `provenance ∈ {real_bids, synthetic_proxy, quantum_field}`.

## Run the synthetic benchmark (fully offline)

```bash
bash run_benchmarks.sh
# -> outputs/dual_engine/collision_benchmark.{json,png}
```

## Run on REAL data

```bash
# Real EEG (e.g. OpenNeuro ds003969 / ds000245), synced locally:
aws s3 sync --no-sign-request s3://openneuro.org/ds003969 /data/ds003969
BIDS_ROOT=/data/ds003969 bash run_benchmarks.sh
#   -> outputs/dual_engine/real_neuro_result.json   (provenance: real_bids)

# Real quantum field grid in HDF5 (complex 'psi', or real/imag pair, or a 'phase' array):
QFIELD_H5=/data/spinor_bec.h5 bash run_benchmarks.sh
#   -> outputs/dual_engine/real_quantum_result.json (provenance: quantum_field)

# Programmatic use:
python - <<'PY'
from dual_engine.data_adapters import NeuroBIDSAdapter, QuantumFieldAdapter
from dual_engine.topology_engine import analyze_windows
from dual_engine.action_auditor import audit_field

f = NeuroBIDSAdapter("/data/ds003969").load_su2_field(subject="01", task="rest", n_windows=8)
print(f.provenance, [r.Q_abs for r in analyze_windows(f)], audit_field(f).Sigma_dot)
PY
```

## Tests

```bash
python -m pytest tests/test_dual_engine.py -q     # 15 tests, offline
```

