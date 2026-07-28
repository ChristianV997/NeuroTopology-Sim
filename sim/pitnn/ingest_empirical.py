"""Offline empirical EEG/fMRI ingestion for PITNN.

CSV/NPY and local MNE files are supported. No dataset identifier is resolved
and no network operation is performed. Signal arrays use shape `(samples,
channels)` and amplitudes are z-scored per channel.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import csv
import numpy as np
from scipy.signal import hilbert


@dataclass(frozen=True)
class EmpiricalSignal:
    """Normalized multichannel signal and analytic phase in radians."""
    data: np.ndarray
    analytic: np.ndarray
    phase: np.ndarray
    sample_rate_hz: float
    source: str

    @property
    def macro_signal(self) -> np.ndarray:
        """Return a deterministic phase-derived scalar for macro-TDA input."""
        return np.mean(np.sin(self.phase), axis=1)


@dataclass(frozen=True)
class LabeledFeatureTable:
    """Numeric PITNN features with the window-level state labels retained."""
    data: np.ndarray
    states: tuple[str, ...]
    subjects: tuple[str, ...]
    feature_names: tuple[str, ...]


def _normalize(data: np.ndarray) -> np.ndarray:
    values = np.asarray(data, dtype=float)
    if values.ndim == 1:
        values = values[:, None]
    if values.ndim != 2 or values.shape[0] < 8 or values.shape[1] < 1 or not np.all(np.isfinite(values)):
        raise ValueError("empirical data must be finite with shape (samples>=8, channels>=1)")
    centered = values - np.mean(values, axis=0, keepdims=True)
    scale = np.std(centered, axis=0, keepdims=True)
    if np.any(scale <= np.finfo(float).eps):
        raise ValueError("empirical channels must have non-zero variance")
    return centered / scale


def _read_tabular(path: Path) -> np.ndarray:
    if path.suffix.lower() == ".npy":
        return np.asarray(np.load(path, allow_pickle=False), dtype=float)
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        raise ValueError("empty CSV")
    parsed: list[list[float]] = []
    for row in rows:
        try:
            parsed.append([float(item) for item in row])
        except ValueError:
            if not parsed:
                continue  # one optional header row
            raise ValueError("CSV contains non-numeric data after its header")
    if not parsed:
        raise ValueError("CSV contains no numeric rows")
    width = len(parsed[0])
    if any(len(row) != width for row in parsed):
        raise ValueError("CSV rows have inconsistent column counts")
    return np.asarray(parsed, dtype=float)


def ingest_labeled_features(path: str | Path,
                            feature_names: tuple[str, ...] = (
                                "q_net", "q_abs", "f_dress", "defect_density",
                            )) -> LabeledFeatureTable:
    """Read the ds005620 PITNN window CSV without treating metadata as signal.

    The tier-1 converter emits ``subject_id`` and ``state`` string columns next
    to numeric topology features.  The generic empirical reader intentionally
    rejects such mixed CSVs; this explicit adapter keeps that contract strict
    while making the labeled handoff usable by downstream analyses.
    """
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.suffix.lower() != ".csv":
        raise ValueError("labeled PITNN features must be a CSV")
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("labeled PITNN CSV requires a header")
        required = {"subject_id", "state", *feature_names}
        missing = sorted(required.difference(reader.fieldnames))
        if missing:
            raise ValueError(f"labeled PITNN CSV missing columns: {', '.join(missing)}")
        rows = list(reader)
    if not rows:
        raise ValueError("labeled PITNN CSV contains no rows")
    values: list[list[float]] = []
    states: list[str] = []
    subjects: list[str] = []
    for row in rows:
        try:
            values.append([float(row[name]) for name in feature_names])
        except (TypeError, ValueError) as exc:
            raise ValueError("labeled PITNN feature values must be numeric") from exc
        state = (row["state"] or "").strip().lower()
        subject = (row["subject_id"] or "").strip()
        if not state or not subject:
            raise ValueError("labeled PITNN rows require non-empty state and subject_id")
        states.append(state)
        subjects.append(subject)
    data = np.asarray(values, dtype=float)
    if not np.all(np.isfinite(data)):
        raise ValueError("labeled PITNN feature values must be finite")
    return LabeledFeatureTable(data, tuple(states), tuple(subjects), feature_names)


def ingest_empirical(path: str | Path, sample_rate_hz: float | None = None,
                     picks: list[str] | None = None) -> EmpiricalSignal:
    """Load a local CSV/NPY/FIF/EDF file and extract normalized analytic phase."""
    source_path = Path(path)
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    suffix = source_path.suffix.lower()
    if suffix in {".csv", ".npy"}:
        raw = _read_tabular(source_path)
        if sample_rate_hz is None or sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz is required and positive for CSV/NPY")
        rate = float(sample_rate_hz)
    elif suffix in {".fif", ".edf"}:
        if sample_rate_hz is not None and sample_rate_hz <= 0:
            raise ValueError("sample_rate_hz must be positive when supplied")
        try:
            import mne
            raw_mne = mne.io.read_raw(str(source_path), preload=True, verbose="ERROR")
        except ImportError as exc:
            raise RuntimeError("MNE is required for local FIF/EDF ingestion") from exc
        raw = raw_mne.get_data(picks=picks).T
        rate = float(sample_rate_hz or raw_mne.info["sfreq"])
    else:
        raise ValueError("supported empirical formats are .csv, .npy, .fif and .edf")
    normalized = _normalize(raw)
    analytic = hilbert(normalized, axis=0)
    phase = np.unwrap(np.angle(analytic), axis=0)
    return EmpiricalSignal(normalized, analytic, phase, rate, str(source_path))


def empirical_to_macro_signal(signal: EmpiricalSignal) -> np.ndarray:
    """Validate and adapt an empirical object to `invert_macro_signal` input."""
    macro = np.asarray(signal.macro_signal, dtype=float)
    if macro.ndim != 1 or len(macro) < 4 or not np.all(np.isfinite(macro)):
        raise ValueError("empirical macro signal is invalid")
    return macro


def ingest_conditions(path: str | Path, sample_rate_hz: float,
                       condition_a_label: str = "condition_a",
                       condition_b_label: str = "condition_b") -> tuple[np.ndarray, np.ndarray, str]:
    """Load two local conditions from ``.npz`` or split a tabular recording.

    NPZ files must contain ``state_a`` and ``state_b`` arrays, each shaped
    ``(samples, channels)``.  CSV/NPY input is split along time into equal
    halves, preserving offline reproducibility.
    """
    source = Path(path)
    if not source.is_file() or sample_rate_hz <= 0:
        raise ValueError("existing input path and positive sample rate are required")
    if source.suffix.lower() == ".npz":
        with np.load(source, allow_pickle=False) as bundle:
            if not {"state_a", "state_b"}.issubset(bundle.files):
                raise ValueError("NPZ must contain state_a and state_b arrays")
            first = _normalize(bundle["state_a"])
            second = _normalize(bundle["state_b"])
    else:
        values = _read_tabular(source) if source.suffix.lower() in {".csv", ".npy"} else None
        if values is None:
            raise ValueError("multi-condition input must be CSV, NPY or NPZ")
        midpoint = values.shape[0] // 2
        if midpoint < 8 or values.shape[0] - midpoint < 8:
            raise ValueError("tabular recording must contain at least 16 samples")
        first, second = _normalize(values[:midpoint]), _normalize(values[midpoint:])
    return first, second, "empirical_csv" if source.suffix.lower() == ".csv" else "empirical_local"
