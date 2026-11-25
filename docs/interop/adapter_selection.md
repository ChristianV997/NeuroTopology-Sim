# Canonical Signal Adapter Selection & Duplicate-Resolution Architecture

## 1. Overview & Objectives

In `NeuroTopology-Sim`, signal ingestion spans multiple ecosystem implementations:
- **PR #212**: Core signal interoperability contracts, schemas, and capability discovery (`shared/interop/contracts.py`, `adapter_registry.py`).
- **PR #214**: MNE/SciPy streaming EEG ingestion path (`sciencer_d/btc_icft/io/eeg_mne_adapter.py`, `eeg_readers.py`).
- **PR #220**: Native dependency-light signal adapters (`shared/interop/adapters/edf_adapter.py`, `brainvision_adapter.py`, etc.).
- **PR #218**: Conformance and audit reports identifying potential functional overlap between #214 and #220.

The canonical adapter-selection layer (`shared/interop/adapter_selection.py`) provides a deterministic, policy-driven arbitration engine. It resolves any signal source (FIF, EDF/BDF, BrainVision, NPY/CSV) to exactly one canonical adapter based on capability evidence, without modifying existing contract roots or deleting adapter implementations.

---

## 2. Selection Policies & Rules

### Rule 1: Evidence-Based Format Resolution
The file format is resolved from explicit declaration (`file_format`) or file extension mapping (`detect_format_from_path`). The selector **never loads a complete recording** into memory merely to identify an adapter; only the file path, extension, and header metadata are probed.

### Rule 2: Strict Constraint & Metadata Preservation
Adapter selection strictly verifies:
- **Channel Order**: Exact channel sequence must be preserved. Any permutation or mismatch between requested and expected metadata triggers `CHANNEL_ORDER_MISMATCH`.
- **Sample Rate**: Must match the declared frequency within numerical tolerance ($10^{-3}$ Hz). Discrepancies trigger `SAMPLE_RATE_MISMATCH`.
- **Montage Provenance**: If 3D sensor coordinates or montage metadata are required, candidates lacking `montage_support` are rejected with `MONTAGE_UNSUPPORTED`.
- **Streaming Support**: Bounded-memory streaming pipelines require `streaming_support=True`; non-streaming candidates are rejected with `STREAMING_UNSUPPORTED`.

### Rule 3: Native Precedence over Fallback
When multiple adapters support a format:
- A **native adapter** (pure-NumPy, minimal dependencies) is preferred over an external library or fallback adapter (e.g. MNE) **only when capability evidence supports it** (dependencies available, constraints satisfied).
- If the native adapter is unavailable (e.g. missing optional dependency), the system selects the fallback adapter (`FALLBACK_SELECTED`, reason `FALLBACK_PRIMARY_UNAVAILABLE`) if `allow_fallback=True`.
- If fallbacks are disallowed (`allow_fallback=False`), the outcome is `UNAVAILABLE` (`DEPENDENCY_MISSING`).

### Rule 4: Ambiguity Refusal
The engine **never silently guesses**. If two competing adapters of the same tier have equal priority and compatible capabilities, selection is explicitly refused with status `AMBIGUOUS` and reason `AMBIGUOUS_CANDIDATES`, prompting an evidence-based override.

### Rule 5: Offline & No-Network Guarantee
The selector never attempts network calls, auto-installations, or remote package resolution. Candidates requiring network are rejected unless `allow_network=True`.

---

## 3. Decision Statuses & Reason Codes

Every selection produces a structured `SelectionResult` with one of six canonical statuses and a specific machine-readable `ReasonCode`:

| Status | Definition | Typical Reason Codes |
| :--- | :--- | :--- |
| `selected` | Single canonical adapter selected unambiguously | `NATIVE_PREFERRED`, `SINGLE_MATCH` |
| `fallback_selected` | Fallback adapter chosen because native is unavailable | `FALLBACK_PRIMARY_UNAVAILABLE` |
| `unavailable` | Adapter exists but required dependency is missing | `DEPENDENCY_MISSING` |
| `ambiguous` | Multiple competing adapters with identical priority | `AMBIGUOUS_CANDIDATES`, `CONFLICTING_ADAPTERS` |
| `incompatible` | Constraints violated (channel order, rate, montage) | `CHANNEL_ORDER_MISMATCH`, `SAMPLE_RATE_MISMATCH`, `MONTAGE_UNSUPPORTED`, `STREAMING_UNSUPPORTED`, `MALFORMED_METADATA`, `NETWORK_NOT_ALLOWED` |
| `unsupported` | No registered candidate supports the file format | `UNSUPPORTED_FORMAT` |

---

## 4. Duplicate & Overlap Resolution

The selector's `detect_duplicates()` function systematically maps ecosystem overlap across open PRs:

| Format | Native Implementation (PR #220) | Library / Fallback (PR #214 / Core) | Selection Policy |
| :--- | :--- | :--- | :--- |
| **EDF / BDF** | `native_edf` (pure-NumPy reader) | `mne_edf` (MNE-based reader) | Native preferred when NumPy is present; MNE selected as fallback if native is unavailable or if advanced MNE transforms are explicitly requested. |
| **BrainVision** | `native_brainvision` (pure-NumPy reader) | `mne_brainvision` (MNE-based reader) | Native preferred for low-overhead streaming; MNE used as verified reference fallback. |
| **FIF** | *None* (Neuromag binary requires parser) | `mne_fif` (MNE-Python reader) | Single match (`mne_fif`) selected via MNE capability. |
| **NPY / CSV** | `numpy_adapter`, `csv_adapter` | *None* | Native single match for bounded arrays and calibration fixtures. |

---

## 5. Usage Example

```python
from shared.interop.adapter_selection import select_adapter, SelectionStatus

# Basic selection from path
result = select_adapter("sub-01_task-rest_eeg.edf")
if result.status == SelectionStatus.SELECTED:
    print(f"Chosen adapter: {result.selected_adapter}")
    print(f"Reason: {result.reason_code.value} - {result.reason_message}")

# Constrained selection requiring montage and streaming
res_strict = select_adapter(
    "sub-02_task-visual_eeg.vhdr",
    require_montage=True,
    require_streaming=True,
    allow_fallback=False,
)
print(res_strict.status, res_strict.selected_adapter)
```

---

## 6. Verification & Test Suite

All tests execute in clean offline environments without third-party dependencies:

```bash
uv run python -m pytest -c /dev/null -o addopts="--import-mode=importlib" tests/interop/test_contracts.py tests/interop/test_registry.py tests/interop_conformance/test_adapter_selection.py
```

### Coverage Summary
- `test_format_detection_from_path`: Extension-based format extraction without I/O.
- `test_one_available_adapter`: Single match resolution.
- `test_two_compatible_adapters_prefer_native`: Verified native priority over fallback.
- `test_fallback_selected_when_native_unavailable`: Fallback degradation handling.
- `test_ambiguous_selection_refused`: Strict refusal on duplicate tie.
- `test_missing_optional_dependency`: Explicit dependency tracking.
- `test_malformed_metadata_rejection`: Guardrails against NaN/negative frequencies or empty channel strings.
- `test_channel_order_mismatch`: Detection of channel permutations.
- `test_sampling_rate_mismatch`: Detection of sampling frequency mismatches.
- `test_montage_provenance_mismatch`: Validation of sensor coordinate capabilities.
- `test_no_network_execution`: Offline enforcement.
- `test_deterministic_repeated_selection`: Repeatability across runs.
- `test_never_loads_complete_recording`: Zero-I/O virtual path resolution.
- `test_detect_duplicates`: Complete ecosystem duplicate inventory.
