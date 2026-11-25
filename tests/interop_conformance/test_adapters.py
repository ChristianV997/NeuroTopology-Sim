"""Dynamic adapter conformance test suite.

Evaluates discovered adapters (PR #214, PR #220) against the 16 contract properties.
If an adapter or capability is not available in the current checkout, reports it
honestly as skipped/unavailable rather than silently ignoring or failing.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from tests.interop_conformance.validator import ConformanceValidator


def test_pr214_mne_adapter_conformance(discovered_adapters, fixture_fif_metadata_path, fixture_malformed_path):
    adapter_info = discovered_adapters.get("PR214_MNE", {})
    if not adapter_info.get("available", False):
        pytest.skip(f"PR #214 MNE adapter not available in this environment: {adapter_info.get('reason', 'Missing capability')}")

    fn = adapter_info["function"]
    cap_check = adapter_info.get("capability_check")

    # Property 10: Capability state
    if cap_check:
        eval_cap = ConformanceValidator.validate_property_10_capability_state("PR214_MNE", cap_check)
        assert eval_cap.passed

    # Property 13: Lazy imports
    eval_lazy = ConformanceValidator.validate_property_13_lazy_imports("sciencer_d.btc_icft.io.eeg_mne_adapter", "mne")
    assert eval_lazy.passed

    # Property 11: Malformed error
    eval_mal = ConformanceValidator.validate_property_11_malformed_errors(fn, fixture_malformed_path)
    assert eval_mal.passed


def test_pr220_native_adapter_conformance(discovered_adapters, fixture_csv_path, fixture_malformed_path):
    adapter_info = discovered_adapters.get("PR220_Native", {})
    if not adapter_info.get("available", False):
        pytest.skip(f"PR #220 Native adapter not available in this environment: {adapter_info.get('reason', 'Missing capability')}")

    fn = adapter_info["function"]
    cap_check = adapter_info.get("capability_check")

    # Property 10: Capability state
    if cap_check:
        eval_cap = ConformanceValidator.validate_property_10_capability_state("PR220_Native", cap_check)
        assert eval_cap.passed

    # Property 11: Malformed error
    eval_mal = ConformanceValidator.validate_property_11_malformed_errors(fn, fixture_malformed_path)
    assert eval_mal.passed
