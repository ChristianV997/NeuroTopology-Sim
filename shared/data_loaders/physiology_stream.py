"""Memory-bounded multimodal physiology stream loader for EEG, ECG, and autonomic signals.

Scientific guardrails:
- Physiological coupling is a candidate mechanism, not proof of a mental-state transition.
- Do not describe respiration or parasympathetic activity as equivalent to calmness,
  detachment, equanimity, or liberation.
- Synthetic data is never empirical evidence.
- No label inference: never infer awake, sedated, meditation, jhāna, task, or arousal
  states from filenames or paths; preserve operator labels verbatim.
- Strict memory boundedness: preload-disabled access; never load full high-density recordings.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
from pathlib import Path
from typing import Any, Iterator, Sequence
import numpy as np

from shared.data_loaders.physiology_types import (
    AlignmentMode,
    CardiacFeatures,
    ChannelInfo,
    ClockAlignmentInfo,
    PhysiologyCapabilityState,
    PhysiologyChannelType,
    PhysiologyChunk,
    PhysiologySummary,
    QualityMetrics,
    ResamplingMetadata,
    RespiratoryFeatures,
)

SUPPORTED_PHYSIOLOGY_EXTENSIONS = {
    ".fif": "FIF",
    ".fif.gz": "FIF_GZ",
    ".edf": "EDF",
    ".bdf": "BDF",
    ".vhdr": "BRAINVISION",
}

SYNTHETIC_INDICATORS = (
    "synthetic",
    "simulated",
    "mock",
    "demo_fixture",
    "test_fixture",
    "phantom",
)

BANNED_ASSERTIONS = (
    "calmness",
    "detachment",
    "equanimity",
    "liberation",
    "consciousness proven",
    "soul proven",
    "afterlife proven",
    "jhāna proven",
)


def compute_file_sha256(path: Path) -> str:
    """Compute SHA-256 digest of a file in 1MB chunks."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def classify_channel_type(channel_name: str, mne_type: str | None = None) -> PhysiologyChannelType:
    """Determine physiological modality classification from channel name or MNE type."""
    ch_clean = channel_name.strip().upper()
    if mne_type:
        mne_upper = mne_type.strip().upper()
        if mne_upper == "EEG":
            return PhysiologyChannelType.EEG
        elif mne_upper == "ECG":
            return PhysiologyChannelType.ECG
        elif mne_upper == "RESP":
            return PhysiologyChannelType.RESPIRATION
        elif mne_upper == "EOG":
            return PhysiologyChannelType.EOG
        elif mne_upper == "EMG":
            return PhysiologyChannelType.EMG

    if any(sig in ch_clean for sig in ("ECG", "EKG", "HEART", "CARDIAC")):
        return PhysiologyChannelType.ECG
    elif any(sig in ch_clean for sig in ("RESP", "CHEST", "ABDOMEN", "THORACIC", "BREATH", "AIRFLOW", "PNEUMO")):
        return PhysiologyChannelType.RESPIRATION
    elif any(sig in ch_clean for sig in ("GSR", "EDA", "GALVANIC", "SKIN_COND")):
        return PhysiologyChannelType.GSR_EDA
    elif any(sig in ch_clean for sig in ("PPG", "PLETH", "PULSE")):
        return PhysiologyChannelType.PPG
    elif any(sig in ch_clean for sig in ("EMG", "CHIN", "MASSETER")):
        return PhysiologyChannelType.EMG
    elif any(sig in ch_clean for sig in ("EOG", "VEOG", "HEOG")):
        return PhysiologyChannelType.EOG
    elif any(sig in ch_clean for sig in ("TEMP", "THERM")):
        return PhysiologyChannelType.TEMPERATURE
    elif any(ch_clean.startswith(pfx) for pfx in ("FP", "AF", "F", "FC", "C", "CP", "P", "PO", "O", "T", "TP", "FT", "IZ", "OZ", "PZ", "CZ", "FZ", "FPZ")):
        return PhysiologyChannelType.EEG
    else:
        return PhysiologyChannelType.OTHER_PHYSIOLOGY


