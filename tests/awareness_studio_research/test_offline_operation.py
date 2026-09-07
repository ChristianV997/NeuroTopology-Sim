"""Confirms the package's default behavior is fully offline and imports
no heavy scientific dependency (numpy/scipy/sklearn/mne/torch/pandas)."""
from __future__ import annotations

import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tools.awareness_studio_research import importers
from tools.awareness_studio_research.checksum import stable_source_id
from tools.awareness_studio_research.models import LiteratureSource
from tools.awareness_studio_research.store import EvidenceRegistry

FIXTURES_DIR = Path(__file__).parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_no_socket_calls_during_full_ingest_cycle(tmp_path, monkeypatch):
    def _no_network(*args, **kwargs):
        raise AssertionError("network access attempted during offline ingest")

    monkeypatch.setattr(socket, "socket", _no_network)

    registry = EvidenceRegistry(tmp_path / "events.jsonl")
    sources = importers.import_json_export(FIXTURES_DIR / "sample_export.json")
    for source in sources:
        registry.add_source(source)
    assert len(registry.list_sources()) == 2


def test_no_heavy_import_in_package_modules():
    """Isolated subprocess: import every module in the package and
    confirm none of numpy/scipy/sklearn/mne/torch/pandas end up loaded --
    this package must work in a minimal, dependency-light environment."""
    script = (
        "import sys; "
        "import tools.awareness_studio_research as pkg; "
        "import tools.awareness_studio_research.models; "
        "import tools.awareness_studio_research.checksum; "
        "import tools.awareness_studio_research.dedupe; "
        "import tools.awareness_studio_research.store; "
        "import tools.awareness_studio_research.importers; "
        "import tools.awareness_studio_research.network; "
        "import tools.awareness_studio_research.query; "
        "import tools.awareness_studio_research.verification; "
        "heavy = {'numpy', 'scipy', 'sklearn', 'mne', 'torch', 'pandas'}; "
        "loaded = heavy & set(sys.modules); "
        "print('LOADED_HEAVY=' + ','.join(sorted(loaded)))"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "LOADED_HEAVY=" in result.stdout
    loaded_line = next(line for line in result.stdout.splitlines() if line.startswith("LOADED_HEAVY="))
    loaded = loaded_line.split("=", 1)[1]
    assert loaded == "", f"unexpected heavy imports: {loaded}"


def test_isolated_subprocess_cli_ingest_and_query(tmp_path):
    store_path = tmp_path / "events.jsonl"
    ingest = subprocess.run(
        [
            sys.executable, "scripts/awareness_studio_research.py",
            "--store", str(store_path), "ingest", "--kind", "json",
            "--input", str(FIXTURES_DIR / "sample_export.json"),
        ],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert ingest.returncode == 0, ingest.stderr
    assert "added:" in ingest.stdout

    list_sources = subprocess.run(
        [sys.executable, "scripts/awareness_studio_research.py", "--store", str(store_path), "list-sources"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert list_sources.returncode == 0, list_sources.stderr
    assert "Decentering" in list_sources.stdout


def test_no_hidden_network_import_at_module_load(monkeypatch):
    """Importing network.py itself must not touch the network -- only
    calling its functions with allow_network=True does."""

    def _no_network(*args, **kwargs):
        raise AssertionError("network access attempted merely by importing network.py")

    monkeypatch.setattr(socket, "socket", _no_network)
    import importlib

    import tools.awareness_studio_research.network as network_module

    importlib.reload(network_module)
