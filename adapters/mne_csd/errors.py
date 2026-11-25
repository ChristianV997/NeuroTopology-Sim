"""Fail-closed errors for the MNE CSD adapter."""
from __future__ import annotations


class CSDAdapterError(ValueError):
    """Base error for invalid CSD adapter inputs or unavailable backend."""


class MNEUnavailableError(CSDAdapterError):
    """Raised when MNE is required but not importable."""


class MissingCoordinatesError(CSDAdapterError):
    """Raised when usable 3D montage coordinates are missing."""


class InvalidChannelSelectionError(CSDAdapterError):
    """Raised when requested channels are absent, non-EEG, or otherwise unusable."""


class ReferenceMutationError(CSDAdapterError):
    """Raised when a caller asks the adapter to silently change the EEG reference."""
