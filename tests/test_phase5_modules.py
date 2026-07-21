"""Tests for Phase 5 modules: neuromaps, atlas utilities, and fast-TR fixtures."""
from __future__ import annotations

import pytest
import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
# neuromaps_nulls tests
# ─────────────────────────────────────────────────────────────────────────────


def test_neuromaps_nulls_import():
    """Test that neuromaps_nulls module can be imported."""
    from validation.neuromaps_nulls import spin_test_neuromaps
    assert callable(spin_test_neuromaps)


def test_neuromaps_spin_test_fallback_2d():
    """Test that neuromaps spin test falls back to 2D hand-rolled when surface is None."""
    from validation.neuromaps_nulls import spin_test_neuromaps

    # 2D coordinates (montage case)
    xy = np.array([[0, 0], [1, 0], [0, 1], [1, 1]], dtype=float)
    values = np.array([1.0, 2.0, 3.0, 4.0], dtype=float)

    def stat_fn(v):
        return float(np.mean(v))

    result = spin_test_neuromaps(
        values,
        xy,
        stat_fn,
        method="alexander_bloch",
        n_permutations=100,
        seed=42,
        surface=None,  # Trigger fallback
    )

    assert "observed" in result
    assert "p_value" in result
    assert result["metric_kind"] == "spatial_spin_null_test"


def test_neuromaps_null_distribution():
    """Test null distribution generation via neuromaps wrapper."""
    from validation.neuromaps_nulls import spin_null_distribution_neuromaps

    xy = np.array([[0, 0], [1, 0], [0, 1]], dtype=float)
    values = np.array([1.0, 2.0, 3.0], dtype=float)

    def stat_fn(v):
        return float(np.sum(v))

    null = spin_null_distribution_neuromaps(
        values,
        xy,
        stat_fn,
        method="alexander_bloch",
        n_permutations=50,
        seed=42,
        surface=None,
    )

    assert isinstance(null, np.ndarray)
    assert null.size > 0
    assert np.all(np.isfinite(null))


@pytest.mark.skipif(
    pytest.importorskip("neuromaps", minversion=None) is None,
    reason="neuromaps not installed",
)
def test_neuromaps_methods_documented():
    """Test that neuromaps methods are documented in the module."""
    from validation.neuromaps_nulls import spin_test_neuromaps

    # Verify method options are documented (no actual neuromaps call)
    doc = spin_test_neuromaps.__doc__
    assert "alexander_bloch" in doc
    assert "vasa" in doc or "method" in doc


# ─────────────────────────────────────────────────────────────────────────────
# atlas_utils tests
# ─────────────────────────────────────────────────────────────────────────────


def test_atlas_utils_import():
    """Test that atlas_utils module can be imported."""
    from validation.atlas_utils import fetch_schaefer_atlas, fetch_yeo_networks
    assert callable(fetch_schaefer_atlas)
    assert callable(fetch_yeo_networks)


def test_schaefer_specs():
    """Test Schaefer atlas specs are documented."""
    from validation.atlas_utils import fetch_schaefer_atlas

    # Verify function has proper docstring
    assert "400" in fetch_schaefer_atlas.__doc__
    assert "Schaefer" in fetch_schaefer_atlas.__doc__


def test_yeo_specs():
    """Test Yeo network specs are documented."""
    from validation.atlas_utils import fetch_yeo_networks

    doc = fetch_yeo_networks.__doc__
    assert "7" in doc
    assert "17" in doc


@pytest.mark.skipif(
    pytest.importorskip("nilearn", minversion=None) is None,
    reason="nilearn not installed",
)
def test_schaefer_fetch_basic():
    """Test Schaefer atlas fetch (requires nilearn)."""
    from validation.atlas_utils import fetch_schaefer_atlas

    atlas = fetch_schaefer_atlas(n_rois=100)
    assert "maps" in atlas
    assert "labels" in atlas
    assert "n_rois" in atlas
    assert atlas["n_rois"] == 100


@pytest.mark.skipif(
    pytest.importorskip("nilearn", minversion=None) is None,
    reason="nilearn not installed",
)
def test_yeo_fetch_basic():
    """Test Yeo network fetch (requires nilearn)."""
    from validation.atlas_utils import fetch_yeo_networks

    atlas = fetch_yeo_networks(n_networks=7)
    assert "maps" in atlas
    assert "labels" in atlas
    assert atlas["n_networks"] == 7


def test_atlas_invalid_n_rois():
    """Test that invalid n_rois raises ValueError."""
    from validation.atlas_utils import fetch_schaefer_atlas

    pytest.importorskip("nilearn")
    with pytest.raises(ValueError, match="n_rois"):
        fetch_schaefer_atlas(n_rois=999)


