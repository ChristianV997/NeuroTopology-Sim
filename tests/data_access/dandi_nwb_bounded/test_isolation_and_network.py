"""Isolated subprocess and no-network gates for DANDI/NWB bounded ingest."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from data.dandi_nwb_ingest import (
    IngestionContractError,
    LocalFileWindowSource,
    WindowRequest,
    Provenance,
    read_bounded_window,
    open_nwb_lazy,
    resolve_asset_blobs,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_isolated_subprocess_bounded_read(tmp_path):
    fixture = tmp_path / "window.bin"
    fixture.write_bytes(b"01234567")
    script = tmp_path / "child.py"
    script.write_text(
        f"""
import json, sys
sys.path.insert(0, {str(REPO_ROOT)!r})
from data.dandi_nwb_ingest import LocalFileWindowSource, Provenance, WindowRequest, read_bounded_window
src = LocalFileWindowSource({str(fixture)!r})
req = WindowRequest(
    provenance=Provenance("ds","obj","local_fixture","fixture://obj",synthetic=True),
    start=0, stop=4, unit="bytes", expected_size=4,
    checksum_policy="none", expected_checksum=None,
    cache_budget_bytes=64, consumer_lease="child",
    eviction_policy="release_after_final_consumer",
    network_permission=False,
)
result = read_bounded_window(src, req)
print(json.dumps(result.to_dict(), allow_nan=False, sort_keys=True))
assert src.closed == 1
assert result.state.value == "COMPLETE"
""",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload["state"] == "COMPLETE"
    assert payload["bytes_read"] == 4
    assert payload["checksum_status"] == "unknown"


def test_no_live_dandi_or_aws_urls_in_owned_tests():
    root = REPO_ROOT / "tests" / "data_access" / "dandi_nwb_bounded"
    # Build needles without embedding live URLs as contiguous literals in this file.
    forbidden = [
        "https://" + "api.dandiarchive.org",
        "https://" + "dandiarchive.org",
        "https://" + "dandiarchive.s3.amazonaws.com",
        "s3://" + "dandiarchive",
    ]
    for path in root.rglob("*.py"):
        if path.name == Path(__file__).name:
            continue
        lowered = path.read_text(encoding="utf-8").lower()
        for needle in forbidden:
            assert needle not in lowered, f"{path} contains live endpoint {needle}"


def test_offline_blocks_remote_helpers():
    with pytest.raises(IngestionContractError):
        open_nwb_lazy("https://example.invalid/x.nwb", network_permission=False, offline=True)
    with pytest.raises(IngestionContractError):
        resolve_asset_blobs("000458", "0.230317.0039", network_permission=False, offline=True)
