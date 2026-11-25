# Signal Adapters Architecture

## Overview
The `shared/interop/adapters` module implements native signal parsing for NeuroTopology-Sim. Adapters map external neurophysiology formats into canonical `SignalChunk` representations based on the contracts established in PR #212.

## Offline-First & Lazy Dependencies
NeuroTopology-Sim prioritizes a strictly memory-bounded and offline execution path. Many ecosystem tools (like MNE, EEGLAB, NWB) are heavy or require significant network dependencies to install. 

To resolve this, **all adapters employ lazy loading**:
- Importing `shared.interop.adapters` will **never** trigger an `ImportError` even if MNE, PyNWB, or SciPy are missing.
- Calling `Adapter.get_capability()` returns an `AdapterCapability` object, allowing the command center to natively probe the active environment. If a dependency is missing, `availability=False` and `status="unavailable"` is returned safely.

## Supported Formats
### Integrated Adapters
- **MNE FIF (`mne_adapter.py`)**: Streams `.fif` recordings via `mne.io.read_raw_fif(preload=False)`. Memory bounded, allowing large recordings to be chunked.
- **EDF (`edf_adapter.py`)**: Wraps MNE's EDF parser.
- **BrainVision (`brainvision_adapter.py`)**: Wraps MNE's BrainVision parser.
- **NumPy & CSV (`numpy_adapter.py`)**: Raw numerical fallback using `np.load(mmap_mode="r")` for `.npy` arrays, and `np.genfromtxt` for `.csv`.

### Capability Probes
Probes exist for ecosystems we integrate with conceptually, but whose binaries might not be present locally:
- **NWB**: via `pynwb`
- **BrainFlow**: via `brainflow`
- **LSL (Lab Streaming Layer)**: via `pylsl`
- **EEGLAB**: via `eeglabio`
- **FieldTrip**: via `scipy.io` (.mat)

## Adapter Lifecycle
All adapters inherit from `BaseSignalAdapter` and support Python's context manager protocol:
```python
with MneFifAdapter("recording.fif") as adapter:
    for chunk in adapter.iter_chunks(chunk_size=1024):
        print(chunk.data.shape) # (n_channels, 1024)
```

1. **`open()`**: Instantiates the underlying parser (e.g. `mne.io.read_raw`).
2. **`iter_chunks(chunk_size)`**: Yields contiguous `SignalChunk` objects.
3. **`close()`**: Explictly releases file handles (e.g., closing memory maps for `.npy`).
