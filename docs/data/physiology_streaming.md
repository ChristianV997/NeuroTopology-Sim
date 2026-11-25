# Memory-Bounded Multimodal Physiology Streaming Loader

## Overview

The `PhysiologyStreamReader` provides a memory-bounded, offline-first ingestion pipeline for multimodal physiological signals, spanning electroencephalography (EEG), electrocardiography (ECG), respiration (RESP), photoplethysmography (PPG), galvanic skin response / electrodermal activity (GSR/EDA), electromyography (EMG), electrooculography (EOG), and temperature.

The architecture is explicitly designed for large-scale, continuous recordings where loading entire raw files into memory would exhaust system resources or introduce unconstrained memory overhead. Slicing is performed lazily with `preload=False` unconditionally enforced.

```
+-------------------------------------------------------------------------------+
|                             Raw Multimodal File                               |
|                  (FIF, FIF.GZ, EDF, BDF, BrainVision .vhdr)                   |
+-------------------------------------------------------------------------------+
                                       |
                                       | preload=False (Zero-copy on disk)
                                       v
+-------------------------------------------------------------------------------+
|                           PhysiologyStreamReader                              |
|  - Extension & Format Validation                                              |
|  - Channel Modality Classification (EEG, ECG, RESP, GSR, PPG, EMG, EOG, etc.) |
|  - Capability Discovery (AVAILABLE, MISSING_DEPENDENCY, UNSUPPORTED, etc.)    |
|  - Synthetic / Empirical Provenance Detection                                 |
+-------------------------------------------------------------------------------+
           |                                                       |
           | iter_chunks(chunk_duration_s=1.0)                     | compute_summary()
           v                                                       v
+------------------------------------+           +------------------------------------+
|          PhysiologyChunk           |           |         PhysiologySummary          |
|  - Sliced time window data array   |           |  - Channel inventory & metadata    |
|  - Causal multi-rate resampling    |           |  - Respiratory metrics (Rate, I:E) |
|  - Timestamps & finite status      |           |  - Cardiac & HRV (HR, RMSSD, SDNN) |
|  - Bad channel flags & provenance  |           |  - Quality & missingness ratios    |
|  - Common clock alignment metadata |           |  - Deterministic SHA-256 checksum  |
+------------------------------------+           +------------------------------------+
```

---

## Modality Taxonomy & Channel Classification

Channels are classified deterministically based on standard naming conventions and MNE channel descriptor types:

| Channel Modality | Type Enum | Typical Match Patterns | Standard Units |
| :--- | :--- | :--- | :--- |
| **EEG** | `PhysiologyChannelType.EEG` | 10-20 electrode labels (`Fp1`, `Cz`, `O2`, etc.) or MNE type `EEG` | `V` |
| **ECG** | `PhysiologyChannelType.ECG` | `ECG`, `EKG`, `HEART`, `CARDIAC` or MNE type `ECG` | `V` |
| **Respiration** | `PhysiologyChannelType.RESPIRATION` | `RESP`, `CHEST`, `ABDOMEN`, `THORACIC`, `BREATH`, `AIRFLOW`, `PNEUMO` | `arbitrary_expansion` |
| **GSR / EDA** | `PhysiologyChannelType.GSR_EDA` | `GSR`, `EDA`, `GALVANIC`, `SKIN_COND` | `uS` |
| **PPG** | `PhysiologyChannelType.PPG` | `PPG`, `PLETH`, `PULSE` | `arbitrary_optical` |
| **EMG** | `PhysiologyChannelType.EMG` | `EMG`, `CHIN`, `MASSETER` or MNE type `EMG` | `V` |
| **EOG** | `PhysiologyChannelType.EOG` | `EOG`, `VEOG`, `HEOG` or MNE type `EOG` | `V` |
| **Temperature** | `PhysiologyChannelType.TEMPERATURE` | `TEMP`, `THERM` | `degC` |
| **Other Physiology**| `PhysiologyChannelType.OTHER_PHYSIOLOGY` | Unmatched auxiliary physiological signals | `arbitrary` |

---

## Multi-Rate Synchronization & Causal Alignment

Multimodal physiology acquisition frequently records heterogeneous modalities at disparate native sampling rates (e.g., EEG at 500 Hz, ECG at 250 Hz, respiration at 25–100 Hz).

### Causal Linear Interpolation

When a common clock sampling rate is requested via `common_sfreq_hz`, `PhysiologyStreamReader` enforces strictly causal interpolation:
- For any target timestamp $t_k$, the interpolated sample is evaluated strictly using surrounding historical positions from the source stream:
  $$x(t_k) = (1 - w) \cdot x[i] + w \cdot x[i+1]$$
  where $i = \lfloor t_k \cdot f_s \rfloor$ and $w = t_k \cdot f_s - i$.
- In `AlignmentMode.CAUSAL`, no future samples beyond the current window boundary are accessible, preventing anticausal information leakage into downstream online or topological filters.

### Resampling Provenance

Every chunk and summary artifact maintains full provenance in `ResamplingMetadata`:
- `source_sfreq_hz`: Native device sampling rate in Hz.
- `target_sfreq_hz`: Target common clock sampling rate in Hz.
- `ratio`: $f_{target} / f_{source}$.
- `method`: Identifier of the resampling operator (e.g., `identity` or `causal_linear_interpolation`).
- `interpolated`: Boolean flag indicating whether interpolation was performed.

---

## Feature Extraction & Quality Assessment

### Respiratory Dynamics

