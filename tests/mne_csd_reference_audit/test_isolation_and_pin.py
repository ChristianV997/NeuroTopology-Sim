from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from tools.mne_csd_reference_audit import pin

REPO_ROOT = Path(__file__).resolve().parents[2]

_ISOLATED = """
import socket, sys
sys.path.insert(0, sys.argv[1])
def _blocked(*a, **k):
    raise SystemExit("network access attempted")
socket.socket.connect = _blocked
socket.create_connection = _blocked
from tools.mne_csd_reference_audit.report import build_report
report = build_report()
print(report["status"], "mne" in sys.modules, report["evidence_class"])
"""


def test_reference_runs_in_a_clean_process_without_mne_or_network():
    proc = subprocess.run(
        [sys.executable, "-I", "-c", _ISOLATED, str(REPO_ROOT)],
        capture_output=True, text=True, timeout=300, cwd=str(REPO_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    status, mne_loaded, evidence = proc.stdout.strip().splitlines()[-1].split()
    assert status == "HOLD"
    assert mne_loaded == "False"
    assert evidence == "SYNTHETIC_ONLY"


def test_reference_package_source_never_imports_mne():
    package = REPO_ROOT / "tools" / "mne_csd_reference_audit"
    for source in package.glob("*.py"):
        text = source.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import mne|from mne)", text, re.MULTILINE), source.name


def test_pin_is_internally_consistent():
    assert pin.MNE_TAG == f"v{pin.MNE_VERSION}"
    assert re.fullmatch(r"[0-9a-f]{40}", pin.MNE_TAG_COMMIT)
    assert re.fullmatch(r"[0-9a-f]{64}", pin.MNE_SDIST_SHA256)
    assert pin.MNE_SDIST_FILENAME == f"mne-{pin.MNE_VERSION}.tar.gz"
    assert pin.MNE_LICENSE == "BSD-3-Clause"
    for digest in pin.MNE_SOURCE_FILES.values():
        assert re.fullmatch(r"[0-9a-f]{64}", digest)
    assert pin.MNE_DEFAULTS == {"stiffness": 4, "n_legendre_terms": 50, "lambda2": 1e-5, "sphere": "auto"}


def test_report_json_is_strict_and_status_is_hold():
    from tools.mne_csd_reference_audit.report import build_report, to_json

    text = to_json(build_report())
    decoded = json.loads(text, parse_constant=lambda t: (_ for _ in ()).throw(ValueError(t)))
    assert decoded["status"] == "HOLD"
    assert decoded["levels"]["L3_mne_execution_parity"].startswith("not executed")
    assert decoded["pinned_mne"]["tag_commit"] == pin.MNE_TAG_COMMIT
