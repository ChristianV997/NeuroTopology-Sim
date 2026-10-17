# Spherical-spline CSD (NumPy production surface)

**Status:** HOLD / SYNTHETIC_ONLY  
**Module:** `neurotopology_sim.experimental.preprocessing.spherical_csd`  
**Owner:** Batch 2 / Cursor Agent C (sole production writer for this path)

## Scope

Sensor-space spherical-spline surface Laplacian / current source density (CSD).
Not anatomical source localization. Not a clinical or ontology claim.

## Pinned MNE

| Field | Value |
|---|---|
| Version | 1.13.2 |
| Tag | v1.13.2 |
| Commit | `bf67729b805865b5bb0f2f97621e416278efd1b2` |
| License | BSD-3-Clause |
| Sources | `mne/preprocessing/_csd.py`, `mne/channels/interpolation.py` |
| Defaults | `lambda2=1e-5`, `stiffness=4`, `n_legendre_terms=50` |

Mathematical source: Perrin et al. spherical splines (1987, 1989), as
implemented in the pinned MNE release.

## API

```python
from neurotopology_sim.experimental.preprocessing import (
    SphericalCSDConfig,
    compute_spherical_csd_transform,
    apply_spherical_csd,
)

cfg = SphericalCSDConfig(sphere=(0.0, 0.0, 0.0, 0.095))  # meters; no "auto"
result = compute_spherical_csd_transform(positions_m, cfg, channel_names=names)
csd = apply_spherical_csd(result.transform, data_volts)  # -> V/m^2
```

- Full N×N matrix; channel order is the row order of `positions`.
- Rejects non-finite / zero coordinates, sphere `"auto"`, nearly coincident
  sensors, and ill-conditioned `G + λ²I`.
- Average-reference null: `||M @ 1||_∞` checked fail-closed.
- Scaling: `1/R²` with R in meters → output unit `V/m²` for volt inputs.

## Relation to other surfaces

| Surface | Role |
|---|---|
| This module | NumPy operator (matrix + apply) |
| `adapters/mne_csd` (PR #378) | Thin wrapper around MNE instance API |
| `tools/mne_csd_reference_audit` (PR #402) | Independent audit reference (not production) |
| Antigravity Agent C | Independent conformance tests/fixtures (do not edit here) |

## Tests

```bash
python -m pytest tests/neurotopology_sim/experimental/preprocessing/test_spherical_csd.py -q
```

Optional live-MNE full-matrix parity skips when MNE is not installed (this
lane does not install optional EEG deps).
