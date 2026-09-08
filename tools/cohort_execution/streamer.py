"""Bounded streaming recording reader across electrophysiology and array formats.

Ensures recordings are streamed window-by-window without materializing full cohorts
or full recording matrices into memory.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Iterator
import numpy as np


@dataclass(frozen=True)
class StreamMetadata:
    file_path: str
    format: str
    checksum: str
    sample_count: int
    channel_count: int
    sampling_rate_hz: float
    montage_coordinates: np.ndarray | None
    is_synthetic: bool


def compute_file_sha256(path: Path | str, chunk_size: int = 1024 * 1024) -> str:
    """Computes SHA-256 hash of a file in streaming byte blocks."""
    p = Path(path)
    if not p.is_file():
        return "file_not_found"
    h = hashlib.sha256()
    with p.open("rb") as f:
        while block := f.read(chunk_size):
            h.update(block)
    return h.hexdigest()


class RecordingStreamer:
    """Bounded window streamer for an individual electrophysiology recording."""

    def __init__(
        self,
        file_path: str | Path,
        *,
        format_hint: str | None = None,
        default_sfreq: float = 1000.0,
        is_synthetic: bool = False,
    ) -> None:
        self.path = Path(file_path)
        self.format_hint = (format_hint or self.path.suffix.lstrip(".").lower())
        self.default_sfreq = default_sfreq
        self.is_synthetic = is_synthetic
        self._metadata: StreamMetadata | None = None

    def get_metadata(self) -> StreamMetadata:
        """Inspects file headers and metadata without full data materialization."""
        if self._metadata is not None:
            return self._metadata

        if not self.path.is_file():
            raise FileNotFoundError(f"Recording file not found on disk: {self.path}")

        checksum = compute_file_sha256(self.path)
        ext = self.path.suffix.lower()

        if ext == ".npy":
            arr = np.load(self.path, mmap_mode="r")
            if arr.ndim != 2:
                raise ValueError(f".npy recording must be 2D (channels, samples), got shape {arr.shape}")
            n_ch, n_samples = arr.shape
            self._metadata = StreamMetadata(
                file_path=str(self.path.resolve()),
                format="npy",
                checksum=checksum,
                sample_count=int(n_samples),
                channel_count=int(n_ch),
                sampling_rate_hz=self.default_sfreq,
                montage_coordinates=None,
                is_synthetic=self.is_synthetic,
            )
            return self._metadata

        if ext == ".csv":
            with self.path.open("r", encoding="utf-8") as f:
                reader = csv.reader(f)
                first_row = next(reader, None)
                if first_row is None:
                    raise ValueError("CSV recording is empty")
                try:
                    [float(val) for val in first_row]
                    row_offset = 0
                except ValueError:
                    row_offset = 1
                n_cols = len(first_row)
                line_count = 1 + sum(1 for _ in f) - row_offset

            self._metadata = StreamMetadata(
                file_path=str(self.path.resolve()),
                format="csv",
                checksum=checksum,
                sample_count=int(line_count),
                channel_count=int(n_cols),
                sampling_rate_hz=self.default_sfreq,
                montage_coordinates=None,
                is_synthetic=self.is_synthetic,
            )
            return self._metadata

        if ext in (".vhdr", ".edf", ".fif", ".bdf"):
            from shared.data_loaders.eeg_bids_loader import read_local_raw

            raw_stream = read_local_raw(self.path, preload=False)
            raw = raw_stream.raw
            n_ch = len(raw.ch_names)
            n_samples = int(raw.n_times)
            sfreq = float(raw_stream.metadata.sfreq_hz)
            coords = raw_stream.metadata.montage_coordinates

            self._metadata = StreamMetadata(
                file_path=str(self.path.resolve()),
                format=ext.lstrip("."),
                checksum=checksum,
                sample_count=n_samples,
                channel_count=n_ch,
                sampling_rate_hz=sfreq,
                montage_coordinates=coords,
                is_synthetic=self.is_synthetic,
            )
            return self._metadata

        raise ValueError(f"Unsupported recording format: {ext}")

    def iter_windows(
        self,
        *,
        window_samples: int = 1024,
        window_duration_s: float | None = None,
        step_samples: int | None = None,
        step_duration_s: float | None = None,
        channel_limit: int | None = None,
        sample_limit: int | None = None,
        max_points_per_window: int | None = None,
        max_windows: int | None = None,
    ) -> Iterator[tuple[int, np.ndarray, bool]]:
        """Yields bounded windows `(window_index, window_data, is_finite)`.

        Each window is shape `(channels, window_samples)` with channel_limit applied.
        Memory is strictly bounded to the active window.
        """
        meta = self.get_metadata()

        if window_duration_s is not None:
            effective_window_samples = int(round(window_duration_s * meta.sampling_rate_hz))
        else:
            effective_window_samples = window_samples

        if max_points_per_window is not None:
            effective_window_samples = min(effective_window_samples, max_points_per_window)

        if effective_window_samples < 8:
            raise ValueError(f"effective window samples must be >= 8, got {effective_window_samples}")

        if step_duration_s is not None:
            effective_step = int(round(step_duration_s * meta.sampling_rate_hz))
        elif step_samples is not None:
            effective_step = step_samples
        else:
            effective_step = effective_window_samples

        if effective_step < 1:
            raise ValueError(f"effective step must be >= 1, got {effective_step}")

        ext = self.path.suffix.lower()
        windows_yielded = 0
        total_samples_streamed = 0

        effective_sample_count = meta.sample_count
        if sample_limit is not None:
            effective_sample_count = min(effective_sample_count, sample_limit)

        if ext == ".npy":
            arr = np.load(self.path, mmap_mode="r")
            for start in range(0, effective_sample_count - effective_window_samples + 1, effective_step):
                if max_windows is not None and windows_yielded >= max_windows:
                    break
                chunk = np.asarray(arr[:, start : start + effective_window_samples], dtype=np.float64)
                if channel_limit is not None and channel_limit < chunk.shape[0]:
                    chunk = chunk[:channel_limit, :]
                is_finite = bool(np.all(np.isfinite(chunk)))
                yield windows_yielded, chunk, is_finite
                windows_yielded += 1
                total_samples_streamed += effective_window_samples
            return

        if ext == ".csv":
            with self.path.open("r", encoding="utf-8") as f:
                reader = csv.reader(f)
                first_row = next(reader, None)
                if first_row is None:
                    return
                try:
                    first_vals = [float(v) for v in first_row]
                    has_header = False
                except ValueError:
                    has_header = True

            with self.path.open("r", encoding="utf-8") as f:
                reader = csv.reader(f)
                if has_header:
                    next(reader, None)

                buffer: list[list[float]] = []
                samples_read = 0
                for row in reader:
                    if not row:
                        continue
                    if sample_limit is not None and samples_read >= sample_limit:
                        break
                    try:
                        vals = [float(v) for v in row]
                    except ValueError:
                        vals = [np.nan] * len(row)
                    buffer.append(vals)
                    samples_read += 1

                    if len(buffer) == effective_window_samples:
                        if max_windows is not None and windows_yielded >= max_windows:
                            break
                        chunk = np.asarray(buffer, dtype=np.float64).T
                        if channel_limit is not None and channel_limit < chunk.shape[0]:
                            chunk = chunk[:channel_limit, :]
                        is_finite = bool(np.all(np.isfinite(chunk)))
                        yield windows_yielded, chunk, is_finite
                        windows_yielded += 1
                        buffer = buffer[effective_step:]
            return

        if ext in (".vhdr", ".edf", ".fif", ".bdf"):
            from shared.data_loaders.eeg_bids_loader import read_local_raw

            stream = read_local_raw(self.path, preload=False)
            raw = stream.raw
            total_samples = min(int(raw.n_times), effective_sample_count)

            for start in range(0, total_samples - effective_window_samples + 1, effective_step):
                if max_windows is not None and windows_yielded >= max_windows:
                    break
                stop = start + effective_window_samples
                data = raw.get_data(start=start, stop=stop)
                chunk = np.asarray(data, dtype=np.float64)
                if channel_limit is not None and channel_limit < chunk.shape[0]:
                    chunk = chunk[:channel_limit, :]
                is_finite = bool(np.all(np.isfinite(chunk)))
                yield windows_yielded, chunk, is_finite
                windows_yielded += 1
            return
