"""No-network and lifecycle tests for the DANDI 000458 caller."""
from __future__ import annotations

import json

import pytest

from data.dandi_nwb_ingest import DandiAsset, IngestionContractError
from tools import stream_process_dandi000458 as stream


def _asset() -> DandiAsset:
    return DandiAsset(
        "000458",
        "0.230317.0039",
        "sub-01/sub-01_behavior+ecephys.nwb",
        "sub-01",
        "https://example.invalid/blobs/fake",
        128,
        "a" * 64,
    )


def test_run_requires_permission_before_dandi_resolution(tmp_path):
    with pytest.raises(IngestionContractError, match="explicit network permission"):
        stream.run(
            str(tmp_path / "outputs" / "run"),
            1.0,
            1,
            2,
            None,
            None,
            output_root=str(tmp_path / "outputs"),
        )


def test_run_resumes_completed_asset_and_keeps_output_contained(tmp_path, monkeypatch):
    root = tmp_path / "outputs"
    out = root / "run"
    calls: list[str] = []
    monkeypatch.setattr(stream, "resolve_asset_blobs", lambda *args, **kwargs: [_asset()])

    def fake_process(asset, out_dir, *_args, **kwargs):
        calls.append(asset.path)
        assert kwargs["network_permission"] is True
        return {"success": True, "output_paths": ["fixture.csv"]}

    monkeypatch.setattr(stream, "process_asset", fake_process)
    assert stream.run(str(out), 1.0, 1, 2, None, None, network_permission=True, output_root=str(root)) == 0
    assert stream.run(str(out), 1.0, 1, 2, None, None, network_permission=True, output_root=str(root)) == 0
    assert calls == [_asset().path]
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["processed"][_asset().path]["success"] is True


def test_output_escape_is_rejected_before_resolution(tmp_path, monkeypatch):
    monkeypatch.setattr(stream, "resolve_asset_blobs", lambda *_args, **_kwargs: pytest.fail("resolution should not run"))
    with pytest.raises(IngestionContractError, match="inside output_root"):
        stream.run(
            str(tmp_path / "outside"),
            1.0,
            1,
            2,
            None,
            None,
            network_permission=True,
            output_root=str(tmp_path / "outputs"),
        )


def test_process_asset_records_source_and_output_checksums(tmp_path, monkeypatch):
    import importlib

    windower = importlib.import_module("sciencer_d.btc_icft.level_m.dandi000458_windows_real")
    monkeypatch.setattr(windower, "build_and_extract_real_windows", lambda *args, **kwargs: ([], []))
    out = tmp_path / "out"
    out.mkdir()

    result = stream.process_asset(_asset(), out, 1.0, 1, 2, network_permission=True)

    assert result["source_checksum_sha256"] == "a" * 64
    assert set(result["output_paths"]) == {
        "sub-01_features_m.csv",
        "sub-01_features_t.csv",
    }
    assert all(len(value) == 64 for value in result["output_sha256"].values())
