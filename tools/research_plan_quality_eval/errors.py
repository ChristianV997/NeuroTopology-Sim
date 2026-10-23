"""Exceptions raised by the research-plan evaluation harness."""
from __future__ import annotations


class HarnessError(Exception):
    """Base class for all harness failures."""


class ManifestError(HarnessError):
    """The fixture manifest is malformed, inconsistent, or does not match its files."""


class MalformedRecordError(HarnessError):
    """A plan record is not a valid ResearchPlan or carries label-like content."""


class InsufficientEvaluationSetError(HarnessError):
    """The evaluation set is empty or a split falls below the minimum size."""


class HeldOutAccessError(HarnessError):
    """A held-out record was passed to a development-stage operation."""
