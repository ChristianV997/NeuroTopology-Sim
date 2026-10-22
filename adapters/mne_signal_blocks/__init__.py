"""In-memory MNE → canonical signal-block boundary.

Engineering conformance only. Does not validate scientific truth, download
data, or mutate caller arrays/metadata. Optional MNE import is probed at
call time; fixtures run without MNE.
"""

from __future__ import annotations

from adapters.mne_signal_blocks.converter import (
    convert_from_mne_object,
    convert_in_memory_block,
)
from adapters.mne_signal_blocks.schema import (
    SCHEMA_VERSION,
    BlockStatus,
    CanonicalInMemorySignalBlock,
    ConversionResult,
)
from adapters.mne_signal_blocks.validate import validate_block

__all__ = [
    "SCHEMA_VERSION",
    "BlockStatus",
    "CanonicalInMemorySignalBlock",
    "ConversionResult",
    "convert_from_mne_object",
    "convert_in_memory_block",
    "validate_block",
]

# fixtures submodule is importable as adapters.mne_signal_blocks.fixtures
# without eagerly loading it here.
