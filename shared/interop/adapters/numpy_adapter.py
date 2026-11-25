import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from shared.interop.adapters.base import BaseSignalAdapter
from shared.interop.contracts import AdapterCapability, AdapterStatus, SignalChunk

logger = logging.getLogger(__name__)

class NumpyAdapter(BaseSignalAdapter):
    """
    Adapter for raw NumPy (.npy, .npz) and CSV files.
    """

    def __init__(self, source_path: Path | str, **kwargs: Any) -> None:
        super().__init__(source_path, **kwargs)
        self._data = None
        self._np = None
        self._sha256 = kwargs.get("source_sha256")
        self._source_id = kwargs.get("source_id", "numpy-source")
        self._recording_id = kwargs.get("recording_id", "numpy-rec")
        self.sample_rate_hz = kwargs.get("sample_rate_hz", 1000.0)

    @classmethod
    def get_capability(cls) -> AdapterCapability:
        try:
            import numpy
            return AdapterCapability(
                adapter_name="numpy",
                supported_formats=[".npy", ".npz", ".csv"],
                dependency="numpy",
                availability=True,
                streaming_support=True,
                montage_support=False,
                write_support=True,
                network_requirement="none",
                status=AdapterStatus.INTEGRATED,
            )
        except ImportError:
            return AdapterCapability(
                adapter_name="numpy",
                supported_formats=[".npy", ".npz", ".csv"],
                dependency="numpy",
                availability=False,
                streaming_support=False,
                montage_support=False,
                write_support=False,
                network_requirement="none",
                status=AdapterStatus.UNAVAILABLE,
            )

    def open(self) -> None:
        if self.is_open:
            return
        try:
            import numpy as np
            self._np = np
        except ImportError as exc:
            raise RuntimeError("NumPy is not installed") from exc

        path = str(self.source_path)
        if path.endswith(".csv"):
            self._data = self._np.genfromtxt(path, delimiter=",")
        elif path.endswith(".npz"):
            self._data = self._np.load(path)["arr_0"]
        else:
            self._data = self._np.load(path, mmap_mode="r")
            
        # Ensure shape is (channels, samples)
        if self._data.ndim == 1:
            self._data = self._data.reshape(1, -1)
        elif self._data.ndim != 2:
            raise ValueError("Data must be 2D (channels, samples)")
            
        self.is_open = True

    def close(self) -> None:
        if self._data is not None:
            if hasattr(self._data, "base") and self._data.base is not None and hasattr(self._data.base, "close"):
                # if it's a view on a memmap
                self._data.base.close()
            elif hasattr(self._data, "_mmap") and hasattr(self._data._mmap, "close"):
                self._data._mmap.close()
            self._data = None
        self.is_open = False

    def iter_chunks(self, chunk_size: int = 1024) -> Iterator[SignalChunk]:
        if not self.is_open or self._data is None:
            raise RuntimeError("Adapter is not open")
        
        n_channels, n_times = self._data.shape
        ch_names = [f"CH{i}" for i in range(n_channels)]
        
        chunk_idx = 0
        for start in range(0, n_times, chunk_size):
            end = min(start + chunk_size, n_times)
            data_chunk = self._data[:, start:end]
            times = self._np.arange(start, end) / self.sample_rate_hz
            
            yield SignalChunk(
                data=data_chunk,
                timestamps=times,
                sample_rate_hz=self.sample_rate_hz,
                channel_names=ch_names,
                units="V",
                source_id=self._source_id,
                recording_id=self._recording_id,
                chunk_index=chunk_idx,
                start_sample=start,
                source_sha256=self._sha256,
            )
            chunk_idx += 1
