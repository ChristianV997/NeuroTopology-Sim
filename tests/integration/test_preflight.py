"""Preflight: path/metadata/dependency validation and the no-hidden-network
default."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.integration_bridge import preflight


def test_missing_input_path_is_an_error(tmp_path):
    errors = preflight.validate_paths(tmp_path / "nope.csv", tmp_path / "out")
    assert any("does not exist" in e for e in errors)


def test_symlinked_input_path_is_rejected(tmp_path):
    real = tmp_path / "real.csv"
    real.write_text("1,2,3\n")
    link = tmp_path / "link.csv"
    link.symlink_to(real)
    errors = preflight.validate_paths(link, tmp_path / "out")
    assert any("symlink" in e for e in errors)


def test_valid_metadata_has_no_errors():
    assert preflight.validate_metadata({"data_mode": "synthetic", "dataset_id": "d1", "seed": 0}) == []


def test_missing_required_metadata_field_is_reported():
    errors = preflight.validate_metadata({"data_mode": "synthetic", "seed": 0})
    assert any("dataset_id" in e for e in errors)


def test_invalid_data_mode_is_rejected():
    errors = preflight.validate_metadata({"data_mode": "bogus", "dataset_id": "d1", "seed": 0})
    assert any("invalid data_mode" in e for e in errors)


def test_non_integer_seed_is_rejected():
    errors = preflight.validate_metadata({"data_mode": "synthetic", "dataset_id": "d1", "seed": "zero"})
    assert any("seed" in e for e in errors)


def test_dependency_profile_flags_unavailable_requested_adapter():
    errors = preflight.validate_dependency_profile(("graph_beta1",), {"graph_beta1": False})
    assert len(errors) == 1
    assert "graph_beta1" in errors[0]


def test_dependency_profile_flags_unknown_adapter_name():
    errors = preflight.validate_dependency_profile(("not_a_real_adapter",), {})
    assert any("unknown adapter" in e for e in errors)


def test_dependency_profile_passes_when_available():
    assert preflight.validate_dependency_profile(("spatial_topology",), {"spatial_topology": True}) == []


# ---- no-hidden-network default ----

def test_network_refused_by_default_when_not_requested():
    allowed, errors = preflight.resolve_network_permission(live_requested=False, allow_network_flag=False)
    assert allowed is False
    assert errors == []


def test_network_refused_when_live_requested_but_no_flag_or_env(monkeypatch):
    monkeypatch.delenv("NTS_INTEGRATION_ALLOW_NETWORK", raising=False)
    allowed, errors = preflight.resolve_network_permission(live_requested=True, allow_network_flag=False)
    assert allowed is False
    assert errors


def test_network_refused_when_flag_set_but_env_missing(monkeypatch):
    monkeypatch.delenv("NTS_INTEGRATION_ALLOW_NETWORK", raising=False)
    allowed, errors = preflight.resolve_network_permission(live_requested=True, allow_network_flag=True)
    assert allowed is False
    assert errors


def test_network_refused_when_env_set_but_flag_missing(monkeypatch):
    monkeypatch.setenv("NTS_INTEGRATION_ALLOW_NETWORK", "true")
    allowed, errors = preflight.resolve_network_permission(live_requested=True, allow_network_flag=False)
    assert allowed is False
    assert errors


def test_network_allowed_only_when_both_flag_and_env_present(monkeypatch):
    monkeypatch.setenv("NTS_INTEGRATION_ALLOW_NETWORK", "true")
    allowed, errors = preflight.resolve_network_permission(live_requested=True, allow_network_flag=True)
    assert allowed is True
    assert errors == []


def test_sha256_of_file_is_stable(tmp_path):
    path = tmp_path / "data.bin"
    path.write_bytes(b"hello world")
    assert preflight.sha256_of_file(path) == preflight.sha256_of_file(path)


def test_sha256_of_file_refuses_past_the_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "_MAX_HASHED_BYTES", 4)
    path = tmp_path / "toobig.bin"
    path.write_bytes(b"way more than four bytes")
    with pytest.raises(ValueError):
        preflight.sha256_of_file(path)


def test_run_preflight_ok_true_for_a_clean_synthetic_request(tmp_path):
    report = preflight.run_preflight(
        input_path=None,
        output_dir=tmp_path / "out",
        metadata={"data_mode": "synthetic", "dataset_id": "d1", "seed": 0},
        requested_adapters=(),
        adapters_available={},
    )
    assert report.ok is True
    assert report.errors == []
