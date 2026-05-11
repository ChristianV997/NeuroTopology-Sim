"""DS005620 EEG reader adapter contracts."""
from .eeg_readers import (
    EEGReaderCapability,
    EEGFileReadability,
    EEGChannelInventory,
    inspect_eeg_file,
    inspect_eeg_files,
    build_reader_capability_report,
    build_channel_inventory,
    write_eeg_reader_outputs,
)

__all__ = [
    "EEGReaderCapability",
    "EEGFileReadability",
    "EEGChannelInventory",
    "inspect_eeg_file",
    "inspect_eeg_files",
    "build_reader_capability_report",
    "build_channel_inventory",
    "write_eeg_reader_outputs",
]