def infer_channel_units(ch_type: PhysiologyChannelType) -> str:
    """Infer standardized physical measurement units for channel type."""
    if ch_type == PhysiologyChannelType.EEG:
        return "V"
    elif ch_type == PhysiologyChannelType.ECG:
        return "V"
    elif ch_type == PhysiologyChannelType.RESPIRATION:
        return "arbitrary_expansion"
    elif ch_type == PhysiologyChannelType.GSR_EDA:
        return "uS"
    elif ch_type == PhysiologyChannelType.PPG:
        return "arbitrary_optical"
    elif ch_type == PhysiologyChannelType.TEMPERATURE:
        return "degC"
    return "arbitrary"


def _resample_channel_causal(data: np.ndarray, source_fs: float, target_fs: float) -> tuple[np.ndarray, ResamplingMetadata]:
    """Causal linear interpolation for sample rate conversion preserving historical causality."""
    if abs(source_fs - target_fs) < 1e-4:
        return data.copy(), ResamplingMetadata(
            source_sfreq_hz=source_fs,
            target_sfreq_hz=target_fs,
            ratio=1.0,
            method="identity",
            interpolated=False,
        )

    n_source = len(data)
    duration_s = n_source / source_fs
    n_target = int(math.floor(duration_s * target_fs))
    if n_target <= 0 or n_source <= 0:
        return np.zeros(0, dtype=data.dtype), ResamplingMetadata(
            source_sfreq_hz=source_fs,
            target_sfreq_hz=target_fs,
            ratio=target_fs / source_fs if source_fs > 0 else 1.0,
            method="causal_linear_interpolation",
            interpolated=True,
        )

    target_times = np.arange(n_target) / target_fs
    source_positions = target_times * source_fs

    idx_floor = np.floor(source_positions).astype(int)
    idx_floor = np.clip(idx_floor, 0, n_source - 1)
    idx_ceil = np.clip(idx_floor + 1, 0, n_source - 1)
    weights = source_positions - idx_floor

    resampled = (1.0 - weights) * data[idx_floor] + weights * data[idx_ceil]
    meta = ResamplingMetadata(
        source_sfreq_hz=source_fs,
        target_sfreq_hz=target_fs,
        ratio=float(target_fs / source_fs),
        method="causal_linear_interpolation",
        interpolated=True,
    )
    return resampled, meta


def compute_respiratory_features(resp_signal: np.ndarray, sfreq: float) -> RespiratoryFeatures:
    """Compute bounded, feature-ready respiratory metrics without clinical claims."""
    if len(resp_signal) < int(sfreq * 2.0) or sfreq <= 0:
        return RespiratoryFeatures(
            respiratory_rate_bpm=None,
            inspiratory_duration_s=None,
            expiratory_duration_s=None,
            ie_ratio=None,
            respiratory_phase_rad=None,
        )

    clean_resp = np.asarray(resp_signal, dtype=float)
    if not np.all(np.isfinite(clean_resp)):
        return RespiratoryFeatures(
            respiratory_rate_bpm=None,
            inspiratory_duration_s=None,
            expiratory_duration_s=None,
            ie_ratio=None,
            respiratory_phase_rad=None,
        )

    # Detrend
    centered = clean_resp - np.mean(clean_resp)
    std = np.std(centered)
    if std < 1e-9:
        return RespiratoryFeatures(
            respiratory_rate_bpm=None,
            inspiratory_duration_s=None,
            expiratory_duration_s=None,
            ie_ratio=None,
            respiratory_phase_rad=None,
        )

    # Detect positive-going zero crossings
    signs = np.sign(centered)
    crossings = np.where((signs[:-1] <= 0) & (signs[1:] > 0))[0]

    if len(crossings) < 2:
        return RespiratoryFeatures(
            respiratory_rate_bpm=None,
            inspiratory_duration_s=None,
            expiratory_duration_s=None,
            ie_ratio=None,
            respiratory_phase_rad=None,
        )

    cycle_lengths = np.diff(crossings) / sfreq
    avg_cycle_s = float(np.mean(cycle_lengths))
    resp_rate_bpm = float(60.0 / avg_cycle_s) if avg_cycle_s > 0 else None

    # Estimate I:E timing across breath cycles
    insp_times: list[float] = []
    exp_times: list[float] = []
    for i in range(len(crossings) - 1):
        c_start = crossings[i]
        c_end = crossings[i + 1]
        cycle = centered[c_start:c_end]
        if len(cycle) < 3:
            continue
        peak_idx = int(np.argmax(cycle))
        insp_s = peak_idx / sfreq
        exp_s = (len(cycle) - peak_idx) / sfreq
        if insp_s > 0 and exp_s > 0:
            insp_times.append(insp_s)
            exp_times.append(exp_s)

    avg_insp_s = float(np.mean(insp_times)) if insp_times else None
    avg_exp_s = float(np.mean(exp_times)) if exp_times else None
    ie_ratio = (avg_insp_s / avg_exp_s) if (avg_insp_s and avg_exp_s and avg_exp_s > 0) else None

    # Instantaneous phase at end of window
    last_cross = crossings[-1]
    samples_since = len(centered) - 1 - last_cross
    phase_rad = float((2.0 * np.pi * (samples_since / (avg_cycle_s * sfreq))) % (2.0 * np.pi) - np.pi) if avg_cycle_s > 0 else None

    return RespiratoryFeatures(
        respiratory_rate_bpm=resp_rate_bpm,
        inspiratory_duration_s=avg_insp_s,
        expiratory_duration_s=avg_exp_s,
        ie_ratio=ie_ratio,
        respiratory_phase_rad=phase_rad,
    )


