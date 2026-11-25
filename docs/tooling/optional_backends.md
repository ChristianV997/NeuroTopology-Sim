# Optional backend capability registry

This registry describes tools that may eventually interoperate with
NeuroTopology-Sim. It probes local importability and records admission state.
It does not install packages, download data, use credentials, or connect to
remote services.

A package name in `configs/tools/optional_backends.yaml` is **not** a support
claim. `scientific_support` is `not_claimed` for every entry.

## Owned files

- `configs/tools/optional_backends.yaml`
- `shared/tooling/capability_registry.py`
- `tests/tooling/`
- `docs/tooling/optional_backends.md`

This work does not modify interop contracts, integration bridges, signal
adapters, CI workflows, Bayesian falsification, streaming kernels, dashboard
routes, AWS code, or QPU code.

## Probe rules

- No optional backend is imported when `shared.tooling` or
  `shared.tooling.capability_registry` is imported.
- Probes are explicit and lazy.
- Missing, unsupported, incompatible, offline-blocked, opt-in-required, and
  error states are distinct.
- `allow_install` is hard-false.
- External services stay opt-in (`allow_remote=true` still does not connect).
- An unavailable tool cannot be replaced by a different scientific method.
- Capability state is serialized as
  `NeuroTopologySim.CapabilityState.v1` for run metadata. The registry does
  not change `RunRecordV1`.

## Classifications

| Classification | Meaning |
|---|---|
| `local_optional_dependency` | Python package that may be probed locally |
| `external_desktop_toolchain` | MATLAB/GUI/desktop tool; not importable here |
| `remote_service_mcp` | Network service; opt-in only |
| `research_reference_only` | Named for documentation; not admitted |
| `unsupported` | Explicitly not admitted |

## Purpose map

These are *appropriateness* notes for future adapters, not enabled pipelines.

### EEG ingestion

Appropriate candidates if later wired and locally available: `mne`, `pynwb`
(local files only). External references: `eeglab`, `fieldtrip`. Not
appropriate: NotebookLM, Semantica, Scrapling, snnTorch.

### MEG ingestion

Appropriate candidates: `mne`, `pynwb` (local files). External reference:
`fieldtrip`.

### Streaming

Named candidates: `pylsl`, `brainflow`. Both are optional-network and not
deterministic-offline. Live ingest stays opt-in. This registry never resolves
streams.

### TDA

None of the registered interoperability tools is a TDA engine. Do not treat
MNE, SciPy, Braindecode, or document tools as persistent homology. Existing
repository TDA code is outside this registry.

### Signal filtering

Appropriate candidates: `scipy_signal`, `mne`. External references: `eeglab`,
`fieldtrip`.

### Spike sorting

Named candidate: `spikeinterface`. This registry does not launch sorter
binaries.

### Neural decoding

Named candidate: `braindecode` (local optional, high memory). `snntorch` is
research reference only and is not selectable.

### Notebook / document research

`notebooklm_mcp` is a remote MCP service and remains opt-in.
`semantica` is research reference only. Neither yields neural observables.

### Artifact mining

`scrapling` and the `neurodata_tooling` umbrella are research reference only.
Web extraction is not a scientific fallback for missing EEG/MEG backends.

## Recording capability state

```python
from shared.tooling.capability_registry import capability_metadata

meta = capability_metadata(offline=True, allow_remote=False)
# attach meta to run metadata without changing RunRecordV1 fields
```

Selecting a backend fails closed:

```python
from shared.tooling.capability_registry import select_backend

select_backend("mne", purpose="eeg_ingestion", offline=True)
```

If `mne` is missing or offline-incompatible, the call raises
`CapabilityAdmissionError`. Callers must not catch that and silently switch to
another method.