Feature extraction is performed via bounded zero-crossing analysis:
- **Zero-Crossing Detection**: Identifies positive-going zero crossings on the mean-subtracted signal.
- **Cycle Threshold Constraint**: At least 2 full breath cycles ($\ge 2$ positive zero crossings) are strictly required. If fewer than 2 cycles exist, `respiratory_rate_bpm`, `inspiratory_duration_s`, `expiratory_duration_s`, `ie_ratio`, and `respiratory_phase_rad` remain `None` (`null` in JSON).
- **Inspiratory / Expiratory (I:E) Ratio**: Breath cycles are partitioned into inspiration (from onset to cycle peak) and expiration (from cycle peak to next onset). The mean inspiratory duration divided by mean expiratory duration yields the I:E ratio.
- **Instantaneous Phase**: Normalized to $[-\pi, \pi)$ relative to the final zero crossing in the window.

### Cardiac & Heart Rate Variability (HRV)

- **R-Peak Detection**: Evaluates positive peaks exceeding $\mu + 1.5\sigma$ with a minimum refractory window of 300 ms (corresponding to an upper physiological bound of 200 BPM).
- **RR Intervals**: Extracted in milliseconds ($RR_i = (p_{i+1} - p_i) / f_s \times 1000$).
- **SDNN**: Standard deviation of NN (RR) intervals:
  $$\text{SDNN} = \sqrt{\frac{1}{N-1}\sum_{i=1}^N (RR_i - \overline{RR})^2}$$
- **RMSSD**: Root mean square of successive differences:
  $$\text{RMSSD} = \sqrt{\frac{1}{N-1}\sum_{i=1}^{N-1} (RR_{i+1} - RR_i)^2}$$

### Quality & Missingness Tracking

- **Missingness Ratio**: Proportion of primary multimodal channels (EEG, ECG, RESP) missing from the recording.
- **Finite Ratio**: Proportion of samples exhibiting finite numeric values ($-\infty < x < \infty$).
- **Strict Null-Safety**: No `NaN` or `Infinity` values are permitted in serialized reports; absent features serialize strictly as `null`.
- **SHA-256 Cryptographic Checksum**: The canonical JSON representation (sorted keys, compact separators, report checksum field zeroed) is hashed with SHA-256 to ensure data and report tamper-evidence.

---

## Strict Scientific Guardrails

All modules, CLI utilities, and downstream pipelines consuming physiology streams must enforce the following scientific boundaries:

> [!IMPORTANT]
> 1. **Candidate Mechanism Only:** Physiological coupling between central (EEG) and autonomic (ECG, RESP) signals is an empirical candidate mechanism, **not proof of a mental-state transition**.
> 2. **No Subjective State Equivalence:** Autonomic indicators (such as respiratory slowing, vagal tone increase, or elevated HRV / RMSSD) must **never be described as equivalent to calmness, detachment, equanimity, or liberation**.
> 3. **No Label Inference:** File paths, participant identifiers, or metadata strings containing keywords such as `awake`, `sedated`, `meditation`, `jhana`, or `arousal` must **never be used to infer mental or cognitive states**. Operator-supplied labels must be preserved verbatim in `supplied_labels` without interpretive inference.
> 4. **Synthetic Data Separation:** Synthetic or mock signals are explicitly marked with `is_synthetic=True` and cannot be cited as empirical evidence.
> 5. **Absence of Proof Claims:** No claim of final theory, consciousness resolution, or TOE validation is permitted.

---

## Programmatic API Usage

### Iterating Over Bounded Chunks

```python
from pathlib import Path
from shared.data_loaders.physiology_stream import PhysiologyStreamReader
from shared.data_loaders.physiology_types import AlignmentMode

reader = PhysiologyStreamReader(
    source_path=Path("path/to/recording.fif"),
    common_sfreq_hz=250.0,
    alignment_mode=AlignmentMode.CAUSAL,
    provenance_hint="empirical",
)

if reader.capability_state == "AVAILABLE":
    for chunk in reader.iter_chunks(chunk_duration_s=2.0, max_chunks=10):
        print(f"Chunk {chunk.chunk_index}: {chunk.data.shape} samples at {chunk.sample_rate_hz} Hz")
        print(f"  Start: {chunk.start_time_s:.2f}s, End: {chunk.end_time_s:.2f}s")
        print(f"  Finite: {chunk.finite_status}, Checksum: {chunk.source_checksum[:8]}...")
```

### Computing Feature Summaries

```python
summary = reader.compute_summary(max_samples=4096)
json_report = summary.to_json(indent=2)
print(json_report)
```

---

## CLI Inspection Tool

The `scripts/inspect_physiology_stream.py` tool provides command-line inspection and feature extraction:

### Usage Syntax

```bash
python scripts/inspect_physiology_stream.py <target_file> [options]
```

### Options

- `target`: Path to recording file (`.fif`, `.fif.gz`, `.edf`, `.bdf`, `.vhdr`).
- `--chunk-duration-s FLOAT`: Chunk duration in seconds (default: `1.0`).
- `--common-sfreq-hz FLOAT`: Optional common clock sampling frequency in Hz.
- `--alignment-mode {causal,noncausal}`: Resampling interpolation mode (default: `causal`).
- `--max-chunks INT`: Maximum number of chunks to inspect (default: `5`).
- `--format {json,markdown}`: Output serialization format (default: `json`).
- `-o, --output PATH`: Write output report to a file.
- `--quiet`: Suppress stdout output.

### Examples

```bash
# Inspect an EDF recording and output Markdown
python scripts/inspect_physiology_stream.py data/sub-01_task-rest_eeg.edf --format markdown

# Stream with causal resampling to 250 Hz and export JSON report
python scripts/inspect_physiology_stream.py data/sub-01_physio.fif --common-sfreq-hz 250.0 --alignment-mode causal -o report.json
```
