# Quantum-source → membrane relay (synthetic / model-only)

**Disposition:** `HOLD / SYNTHETIC_MODEL_ONLY`

**Package:** `neurotopology_sim/experimental/quantum_source_membrane_relay/`

## Purpose

Test a **concrete cross-scale interface**:

1. Open-quantum sink event flux \(\varphi(t)=\gamma\rho_{ee}(t)\) [s⁻¹].
2. Integrated yield \(Y=\int_0^T\varphi(t)\,dt\) [dimensionless].
3. Fixed gain map \(I_\mathrm{offset}(t)=g\,\varphi(t)\) with \(g\) in seconds.
4. FHN membrane response under a **shared** affine voltage calibration.

This is **not** evidence of biological quantum function, consciousness, Orch OR, or clinical effect.

## FHN audit

`sim.pitnn.hodgkin_huxley_ciss.simulate_fhn` converts dimensionless \(v\) to volts by **per-trajectory min–max**. That independently rescales every run and must not be used for cross-arm amplitude comparisons. This package uses `integrate_fhn_fixed_calibration` instead:

\[
V(t)=V_\mathrm{rest}+S\cdot v(t)
\]

with fixed \(V_\mathrm{rest}\) and \(S\) for all arms.

## Arms

| Arm | Source | Gain |
|---|---|---|
| `quantum_coupled` | two-level Lindblad sink | \(g>0\) |
| `classical_matched` | constant flux, same \(Y\) and support duration | same \(g\) |
| `no_source` | \(\varphi=0\) | n/a |
| `no_coupling` | quantum \(\varphi\) computed | \(g=0\) |

## Equations and units

| Symbol | Meaning | Units |
|---|---|---|
| \(\omega\) | splitting | rad/s |
| \(\gamma\) | sink rate | s⁻¹ |
| \(\rho\) | density matrix | dimensionless |
| \(\varphi=\gamma\rho_{ee}\) | event flux | s⁻¹ |
| \(Y=\int\varphi\,dt\) | reaction yield | 1 |
| \(g\) | relay gain | s |
| \(I_\mathrm{offset}=g\varphi\) | FHN current offset | dimensionless |
| \(V\) | calibrated voltage | V |

## Run tests

```bash
cd /path/to/NeuroTopology-Sim
PYTHONPATH=. python3 -m unittest \
  tests.neurotopology_sim.experimental.quantum_source_membrane_relay.test_quantum_source_membrane_relay -v
```
