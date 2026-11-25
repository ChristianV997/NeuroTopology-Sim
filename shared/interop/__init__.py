"""Typed, dependency-light interoperability contracts for signal adapters."""

from .contracts import (
    AdapterCapability,
    AdapterStatus,
    InteropValidationError,
    QualityReport,
    QualityStatus,
    RecordingManifest,
    SignalChunk,
    canonical_json,
    normalize_relative_path,
    sha256_file,
    sha256_text,
    stable_hash,
    stable_id,
)
from .adapter_registry import AdapterRegistry, discover_adapters

__all__ = [
    "AdapterCapability",
    "AdapterRegistry",
    "AdapterStatus",
    "InteropValidationError",
    "QualityReport",
    "QualityStatus",
    "RecordingManifest",
    "SignalChunk",
    "canonical_json",
    "discover_adapters",
    "normalize_relative_path",
    "sha256_file",
    "sha256_text",
    "stable_hash",
    "stable_id",
]
