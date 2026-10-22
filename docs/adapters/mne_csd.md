# MNE Current Source Density (CSD) Adapter

Status: **implemented** under `adapters/mne_csd/`.

Engineering wrapper around the repository’s existing CSD path
(`mne.preprocessing.compute_current_source_density`, already used in
`dual_engine/*` pipelines). This adapter adds **explicit inputs**,
**fail-closed preconditions**, and **output provenance**. It does **not**
introduce a new scientific theory, source-localization method, or claim
about consciousness or neural mechanism.

## Owned paths

- `adapters/mne_csd/`
- `tests/adapters/mne_csd/`
- `docs/adapters/mne_csd.md`

## Upstream API (supported)

| Item | Value |
|---|---|
| Function | `mne.preprocessing.compute_current_source_density` |
| Docs | https://mne.tools/stable/generated/mne.preprocessing.compute_current_source_density.html |
| Source | https://github.com/mne-tools/mne-python/blob/main/mne/preprocessing/_csd.py |
| License | BSD-3-Clause (`https://github.com/mne-tools/mne-python/blob/main/LICENSE.txt`) |
| Project floor | `mne>=1.4.0` (`requirements-eeg.txt`) |
| Verified docs snapshot | MNE 1.13.2 stable documentation |

### Documented parameters (forwarded explicitly)

| Parameter | Default (MNE docs) | Notes |
|---|---|---|
| `sphere` | `"auto"` | `(x, y, z, r)` meters, or `"auto"` digitization fit |
| `lambda2` | `1e-5` | Regularization; MNE requires `0 <= lambda2 < 1` |
| `stiffness` | `4` | Spline stiffness; non-negative |
| `n_legendre_terms` | `50` | Legendre expansion length |
| `copy` | `True` | Must be a real `bool`; the adapter always picks on a copy |

Numeric parameters must be real numbers. Booleans and strings are refused
rather than coerced, so `n_legendre_terms=True` and `lambda2="1e-5"` both fail
closed before MNE is called.

Defaults are taken from the official MNE API documentation / source. They
are **not** Gemini Round 4/5 proposal pins and are not independently
“scientifically validated” by this adapter.

### Units

MNE’s `_csd.py` assigns `FIFF.FIFF_UNIT_V_M2` to transformed EEG channels.
The adapter therefore reports output units as `V/m^2` with
`output_units_status="documented"` when that mapping is established. If the
runtime unit token cannot be mapped for the installed backend/version, units
are reported as **unknown** (never fabricated). The same holds when the backend
reports no unit for the selected channels, or returns no channel info: the
documented unit is not claimed without runtime evidence.

## What the adapter guarantees

1. **Explicit channel selection** — callers must pass `channels=...`. No
   silent “use all EEG” heuristic.
2. **Channel types required** — selected channels must be EEG; others fail closed.
3. **Usable 3D coordinates required** — zero/missing `loc[:3]` fails closed.
   The adapter never fabricates montages or standard-1020 positions.
4. **Coordinate frame reported** when present on the instance.
5. **Sphere / stiffness / lambda2 / n_legendre_terms / copy** recorded in
   provenance and forwarded to the MNE API.
6. **Dropped / excluded channels listed** — channels on the instance that were
   not selected appear in `channels_excluded` / `channels_dropped_report`.
7. **No silent reference mutation** — `alter_reference=True` is refused; the
   adapter never calls `set_eeg_reference`. MNE documents CSD as a
   reference-free Laplacian transform.
8. **Channel order preserved** — output `ch_names` must match the explicit
   selection order or the call fails closed.
9. **Sensor-space vs source localization** — provenance
   `transform_kind=sensor_space_surface_laplacian_csd` and an explicit
   `not_source_localization` note.
10. **Optional MNE** — import is lazy; environments without MNE can still run
    precondition tests. Applying CSD without MNE (and without an injected
    callable) raises `MNEUnavailableError`.

## Public API

```python
from adapters.mne_csd import apply_csd, inspect_preconditions, mne_available

report = inspect_preconditions(raw, channels=["Fz", "Cz", "Pz"])
result = apply_csd(
    raw,
    channels=["Fz", "Cz", "Pz"],
    sphere="auto",          # or (x, y, z, r) in meters
    lambda2=1e-5,
    stiffness=4.0,
    n_legendre_terms=50,
    copy=True,
)
prov = result.provenance.to_dict()
```

## Constant common-reference offset

Per MNE’s documentation, CSD is a Laplacian / “reference-free”
transformation. A spatially constant offset common to all selected channels
is therefore expected to be removed by the upstream transform. This adapter
does not add its own re-referencing step; optional MNE integration tests
check that a constant common offset does not break finiteness / wiring when
MNE is installed. That check is **API/engineering conformance**, not an
independent scientific validation of CSD theory.

## Out of scope

- BIDS ingestion
- Source-space forward models / inverse solvers
- Cochain / Hodge operators
- Production dual_engine pipeline edits
- Real dataset download or participant data
- Consciousness / ontology / clinical claims

## Tests

See `tests/adapters/mne_csd/`. Base tests use duck-typed fixtures and an
injected `csd_callable` (no MNE install required). Optional tests use
`pytest.importorskip("mne")`.
