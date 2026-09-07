"""Unit tests for TDA backend probes."""
from __future__ import annotations

import pytest

from tools.tda_reproducibility.probes import (
    has_tda_adapters_module,
    is_module_available,
    probe_all_backends,
    probe_fallback,
    probe_gtda,
    probe_gudhi,
    probe_ripser,
    probe_ripserplusplus,
)
from tools.tda_reproducibility.types import BackendId, BackendStatus


def test_probe_all_backends_returns_five_backends():
    probes = probe_all_backends()
    assert len(probes) == 5
    ids = [p.backend_id for p in probes]
    assert BackendId.RIPSER.value in ids
    assert BackendId.GUDHI.value in ids
    assert BackendId.GTDA.value in ids
    assert BackendId.RIPSERPLUSPLUS.value in ids
    assert BackendId.FALLBACK.value in ids


def test_probe_ripser_returns_valid_structure():
    p = probe_ripser()
    assert p.backend_id == BackendId.RIPSER.value
    assert p.status in [BackendStatus.AVAILABLE.value, BackendStatus.MISSING.value]
    assert isinstance(p.is_available, bool)
    assert p.max_dimension_supported >= 1
    assert p.supports_distance_matrix is True
    assert p.supports_point_cloud is True
    d = p.to_dict()
    assert d["backend_id"] == "ripser"
    assert "status" in d


def test_probe_gudhi_returns_valid_structure():
    p = probe_gudhi()
    assert p.backend_id == BackendId.GUDHI.value
    assert p.status in [BackendStatus.AVAILABLE.value, BackendStatus.MISSING.value]
    assert isinstance(p.is_available, bool)
    assert p.max_dimension_supported >= 1


def test_probe_gtda_and_ripserplusplus_graceful_missing():
    p_gtda = probe_gtda()
    assert p_gtda.backend_id == BackendId.GTDA.value
    assert isinstance(p_gtda.is_available, bool)

    p_rpp = probe_ripserplusplus()
    assert p_rpp.backend_id == BackendId.RIPSERPLUSPLUS.value
    assert isinstance(p_rpp.is_available, bool)


def test_probe_fallback_always_available():
    p = probe_fallback()
    assert p.backend_id == BackendId.FALLBACK.value
    assert p.is_available is True
    assert p.is_exact is False


def test_is_module_available_nonexistent():
    assert is_module_available("definitely_non_existent_module_xyz_123") is False


def test_has_tda_adapters_returns_bool():
    res = has_tda_adapters_module()
    assert isinstance(res, bool)