def test_atlas_invalid_n_networks():
    """Test that invalid n_networks raises ValueError."""
    from validation.atlas_utils import fetch_yeo_networks

    pytest.importorskip("nilearn")
    with pytest.raises(ValueError, match="n_networks"):
        fetch_yeo_networks(n_networks=5)


def test_ci_fixture_adhd_sample():
    """Test ADHD sample CI fixture documentation."""
    from validation.atlas_utils import ci_fixture_adhd_sample

    doc = ci_fixture_adhd_sample.__doc__
    assert "ADHD" in doc or "40" in doc


# ─────────────────────────────────────────────────────────────────────────────
# fast_tr_fixtures tests
# ─────────────────────────────────────────────────────────────────────────────


def test_fast_tr_fixtures_import():
    """Test that fast_tr_fixtures module can be imported."""
    from validation.fast_tr_fixtures import (
        hcp_ya_specs,
        nki_rs_specs,
        fast_tr_comparison_table,
    )
    assert callable(hcp_ya_specs)
    assert callable(nki_rs_specs)
    assert callable(fast_tr_comparison_table)


def test_hcp_ya_specs():
    """Test HCP-YA specs are correct."""
    from validation.fast_tr_fixtures import hcp_ya_specs

    specs = hcp_ya_specs()
    assert isinstance(specs, dict)
    assert specs["tr"] == 0.72
    assert specs["n_subjects"] > 1000
    assert "ConnectomeDB" in specs["url"] or "connectome" in specs["url"].lower()


def test_nki_rs_specs():
    """Test NKI-RS specs are correct."""
    from validation.fast_tr_fixtures import nki_rs_specs

    specs = nki_rs_specs()
    assert isinstance(specs, dict)
    assert specs["tr"] == 0.645
    assert specs["n_subjects"] >= 1000
    assert "no DUA" in specs["access_level"] or "CC0" in specs["access_level"]


def test_hcp_ya_fetch_stub():
    """Test HCP-YA fetch returns expected stub structure."""
    from validation.fast_tr_fixtures import fetch_hcp_ya_subject

    result = fetch_hcp_ya_subject("100206", run=1)
    assert "subject_id" in result
    assert result["subject_id"] == "100206"
    assert "tr" in result
    assert result["tr"] == 0.72
    assert "status" in result


def test_nki_rs_fetch_stub():
    """Test NKI-RS fetch returns expected stub structure."""
    from validation.fast_tr_fixtures import fetch_nki_rs_subject

    result = fetch_nki_rs_subject("A00008326", session=1)
    assert "subject_id" in result
    assert result["subject_id"] == "A00008326"
    assert "session" in result
    assert result["session"] == 1
    assert "tr" in result
    assert result["tr"] == 0.645


def test_hcp_ya_fetch_invalid_run():
    """Test that invalid run raises ValueError."""
    from validation.fast_tr_fixtures import fetch_hcp_ya_subject

    with pytest.raises(ValueError, match="run"):
        fetch_hcp_ya_subject("100206", run=5)


def test_fast_tr_comparison_table():
    """Test comparison table is properly formatted."""
    from validation.fast_tr_fixtures import fast_tr_comparison_table

    table = fast_tr_comparison_table()
    assert isinstance(table, str)
    assert "ds005237" in table or "ds000031" in table
    assert "NKI-RS" in table
    assert "HCP-YA" in table
    assert "TR" in table


def test_fast_tr_documentation():
    """Test fast-TR documentation is comprehensive."""
    from validation.fast_tr_fixtures import documentation_fast_tr_phase_topology

    doc = documentation_fast_tr_phase_topology()
    assert isinstance(doc, str)
    assert "Nyquist" in doc or "nyquist" in doc.lower()
    assert "Phase" in doc or "phase" in doc.lower()
    assert "645" in doc or "645ms" in doc


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests
# ─────────────────────────────────────────────────────────────────────────────


def test_phase5_modules_no_hard_dependencies():
    """Test that Phase 5 modules don't require hard dependencies to import."""
    # These imports should succeed even if neuromaps/nilearn/boto3 are not installed
    from validation import neuromaps_nulls
    from validation import atlas_utils
    from validation import fast_tr_fixtures

    assert neuromaps_nulls is not None
    assert atlas_utils is not None
    assert fast_tr_fixtures is not None


def test_phase5_dependencies_documented():
    """Test that Phase 5 dependencies are added to requirements.txt."""
    with open("/home/user/ScienceR-Dsim/requirements.txt") as f:
        content = f.read()
        assert "neuromaps" in content
        assert "nilearn" in content
        assert "boto3" in content