def compute_cardiac_features(ecg_signal: np.ndarray, sfreq: float) -> CardiacFeatures:
    """Compute bounded, feature-ready heart rate and HRV metrics without clinical claims."""
    if len(ecg_signal) < int(sfreq * 1.5) or sfreq <= 0:
        return CardiacFeatures(
            heart_rate_bpm=None,
            rr_intervals_ms=None,
            rmssd_ms=None,
            sdnn_ms=None,
        )

    clean_ecg = np.asarray(ecg_signal, dtype=float)
    if not np.all(np.isfinite(clean_ecg)):
        return CardiacFeatures(
            heart_rate_bpm=None,
            rr_intervals_ms=None,
            rmssd_ms=None,
            sdnn_ms=None,
        )

    centered = clean_ecg - np.mean(clean_ecg)
    std = np.std(centered)
    if std < 1e-9:
        return CardiacFeatures(
            heart_rate_bpm=None,
            rr_intervals_ms=None,
            rmssd_ms=None,
            sdnn_ms=None,
        )

    # Detect R-peaks with refractory distance (min 300 ms => max 200 BPM)
    min_dist = int(0.3 * sfreq)
    thresh = float(np.mean(centered) + 1.5 * std)

    peaks: list[int] = []
    last_peak = -min_dist
    for idx in range(1, len(centered) - 1):
        if centered[idx] > thresh and centered[idx] > centered[idx - 1] and centered[idx] > centered[idx + 1]:
            if (idx - last_peak) >= min_dist:
                peaks.append(idx)
                last_peak = idx

    if len(peaks) < 2:
        return CardiacFeatures(
            heart_rate_bpm=None,
            rr_intervals_ms=None,
            rmssd_ms=None,
            sdnn_ms=None,
        )

    rr_ms = [(peaks[i + 1] - peaks[i]) / sfreq * 1000.0 for i in range(len(peaks) - 1)]
    mean_rr = float(np.mean(rr_ms))
    hr_bpm = float(60000.0 / mean_rr) if mean_rr > 0 else None
    sdnn = float(np.std(rr_ms))

    if len(rr_ms) >= 2:
        successive_diffs = np.diff(rr_ms)
        rmssd = float(np.sqrt(np.mean(np.square(successive_diffs))))
    else:
        rmssd = None

    return CardiacFeatures(
        heart_rate_bpm=hr_bpm,
        rr_intervals_ms=rr_ms,
        rmssd_ms=rmssd,
        sdnn_ms=sdnn,
    )


