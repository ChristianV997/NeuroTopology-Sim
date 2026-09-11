"""No-network, no-solver, finite JSON, and Windows/POSIX path handling."""
from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.integration.research_cycle.fixtures import artifact_payload, happy_chain, write_chain
from tests.integration.research_cycle.inspector import (
    ContractError,
    dumps_finite,
    inspect_directory,
    normalize_path,
    owned_python_files,
    parse_stage_document,
    scan_owned_imports,
    stamp_checksum,
    write_document,
)


def test_windows_and_posix_path_forms_are_equivalent() -> None:
    posix = "runs/cycle/metrics.json"
    windows = r"runs\cycle\metrics.json"
    drive = r"C:\research\cycle\metrics.json"
    mixed = r"runs\\cycle/metrics.json"
    assert normalize_path(posix) == "runs/cycle/metrics.json"
    assert normalize_path(windows) == "runs/cycle/metrics.json"
    assert normalize_path(drive) == "research/cycle/metrics.json"
    assert normalize_path(mixed) == "runs/cycle/metrics.json"


def test_artifact_manifest_accepts_windows_and_posix_paths(tmp_path: Path) -> None:
    docs = happy_chain()
    artifacts = dict(docs[4])
    artifacts["payload"] = artifact_payload(
        paths=[r"runs\cycle\summary.json", "runs/cycle/metrics.json"]
    )
    path = tmp_path / "05_artifact_manifest.json"
    write_document(path, stamp_checksum(artifacts))
    parsed = parse_stage_document(path)
    paths = [normalize_path(item["relative_path"]) for item in parsed.payload["artifacts"]]
    assert paths == ["runs/cycle/summary.json", "runs/cycle/metrics.json"]


def test_finite_json_is_preserved_and_nan_is_rejected(tmp_path: Path) -> None:
    docs = happy_chain()
    serialized = dumps_finite(docs[0])
    assert "NaN" not in serialized
    assert "Infinity" not in serialized
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema_version": "x", "value": NaN}\n', encoding="utf-8")
    with pytest.raises(ContractError, match="non-finite"):
        parse_stage_document(bad)


def test_owned_sources_import_neither_network_nor_solvers() -> None:
    hits = scan_owned_imports()
    assert hits["solver"] == []
    assert hits["network"] == []
    assert owned_python_files()


def test_inspection_makes_no_network_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_chain(tmp_path, happy_chain())

    def blocked(*_args, **_kwargs):
        raise AssertionError("network access is forbidden in research-cycle integration tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    report = inspect_directory(tmp_path)
    assert report.network_accessed is False
    assert report.solver_executed is False
    assert report.status == "COMPLETE"


def test_inspector_subprocess_does_not_load_solvers(tmp_path: Path) -> None:
    write_chain(tmp_path, happy_chain())
    repo = Path(__file__).resolve().parents[3]
    script = """
import json, sys
from pathlib import Path
repo = Path(sys.argv[1])
root = Path(sys.argv[2])
sys.path.insert(0, str(repo))
from tests.integration.research_cycle.inspector import inspect_directory
report = inspect_directory(root)
forbidden = {'numpy', 'scipy', 'sklearn', 'mne', 'torch', 'ripser', 'gudhi', 'requests'}
loaded = sorted(name for name in forbidden if name in sys.modules)
print(json.dumps({'status': report.status, 'solver_executed': report.solver_executed, 'loaded': loaded}))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(repo), str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "COMPLETE"
    assert payload["solver_executed"] is False
    assert payload["loaded"] == []
