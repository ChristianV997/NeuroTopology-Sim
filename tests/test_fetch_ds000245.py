"""Fail-closed compatibility tests for the retired ds000245 downloader.

The old tests asserted full S3 enumeration and downloads.  Those expectations
are intentionally retired: ds000245 now accepts only explicit bounded,
checksum-aware manifest requests through the canonical chunk cache.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.fetch_ds000245 import BoundedAccessError, fetch


def test_legacy_full_dataset_fetch_is_rejected(tmp_path: Path) -> None:
    """A destination-only call must not enumerate or download a dataset."""
    with pytest.raises(BoundedAccessError, match="full-dataset"):
        fetch(tmp_path)


def test_legacy_subject_and_limit_filters_are_rejected(tmp_path: Path) -> None:
    """Legacy convenience filters cannot authorize an unbounded transfer."""
    with pytest.raises(BoundedAccessError, match="full-dataset"):
        fetch(tmp_path, subjects=["sub-CTL01"])
    with pytest.raises(BoundedAccessError, match="full-dataset"):
        fetch(tmp_path, limit=1)


def test_empty_or_missing_bounded_request_is_rejected(tmp_path: Path) -> None:
    """No implicit default manifest or full-object fallback is permitted."""
    with pytest.raises(BoundedAccessError, match="explicit"):
        fetch(None)
    with pytest.raises(BoundedAccessError, match="at least one"):
        fetch([])