class PhysiologyStreamReader:
    """Offline-first, preload-disabled multimodal physiology stream reader."""

    def __init__(
        self,
        source_path: str | Path,
        *,
        common_sfreq_hz: float | None = None,
        alignment_mode: AlignmentMode = AlignmentMode.CAUSAL,
        supplied_labels: dict[str, str] | None = None,
        provenance_hint: str = "auto",
        mne_override: Any | None = None,
    ) -> None:
        self.source_path = Path(source_path)
        self.common_sfreq_hz = common_sfreq_hz
        self.alignment_mode = alignment_mode
        self.supplied_labels = dict(supplied_labels) if supplied_labels is not None else {}
        self.provenance_hint = provenance_hint
        self.mne_override = mne_override

        self._raw: Any = None
        self._is_synthetic = False
        self._source_checksum = ""
        self._capability_state = PhysiologyCapabilityState.AVAILABLE.value
        self._missing_dependencies: list[str] = []
        self._channel_infos: list[ChannelInfo] = []
        self._init_reader()

    @property
    def capability_state(self) -> str:
        return self._capability_state

    @property
    def is_synthetic(self) -> bool:
        return self._is_synthetic

    @property
    def channel_infos(self) -> list[ChannelInfo]:
        return list(self._channel_infos)

    def _init_reader(self) -> None:
        if not self.source_path.exists():
            self._capability_state = PhysiologyCapabilityState.UNAVAILABLE_FILE.value
            return

        if self.source_path.is_file():
            self._source_checksum = compute_file_sha256(self.source_path)

        # Detect synthetic status
        path_lower = str(self.source_path).lower()
        has_synth_marker = any(k in path_lower for k in SYNTHETIC_INDICATORS)
        if self.provenance_hint == "synthetic":
            self._is_synthetic = True
        elif self.provenance_hint == "empirical":
            self._is_synthetic = has_synth_marker
        else:
            self._is_synthetic = has_synth_marker

        # Extension check
        ext = self.source_path.suffix.lower()
        if str(self.source_path.name).lower().endswith(".fif.gz"):
            ext = ".fif.gz"

        if ext not in SUPPORTED_PHYSIOLOGY_EXTENSIONS:
            self._capability_state = PhysiologyCapabilityState.UNSUPPORTED_FORMAT.value
            return

        # Resolve MNE
        mne = self.mne_override
        if mne is None:
            if importlib.util.find_spec("mne") is not None:
                import mne as mne_mod
                mne = mne_mod

        if mne is None:
            self._capability_state = PhysiologyCapabilityState.MISSING_OPTIONAL_DEPENDENCY.value
            self._missing_dependencies.append("mne")
            return

        # Open raw with preload=False unconditionally
        try:
            if ext in (".fif", ".fif.gz"):
                self._raw = mne.io.read_raw_fif(str(self.source_path), preload=False, verbose="ERROR")
            elif ext == ".edf":
                self._raw = mne.io.read_raw_edf(str(self.source_path), preload=False, verbose="ERROR")
            elif ext == ".bdf":
                self._raw = mne.io.read_raw_bdf(str(self.source_path), preload=False, verbose="ERROR")
            elif ext == ".vhdr":
                self._raw = mne.io.read_raw_brainvision(str(self.source_path), preload=False, verbose="ERROR")
        except Exception as exc:
            self._capability_state = PhysiologyCapabilityState.MALFORMED_METADATA.value
            return

        if getattr(self._raw, "preload", False) is True:
            raise RuntimeError("Memory invariant violated: preload=True is forbidden in streaming loader.")

        # Classify channels
        ch_names = list(self._raw.ch_names)
        sfreq = float(self._raw.info.get("sfreq", 0.0))
        target_sfreq = self.common_sfreq_hz if self.common_sfreq_hz is not None else sfreq
        bads = set(self._raw.info.get("bads", []))

        # Check montage
        montage = getattr(self._raw, "get_montage", lambda: None)()
        pos_dict = montage.get_positions().get("ch_pos", {}) if montage else {}

        self._channel_infos = []
        for name in ch_names:
            c_type = classify_channel_type(name)
            units = infer_channel_units(c_type)
            coords = None
            if name in pos_dict:
                p = pos_dict[name]
                if p is not None and not np.isnan(p).any():
                    coords = (float(p[0]), float(p[1]), float(p[2]))

            self._channel_infos.append(
                ChannelInfo(
                    name=name,
                    channel_type=c_type.value,
                    original_sfreq_hz=sfreq,
                    aligned_sfreq_hz=target_sfreq,
                    units=units,
                    is_bad=(name in bads),
                    montage_coordinates=coords,
                )
            )

    def iter_chunks(
        self,
        chunk_duration_s: float = 1.0,
        max_chunks: int | None = None,
    ) -> Iterator[PhysiologyChunk]:
        """Yield memory-bounded, clock-aligned physiological signal chunks."""
        if self._capability_state != PhysiologyCapabilityState.AVAILABLE.value or self._raw is None:
            return

        source_sfreq = float(self._raw.info["sfreq"])
        target_sfreq = self.common_sfreq_hz if self.common_sfreq_hz is not None else source_sfreq
        chunk_samples_source = max(1, int(round(chunk_duration_s * source_sfreq)))
        total_times = int(self._raw.n_times)

        # Build alignment info
        resampling_dict: dict[str, ResamplingMetadata] = {}
        missing_channels: list[str] = []
        types_present = {c.channel_type for c in self._channel_infos}
        for expected in (PhysiologyChannelType.EEG.value, PhysiologyChannelType.ECG.value, PhysiologyChannelType.RESPIRATION.value):
            if expected not in types_present:
                missing_channels.append(expected)

        for c in self._channel_infos:
            ratio = float(target_sfreq / source_sfreq)
            is_interpolated = abs(source_sfreq - target_sfreq) > 1e-4
            resampling_dict[c.name] = ResamplingMetadata(
                source_sfreq_hz=source_sfreq,
                target_sfreq_hz=target_sfreq,
                ratio=ratio,
                method="causal_linear_interpolation" if self.alignment_mode == AlignmentMode.CAUSAL else "symmetric_interpolation",
                interpolated=is_interpolated,
            )

        clock_info = ClockAlignmentInfo(
            common_clock_sfreq_hz=target_sfreq,
            alignment_mode=self.alignment_mode.value,
            clock_drift_detected=False,
            clock_drift_warning=None,
            resampling=resampling_dict,
            missing_channels=missing_channels,
        )

        chunk_idx = 0
        for start_samp in range(0, total_times, chunk_samples_source):
            if max_chunks is not None and chunk_idx >= max_chunks:
                break

            stop_samp = min(total_times, start_samp + chunk_samples_source)
            # Memory bounded fetch
            chunk_data_raw = np.asarray(
                self._raw.get_data(start=start_samp, stop=stop_samp),
                dtype=float,
            )
            is_finite = bool(np.all(np.isfinite(chunk_data_raw)))

            start_time = start_samp / source_sfreq
            end_time = stop_samp / source_sfreq

            # Resample each channel if needed
            if abs(source_sfreq - target_sfreq) > 1e-4:
                aligned_channels: list[np.ndarray] = []
                for ch_idx in range(len(self._channel_infos)):
                    res_ch, _ = _resample_channel_causal(
                        chunk_data_raw[ch_idx],
                        source_sfreq,
                        target_sfreq,
                    )
                    aligned_channels.append(res_ch)
                aligned_data = np.stack(aligned_channels, axis=0) if aligned_channels else np.zeros((0, 0))
            else:
                aligned_data = chunk_data_raw

            n_aligned_samples = aligned_data.shape[1] if aligned_data.ndim == 2 else 0
            timestamps = [start_time + i / target_sfreq for i in range(n_aligned_samples)]

            yield PhysiologyChunk(
                chunk_index=chunk_idx,
                start_sample=int(round(start_time * target_sfreq)),
                end_sample=int(round(start_time * target_sfreq)) + n_aligned_samples,
                start_time_s=start_time,
                end_time_s=end_time,
                timestamps=timestamps,
                channel_names=[c.name for c in self._channel_infos],
                channel_types=[c.channel_type for c in self._channel_infos],
                units={c.name: c.units for c in self._channel_infos},
                sample_rate_hz=target_sfreq,
                data=aligned_data,
                finite_status=is_finite,
                bad_channel_flags={c.name: c.is_bad for c in self._channel_infos},
                source_checksum=self._source_checksum,
                provenance_origin=str(self.source_path.resolve()),
                is_synthetic=self._is_synthetic,
                supplied_labels=self.supplied_labels,
                clock_alignment=clock_info,
            )
            chunk_idx += 1

    def compute_summary(self, max_samples: int = 4096) -> PhysiologySummary:
        """Extract bounded physiological features across modalities."""
        if self._capability_state != PhysiologyCapabilityState.AVAILABLE.value or self._raw is None:
            return PhysiologySummary(
                schema_version="v1.0.0",
                source_file=str(self.source_path),
                source_checksum=self._source_checksum,
                is_synthetic=self._is_synthetic,
                capability_state=self._capability_state,
                supplied_labels=self.supplied_labels,
                warnings=["Reader not available for feature summary."],
            )

        sfreq = float(self._raw.info["sfreq"])
        n_times = int(self._raw.n_times)
        inspect_samples = min(n_times, max_samples)
        duration_s = n_times / sfreq if sfreq > 0 else None

        # Sliced read
        raw_chunk = np.asarray(self._raw.get_data(start=0, stop=inspect_samples), dtype=float)
        all_finite = bool(np.all(np.isfinite(raw_chunk)))

        resp_features: RespiratoryFeatures | None = None
        cardiac_features: CardiacFeatures | None = None

        for idx, ch in enumerate(self._channel_infos):
            if ch.channel_type == PhysiologyChannelType.RESPIRATION.value and resp_features is None:
                resp_features = compute_respiratory_features(raw_chunk[idx], sfreq)
            elif ch.channel_type == PhysiologyChannelType.ECG.value and cardiac_features is None:
                cardiac_features = compute_cardiac_features(raw_chunk[idx], sfreq)

        expected_types = {PhysiologyChannelType.EEG.value, PhysiologyChannelType.ECG.value, PhysiologyChannelType.RESPIRATION.value}
        present_types = {c.channel_type for c in self._channel_infos}
        missing_count = len(expected_types - present_types)
        missingness_ratio = float(missing_count / len(expected_types))

        quality = QualityMetrics(
            signal_quality_index=1.0 if all_finite else 0.0,
            missingness_ratio=missingness_ratio,
            synchronization_quality_index=1.0,
            finite_ratio=1.0 if all_finite else 0.0,
        )

        resampling_dict = {
            c.name: ResamplingMetadata(
                source_sfreq_hz=c.original_sfreq_hz,
                target_sfreq_hz=c.aligned_sfreq_hz,
                ratio=1.0,
                method="identity",
                interpolated=False,
            )
            for c in self._channel_infos
        }

        clock_info = ClockAlignmentInfo(
            common_clock_sfreq_hz=sfreq,
            alignment_mode=self.alignment_mode.value,
            clock_drift_detected=False,
            clock_drift_warning=None,
            resampling=resampling_dict,
            missing_channels=list(expected_types - present_types),
        )

        summary = PhysiologySummary(
            schema_version="v1.0.0",
            source_file=str(self.source_path),
            source_checksum=self._source_checksum,
            is_synthetic=self._is_synthetic,
            capability_state=self._capability_state,
            supplied_labels=self.supplied_labels,
            clock_alignment=clock_info,
            channels=self._channel_infos,
            respiration=resp_features,
            cardiac=cardiac_features,
            quality=quality,
            total_samples=n_times,
            duration_s=duration_s,
            warnings=[],
        )
        # Compute checksum
        summary.to_json()
        return summary
