"""Governance phrases, optional availability, and owned-path hygiene."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from adapters.mne_csd import MNEUnavailableError, apply_csd, mne_available
from tests.adapters.mne_csd.test_parameter_forwarding import RecordingCallable

REPO = Path(__file__).resolve().parents[3]
OWNED = [
    REPO / "adapters" / "mne_csd",
    REPO / "tests" / "adapters" / "mne_csd",
    REPO / "docs" / "adapters" / "mne_csd.md",
]

FORBIDDEN = (
    "proves consciousness",
    "consciousness solved",
    "clinical treatment",
    "validated theory of everything",
    "toe validation",
    "final theory",
    "ontology promotion",
    "as scientific evidence",
)


def test_mne_unavailable_raises_when_no_callable_and_no_mne(monkeypatch, eeg_raw):
    import adapters.mne_csd.transform as transform

    monkeypatch.setattr(transform, "mne_available", lambda: False)
    with pytest.raises(MNEUnavailableError):
        apply_csd(eeg_raw, channels=["Fz", "Cz", "Pz"], csd_callable=None)


def test_mne_available_matches_import():
    try:
        import mne  # noqa: F401

        assert mne_available() is True
    except Exception:
        assert mne_available() is False


def test_owned_python_compiles():
    files = list((REPO / "adapters" / "mne_csd").glob("*.py"))
    files.extend((REPO / "tests" / "adapters" / "mne_csd").glob("*.py"))
    for path in files:
        ast.parse(path.read_text(encoding="utf-8"))


def test_no_forbidden_claim_phrases_in_owned_docs_and_code():
    skip = {Path(__file__).name}
    for root in OWNED:
        paths = [root] if root.is_file() else list(root.rglob("*"))
        for path in paths:
            if path.is_file() and path.suffix in {".py", ".md"} and path.name not in skip:
                text = path.read_text(encoding="utf-8").lower()
                for phrase in FORBIDDEN:
                    assert phrase not in text, f"{path}: {phrase}"


def test_provenance_json_finite_and_no_remote_dataset_hosts(eeg_raw):
    result = apply_csd(eeg_raw, channels=["Fz", "Cz", "Pz"], csd_callable=RecordingCallable())
    blob = json.dumps(result.provenance.to_dict(), allow_nan=False).lower()
    assert "openneuro.org" not in blob
    assert "amazonaws.com" not in blob
