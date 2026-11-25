"""Fail-closed errors for the surrogate audit surface."""
from __future__ import annotations


class SurrogateAuditError(ValueError):
    """Invalid input or unsupported configuration for synthetic surrogate audit."""
