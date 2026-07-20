"""CI-durable proof that a registry-only dataset (zero per-dataset Python code)
streams real signal-derived output.

Uses an offline synthetic BIDS fixture with a NEW dataset's real task labels
(ds003800: AuditoryGammaEntrainment / Rest) driven entirely through the
onboarding registry + generic modules -- no `{ds}_windows*.py` or
`{ds}_real_topology.py` files exist for these datasets. Mirrors the
"features track signal, not metadata" regression pattern every hand-ported
dataset test uses.
"""
from __future__ import annotations

import importlib.util
from dataclasses import asdict

import pytest

_HAVE = all(importlib.util.find_spec(m) for m in ("mne", "mne_bids", "edfio"))
pytestmark = pytest.mark.skipif(not _HAVE, reason="requires mne, mne-bids, edfio")

from sciencer_d.btc_icft.datasets.onboarding_registry import get_dataset_config

_NEW_DATASETS = ["ds004148", "ds003800", "ds002338"]


def test_new_datasets_registered_config_only():
    """The 3 new datasets exist in the registry and have NO per-dataset Python
    modules -- the whole point of the generalization."""
    import importlib.util as u
    for ds in _NEW_DATASETS:
        cfg = get_dataset_config(ds)
        assert cfg.task_to_state and cfg.contrasts
        # no {ds}_windows_real / {ds}_real_topology modules should exist
        assert u.find_spec(f"sciencer_d.btc_icft.level_m.{ds}_windows_real") is None
        assert u.find_spec(f"sciencer_d.btc_icft.level_t.{ds}_real_topology") is None


def _build_synth_bids(root, task_labels):
    import shutil
    from pathlib import Path
    import mne
    import numpy as np
    from mne_bids import BIDSPath, write_raw_bids

    def make_raw(state, seed, sfreq=250.0, secs=20.0, n_ch=8):
        rng = np.random.default_rng(seed)
        n = int(sfreq * secs); t = np.arange(n) / sfreq
        base = 4 + (sum(ord(c) for c in state) % 20)
        sig = np.zeros((n_ch, n))
        for c in range(n_ch):
            sig[c] = np.sin(2 * np.pi * (base + c * 1.7) * t + c * 0.5) + 0.6 * rng.standard_normal(n)
        info = mne.create_info([f"EEG{i:02d}" for i in range(n_ch)], sfreq, ch_types="eeg")
        raw = mne.io.RawArray(sig * 1e-5, info, verbose="ERROR")
        raw.set_montage(mne.channels.make_standard_montage("standard_1020"), on_missing="ignore", verbose="ERROR")
        raw.info["line_freq"] = 60
        return raw

    root = Path(root)
    if root.exists():
        shutil.rmtree(root)
    for si, sub in enumerate(("001", "002")):
        for task in task_labels:
            bp = BIDSPath(subject=sub, task=task, run="01", datatype="eeg", root=root, suffix="eeg", extension=".edf")
            write_raw_bids(make_raw(task, seed=si * 10 + (sum(ord(c) for c in task) % 7)), bp,
                           overwrite=True, allow_preload=True, format="EDF", verbose="ERROR")
    return str(root)


def test_registry_only_dataset_produces_signal_derived_topology(tmp_path):
    """A dataset served ONLY by the registry (ds003800) must yield real,
    signal-derived topology: distinct per-window q_abs, and different output for
    different signal content (the anti-hash-fabrication guarantee)."""
    from sciencer_d.btc_icft.level_m.generic_windows_real import build_and_extract_real_windows
    from sciencer_d.btc_icft.level_t.base_real_topology import compute_real_topology_for_window

    # ds003800's real BIDS task labels (AuditoryGammaEntrainment, Rest)
    root = _build_synth_bids(tmp_path / "bids", ["AuditoryGammaEntrainment", "Rest"])
    m_rows = build_and_extract_real_windows("ds003800", root, window_seconds=4, max_windows_per_file=2, max_channels=8)
    m_dicts = [asdict(r) for r in m_rows]
    assert m_dicts, "no windows extracted"

    # states mapped from the registry (not inferred in code)
    states = {r["state_label"] for r in m_dicts}
    assert states == {"entrainment", "rest"}

    t_rows = [asdict(compute_real_topology_for_window(r, max_channels=8)) for r in m_dicts]
    q_abs = [r["q_abs"] for r in t_rows]
    assert all(q != 0.0 for q in q_abs), "degenerate (all-zero) topology -- not signal-derived"
    assert len(set(q_abs)) == len(q_abs), "q_abs identical across windows -- suspicious of hash fabrication"


def test_registry_only_topology_changes_with_signal_not_metadata(tmp_path, monkeypatch):
    """Regression for the fabrication bug class: identical metadata but different
    signal must give different topology (proves the value comes from the signal)."""
    import numpy as np
    from sciencer_d.btc_icft.level_t.base_real_topology import compute_real_topology_for_window

    f1 = tmp_path / "a.edf"; f2 = tmp_path / "b.edf"
    f1.write_bytes(b"x"); f2.write_bytes(b"x")
    signals = {
        str(f1): np.array([[1.0, 1.0, 1.0, 1.0] for _ in range(4)]),
        str(f2): np.array([[float(i % 7) for i in range(40)] for _ in range(6)]),
    }
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda path, *a, **k: signals[path])
    base = {"row_id": "r", "subject_id": "sub-001", "session_id": None, "run_id": None,
            "window_id": "w", "task_label": "Rest", "window_start_s": "0", "window_end_s": "1"}
    out_a = compute_real_topology_for_window({**base, "source_file": str(f1)})
    out_b = compute_real_topology_for_window({**base, "source_file": str(f2)})
    assert (out_a.q_abs, out_a.n_valid_triangles) != (out_b.q_abs, out_b.n_valid_triangles)


def test_discovery_scaffold_never_infers_state_labels(monkeypatch):
    """The discovery tool must map every discovered task to a TODO_state
    placeholder -- it must NEVER guess a semantic state (no_label_inference)."""
    import importlib.util as u, sys, json, io
    spec = u.spec_from_file_location("discover_openneuro_tasks", "tools/discover_openneuro_tasks.py")
    mod = u.module_from_spec(spec); sys.modules[spec.name] = mod; spec.loader.exec_module(mod)
    # structural discovery is mocked; the scaffold logic is what we assert on
    monkeypatch.setattr(mod, "discover", lambda ds, max_subjects=3: ["EyesOpen", "EyesClosed", "Task42"])
    monkeypatch.setattr(sys, "argv", ["discover_openneuro_tasks.py", "dsFAKE"])
    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    rc = mod.main()
    monkeypatch.undo()
    assert rc == 0
    scaffold = json.loads(buf.getvalue())
    # every task present, every state a TODO placeholder (nothing inferred)
    assert set(scaffold["task_to_state"]) == {"eyesopen", "eyesclosed", "task42"}
    assert set(scaffold["task_to_state"].values()) == {"TODO_state"}
