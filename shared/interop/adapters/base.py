import abc
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from shared.interop.contracts import AdapterCapability, SignalChunk

class BaseSignalAdapter(abc.ABC):
    """
    Base class for native signal interoperability adapters.
    Enforces offline-first lazy loading and bounded chunk reads.
    """

    def __init__(self, source_path: Path | str, **kwargs: Any) -> None:
        self.source_path = Path(source_path)
        self.is_open = False

    @abc.abstractmethod
    def open(self) -> None:
        """Open the resource. Must be explicitly called or used via context manager."""
        pass

    @abc.abstractmethod
    def close(self) -> None:
        """Close the resource and clean up."""
        pass

    def __enter__(self) -> "BaseSignalAdapter":
        self.open()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    @abc.abstractmethod
    def iter_chunks(self, chunk_size: int = 1024) -> Iterator[SignalChunk]:
        """Iterate over the signal data in bounded chunks."""
        pass

    @classmethod
    @abc.abstractmethod
    def get_capability(cls) -> AdapterCapability:
        """
        Probe ecosystem capability without hard crashing if dependencies are missing.
        Returns a structured AdapterCapability.
        """
        pass
