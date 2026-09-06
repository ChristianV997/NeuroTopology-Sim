# Memory-Bounded Streaming EEG/MEG Ingestion & Preprocessing Pipeline

## 1. Overview & Architecture

The NeuroTopology-Sim EEG/MEG ingestion pipeline provides a memory-bounded, provenance-rich, montage-aware streaming interface for neurophysiological recordings. Designed to support long-duration recordings without memory exhaustion, the pipeline streams data chunk-by-chunk using Python generators, preserves native sampling rates and channel ordering, extracts sensor geometry in SI units, and executes deterministic signal preprocessing.

```
[EEG/MEG Recording File]
  (.edf, .bdf, .gdf, .set, .vhdr, .fif, .fif.gz, .cnt)
        │
        ▼
[Format Dispatch (preload=False)] ───► [File SHA-256 Checksum]
        │
        ▼
[Montage Resolution & Fallback]
  ├── 1. Raw Dig Montage (SI meters [x, y, z])
  ├── 2. standard_1020 Fallback
  └── 3. standard_1005 Fallback (reports unmatched channels)
        │
        ▼
[iter_mne_signal_chunks] (Generator)
  ├── Shape: (n_channels, n_samples)
  ├── Timestamps: start_s, stop_s, sample_start, sample_end
  ├── Units: V (EEG), T (MEG mag), T/m (MEG grad)
  └── Annotations: Time-windowed slice
        │
        ▼
[Deterministic Preprocessing (scipy.signal)]
  ├── 1. Finite-value verification (rejects NaN/Inf)
  ├── 2. Boundary Cosine Taper (mitigates edge transients)
  ├── 3. IIR Notch Filter (50/60 Hz powerline attenuation)
  ├── 4. SOS Butterworth Bandpass (zero-phase sosfiltfilt)
  ├── 5. Per-Channel Z-Score Normalization
  ├── 6. Hilbert Transform Analytic Phase & Amplitude
  └── 7. Amplitude Validity Masking (noise floor / dropout detection)
```

---

## 2. Supported Formats & Dispatch Table

Reader dispatch is implemented in `sciencer_d/btc_icft/io/eeg_mne_adapter.py` and declared in `sciencer_d/btc_icft/io/eeg_readers.py`. All readers enforce `preload=False` to ensure that data is loaded on demand during chunk iteration rather than buffered into RAM in its entirety.

| Extension | Format Name | MNE Reader Function | Preload Setting |
| :--- | :--- | :--- | :--- |
| `.edf` | European Data Format | `mne.io.read_raw_edf` | `preload=False` |
| `.bdf` | BioSemi 24-bit Data Format | `mne.io.read_raw_bdf` | `preload=False` |
| `.gdf` | General Data Format | `mne.io.read_raw_gdf` | `preload=False` |
| `.set`, `.fdt` | EEGLAB | `mne.io.read_raw_eeglab` | `preload=False` |
| `.vhdr`, `.vmrk`, `.eeg` | BrainVision | `mne.io.read_raw_brainvision` | `preload=False` |
| `.fif`, `.fif.gz` | Neuromag / Elekta / MNE | `mne.io.read_raw_fif` | `preload=False` |
| `.cnt` | Neuroscan | `mne.io.read_raw_cnt` | `preload=False` |

MNE is an **optional dependency** imported lazily inside reader functions (`importlib.import_module("mne")`). If MNE is not installed, the pipeline fails gracefully without crashing imports, and standard capability inspection reports reflect `dependency_not_installed`.

---

## 3. Streaming Generator API

### `iter_mne_signal_chunks`

```python
from sciencer_d.btc_icft.io.eeg_mne_adapter import iter_mne_signal_chunks

for chunk in iter_mne_signal_chunks(
    path="recording.fif",
    chunk_seconds=2.0,
    picks=["Fp1", "Fp2", "Fz", "Cz", "Pz", "Oz"],
    start_s=0.0,
    stop_s=60.0,
    return_dict=False,
):
    print(f"Chunk {chunk.chunk_index}: {chunk.data.shape} samples ({chunk.chunk_start_s:.2f}s - {chunk.chunk_end_s:.2f}s)")
```

### `MNESignalChunk` Fields

| Field | Type | Description |
| :--- | :--- | :--- |
| `chunk_index` | `int` | Sequential 0-indexed chunk identifier |
| `chunk_start_s` | `float` | Exact chunk start time in seconds |
| `chunk_end_s` | `float` | Exact chunk end time in seconds |
| `sample_start` | `int` | Start sample index in recording |
| `sample_end` | `int` | End sample index in recording |
| `sfreq` | `float` | Native sampling rate in Hz |
| `n_channels` | `int` | Number of channels |
| `n_samples` | `int` | Number of samples in current chunk |
| `channel_names` | `list[str]` | Channel names in native or picked order |
| `channel_types` | `list[str]` | Channel modalities (`'eeg'`, `'mag'`, `'grad'`, etc.) |
| `units` | `dict[str, str]` | SI units per channel (`'V'` for EEG, `'T'` for MEG) |
| `data` | `ndarray` | Numeric 2D array of shape `(n_channels, n_samples)` |
| `annotations` | `list[dict]` | Annotations/events active during this time slice |
| `source_file` | `str` | Normalized file path |
| `source_sha256` | `str` | SHA-256 cryptographic digest of source file |
| `montage_coordinates` | `dict[str, list[float]]` | 3D sensor coordinates `[x, y, z]` in meters |
| `montage_source` | `str` | Source of montage (`'raw_montage'`, `'standard_1020'`, `'standard_1005'`, `'none'`) |
| `unmatched_channels` | `list[str]` | Channels without resolved 3D coordinates |
| `warnings` | `list[str]` | Inspection warnings or quality flags |

