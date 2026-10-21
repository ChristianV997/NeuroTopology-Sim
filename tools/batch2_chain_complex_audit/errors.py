"""Validation errors for the independent chain-complex oracle."""

from __future__ import annotations


class ChainComplexError(ValueError):
    """Base error for malformed finite chain-complex inputs."""


class EndpointError(ChainComplexError):
    """Negative, out-of-range, or self-loop edge endpoints."""


class DuplicateError(ChainComplexError):
    """Duplicate edges, faces, or cells under canonical keying."""


class FaceSpecError(ChainComplexError):
    """Invalid face: repeated vertices, missing edges, bad orientation signs."""


class CellSpecError(ChainComplexError):
    """Invalid 3-cell: duplicate faces, unsigned-only checks that fail signed cancel."""


class OrientationError(ChainComplexError):
    """Orientation sign not in {-1, +1}."""
