import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from shared.interop.adapters.base import BaseSignalAdapter
from shared.interop.contracts import AdapterCapability, AdapterStatus, SignalChunk

logger = logging.getLogger(__name__)

class BrainVisionAdapter(BaseSignalAdapter):
    """
    Adapter for BrainVision files (.vhdr) using lazy-loaded MNE.
    """

    def __init__(self, source_path: Path | str, **kwargs: Any) -> None:
        super().__init__(source_path, **kwargs)
        self._raw = None
        self._mne = None
        self._sha256 = kwargs.get("source_sha256")
        self._source_id = kwargs.get("source_id", "bv-source")
        self._recording_id = kwargs.get("recording_id", "bv-rec")

    @classmethod
    def get_capability(cls) -> AdapterCapability:
        try:
            import mne
            return AdapterCapability(
                adapter_name="brainvision",
                supported_formats=[".vhdr", ".eeg", ".vmrk"],
                dependency="mne",
                availability=True,
                streaming_support=True,
                montage_support=True,
                write_support=False,
                network_requirement="none",
                status=AdapterStatus.INTEGRATED,
            )
        except ImportError:
            return AdapterCapability(
                adapter_name="brainvision",
                supported_formats=[".vhdr", ".eeg", ".vmrk"],
                dependency="mne",
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
            import mne
            self._mne = mne
        except ImportError as exc:
            raise RuntimeError("MNE is not installed") from exc

        # preload=False keeps it memory bounded
        self._raw = self._mne.io.read_raw_brainvision(self.source_path, preload=False, verbose=False)
        self.is_open = True

    def close(self) -> None:
        if self._raw is not None:
            self._raw.close()
            self._raw = None
        self.is_open = False

    def iter_chunks(self, chunk_size: int = 1024) -> Iterator[SignalChunk]:
        if not self.is_open or self._raw is None:
            raise RuntimeError("Adapter is not open")
        
        n_times = self._raw.n_times
        sfreq = self._raw.info["sfreq"]
        ch_names = self._raw.ch_names
        
        chunk_idx = 0
        for start in range(0, n_times, chunk_size):
            end = min(start + chunk_size, n_times)
            data, times = self._raw[:, start:end]
            
            yield SignalChunk(
                data=data,
                timestamps=times,
                sample_rate_hz=sfreq,
                channel_names=ch_names,
                units="V",
                source_id=self._source_id,
                recording_id=self._recording_id,
                chunk_index=chunk_idx,
                start_sample=start,
                source_sha256=self._sha256,
            )
            chunk_idx += 1