---

## 4. Montage Resolution & Sensor Geometries

Electrode positions are required for downstream 2D/3D topological phase gradients and spatial winding metrics. The pipeline resolves coordinates in three hierarchical tiers:

1. **Native Raw Montage (`raw_montage`)**: If the recording header contains non-zero digitizer coordinates (`raw.info['chs'][i]['loc'][:3]`), these are extracted directly in SI meters.
2. **Standard 10-20 Fallback (`standard_1020`)**: If native coordinates are absent, channel names are matched against the international 10-20 standard montage (e.g. `Fp1`, `Fz`, `Cz`, `Pz`, `Oz`). Name normalization strips casing and common prefixes (`"EEG "`, `"EEG-"`).
3. **Standard 10-05 Fallback (`standard_1005`)**: Used for high-density montages.
4. **Unmatched Channel Reporting**: Any electrode names not present in the reference montage (such as auxiliary, reference, or custom channels) are added to `unmatched_channels` and recorded with explicit warnings. No coordinates are fabricated.

---

## 5. Deterministic Signal Preprocessing Pipeline

Preprocessing routines in `validation/analytic_phase.py` provide zero-phase signal conditioning:

```python
from validation.analytic_phase import preprocess_signal_pipeline

res = preprocess_signal_pipeline(
    data=chunk.data,
    sfreq=chunk.sfreq,
    low_hz=8.0,
    high_hz=13.0,
    notch_hz=50.0,
    zscore=True,
    order=4,
    apply_taper=True,
    min_amplitude_quantile=0.05,
)

filtered = res["filtered_data"]    # (n_channels, n_samples)
phase = res["phase"]                # values in (-pi, pi]
amplitude = res["amplitude"]        # non-negative instantaneous amplitude
validity_mask = res["validity_mask"]# boolean mask (True where amplitude >= noise floor)
provenance = res["provenance"]      # dict detailing exact parameters
```

### Preprocessing Operations

1. **Finite Value Validation (`validate_signal_finite`)**: Checks that array contains strictly finite numbers; raises `ValueError` if `NaN` or `Inf` are present.
2. **Boundary Cosine Taper (`apply_boundary_taper`)**: Applies a half-cosine taper to the initial and final 5% of chunk samples to minimize filter edge transients.
3. **Notch Filter (`notch_filter`)**: Zero-phase IIR notch filter (`scipy.signal.iirnotch` + `scipy.signal.filtfilt`) attenuating 50 Hz or 60 Hz powerline contamination by > 40 dB without phase distortion.
4. **SOS Butterworth Bandpass (`bandpass_filter_sos`)**: Second-Order Sections (SOS) bandpass filtering with `scipy.signal.sosfiltfilt` ensuring numerical stability and zero phase distortion.
5. **Per-Channel Z-Score (`zscore_normalize`)**: Normalizes each channel to zero mean and unit variance, with division-by-zero protection.
6. **Hilbert Analytic Signal (`compute_analytic_signal`)**: Computes the analytic signal via Hilbert transform, yielding instantaneous phase in $(-\pi, \pi]$ and instantaneous amplitude.
7. **Amplitude Validity Mask (`amplitude_validity_mask`)**: Identifies low-amplitude flatline periods or dropouts below a configurable quantile or absolute noise threshold.
8. **Provenance Tracking**: All applied filter parameters, frequencies, orders, and normalization statistics are logged in `res["provenance"]`.

---

## 6. Scientific Guardrails & Invariants

- **No Clinical Claims**: This pipeline performs signal processing and feature extraction scaffolding. It does not provide medical diagnosis, monitoring, or clinical assessment.
- **No Consciousness or Ontological Claims**: Signal phases and topological metrics describe geometric and dynamic properties of electromagnetic fields; they do not substantiate metaphysical or consciousness hypotheses.
- **Explicit Provenance**: Every yielded chunk records its source file path, source file SHA-256 digest, and applied transformation metadata.
- **Synthetic Test Fixtures**: All unit tests run against explicitly generated synthetic waveforms with deterministic seeds; no real empirical data is downloaded or spoofed.
- **Bounded Memory Guarantee**: Data is read exclusively in slices (`raw.get_data(...)`) from non-preloaded file pointers (`preload=False`).
