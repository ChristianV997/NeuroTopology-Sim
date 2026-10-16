"""Tests for graceful behavior when optional TDA backends are absent.

Guarantees:
1. When optional TDA packages (ripser, gudhi, cripser) are missing, tests cleanly skip
   or verify BACKEND_UNAVAILABLE status.
2. Missing optional software is never treated as a scientific error or test failure.
3. Probes report accurate licenses and version metadata.
"""
from __future__ import annotations

import pytest

from tools.topology_backend_conformance import (
    ComparabilityStatus,
    GudhiCubicalAdapter,
    GudhiRipsAdapter,
    ReferenceSimplicialAdapter,
    RipserAdapter,
    compare_conformance_runs,
    is_module_installed,
    make_known_loop_fixture,
)


def test_probing_optional_packages_does_not_crash() -> None:
    """Probing for optional packages should never raise uncaught exceptions."""
    ripser_adapter = RipserAdapter()
    gudhi_rips_adapter = GudhiRipsAdapter()
    gudhi_cubical_adapter = GudhiCubicalAdapter()

    assert isinstance(ripser_adapter.is_available(), bool)
    assert isinstance(gudhi_rips_adapter.is_available(), bool)
    assert isinstance(gudhi_cubical_adapter.is_available(), bool)

    meta_ripser = ripser_adapter.get_metadata()
    assert meta_ripser.backend_id == "ripser"
    assert meta_ripser.license_type == "MIT"

    meta_gudhi = gudhi_rips_adapter.get_metadata()
    assert meta_gudhi.backend_id == "gudhi_rips"
    assert meta_gudhi.license_type == "MIT"


def test_missing_backend_returns_unavailable_status() -> None:
    """When a backend is absent, comparison returns BACKEND_UNAVAILABLE without crashing."""
    ref_adapter = ReferenceSimplicialAdapter()
    fix = make_known_loop_fixture()
    cfg = fix.get_config(max_dimension=1)

    run_ref = ref_adapter.compute(fix.data, cfg)

    # Test with Ripser adapter
    ripser_adapter = RipserAdapter()
    if not ripser_adapter.is_available():
        run_ripser = ripser_adapter.compute(fix.data, cfg)
        assert run_ripser.success is False
        assert "not installed" in (run_ripser.error_message or "").lower()

        cmp_res = compare_conformance_runs(run_ref, run_ripser, dimension=1)
        assert cmp_res.status == ComparabilityStatus.BACKEND_UNAVAILABLE
        assert cmp_res.is_comparable is False
        assert len(cmp_res.non_comparable_reasons) > 0


@pytest.mark.skipif(not is_module_installed("ripser"), reason="ripser optional package not installed")
def test_ripser_conformance_if_installed() -> None:
    """If ripser is installed, it must conform to the reference engine on the unit square fixture."""
    ref_adapter = ReferenceSimplicialAdapter()
    rips_adapter = RipserAdapter()
    fix = make_known_loop_fixture()
    cfg = fix.get_config(max_dimension=1)

    run_ref = ref_adapter.compute(fix.data, cfg)
    run_rips = rips_adapter.compute(fix.data, cfg)

    assert run_rips.success is True
    cmp_res = compare_conformance_runs(run_ref, run_rips, dimension=1, tolerance=1e-4)
    assert cmp_res.status == ComparabilityStatus.COMPARABLE
    assert cmp_res.passed_tolerance is True


@pytest.mark.skipif(not is_module_installed("gudhi"), reason="gudhi optional package not installed")
def test_gudhi_rips_conformance_if_installed() -> None:
    """If gudhi is installed, its RipsComplex must conform to the reference engine on the unit square fixture."""
    ref_adapter = ReferenceSimplicialAdapter()
    gudhi_adapter = GudhiRipsAdapter()
    fix = make_known_loop_fixture()
    cfg = fix.get_config(max_dimension=1)

    run_ref = ref_adapter.compute(fix.data, cfg)
    run_gudhi = gudhi_adapter.compute(fix.data, cfg)

    assert run_gudhi.success is True
    cmp_res = compare_conformance_runs(run_ref, run_gudhi, dimension=1, tolerance=1e-4)
    assert cmp_res.status == ComparabilityStatus.COMPARABLE
    assert cmp_res.passed_tolerance is True
