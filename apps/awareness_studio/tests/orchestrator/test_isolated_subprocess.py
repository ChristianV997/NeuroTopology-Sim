"""Run the dry-run in a fresh interpreter with network primitives disabled."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_APP_SRC = Path(__file__).resolve().parents[2] / "src"

_SCRIPT = r"""
import json, socket, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path

def _blocked(*args, **kwargs):
    raise RuntimeError("network access attempted")

socket.create_connection = _blocked
socket.socket.connect = _blocked
urllib.request.urlopen = _blocked

from awareness_studio.orchestrator import Orchestrator
from awareness_studio.orchestrator.orchestrator import OrchestratorConfig

result = Orchestrator().run(
    config=OrchestratorConfig(dry_run=True, out_base_dir=Path(sys.argv[1])),
    _now=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
)
print(json.dumps({
    "evidence_state": result.evidence_state,
    "scientific_pass": result.scientific_pass,
    "formal_bayes_factor": result.formal_bayes_factor,
    "stages_failed": result.stages_failed,
}))
"""


def test_dry_run_in_isolated_subprocess_without_network(tmp_path):
    env = {
        **os.environ,
        "PYTHONPATH": str(_APP_SRC),
        "EMBEDDING_PROVIDER": "local_stub",
        "INDEX_BACKEND": "bm25",
        "TOOLS_ENABLED": "false",
        "ANTHROPIC_API_KEY": "",
        "OPENAI_API_KEY": "",
    }
    completed = subprocess.run(
        [sys.executable, "-c", _SCRIPT, str(tmp_path / "out")],
        capture_output=True, text=True, env=env, timeout=120, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload == {
        "evidence_state": "planning",
        "scientific_pass": False,
        "formal_bayes_factor": None,
        "stages_failed": [],
    }
