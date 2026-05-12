from __future__ import annotations
import csv, json, importlib.util
from pathlib import Path
import pytest

from sciencer_d.btc_icft.io import eeg_mne_adapter as a
from sciencer_d.btc_icft.pipelines import extract_mne_signal_blocks as cli


def test_check_mne_available_uninstalled(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda _: None)
    assert a.check_mne_available()["installed"] is False

@pytest.mark.parametrize("ext", [".edf", ".fif", ".set", ".vhdr"])
def test_detect_supported(ext):
    assert a.detect_mne_supported_file(f"x{ext}")["supported"]


def test_detect_unsupported():
    assert not a.detect_mne_supported_file("x.xyz")["supported"]


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        a.extract_mne_signal_windows("/tmp/nope.edf", "DS")


def test_dependency_missing(monkeypatch, tmp_path):
    f = tmp_path / "a.edf"; f.write_text("x")
    monkeypatch.setattr(importlib.util, "find_spec", lambda _: None)
    r = a.extract_mne_signal_windows(str(f), "DS")
    assert r.extraction_status == "dependency_missing"


def test_unsupported_status(tmp_path):
    f = tmp_path / "a.xyz"; f.write_text("x")
    r = a.extract_mne_signal_windows(str(f), "DS")
    assert r.extraction_status == "unsupported_extension"


def test_mock_fixture_outputs(tmp_path):
    out = tmp_path / "out"
    assert cli.main.__call__
    rc = __import__("subprocess").run(["python","-m","sciencer_d.btc_icft.pipelines.extract_mne_signal_blocks","--dataset-id","DS005620","--mock-fixture","--out",str(out)], check=False).returncode
    assert rc == 0
    for n in ["mne_signal_metadata.json","mne_signal_windows.csv","mne_signal_window_values.json","mne_extraction_report.json","omega_event.json","report.md"]:
        assert (out / n).exists()
    json.loads((out / "mne_signal_metadata.json").read_text())
    with (out / "mne_signal_windows.csv").open() as f:
        cols = next(csv.reader(f))
    assert "dataset_id" in cols and "warnings" in cols
    vals = json.loads((out / "mne_signal_window_values.json").read_text())
    assert "signal_values" in vals["windows"][0]
    rep = json.loads((out / "mne_extraction_report.json").read_text())
    assert rep["ready_for_signal_block_conversion"] is True


def test_mock_missing_mode(tmp_path):
    out = tmp_path / "o2"
    rc = __import__("subprocess").run(["python","-m","sciencer_d.btc_icft.pipelines.extract_mne_signal_blocks","--dataset-id","DS005620","--mock-mne-missing","--input",str(tmp_path / "x.edf"),"--out",str(out)], check=False).returncode
    assert rc == 0


def test_safe_text_and_report(tmp_path):
    out = tmp_path / "out"
    __import__("subprocess").run(["python","-m","sciencer_d.btc_icft.pipelines.extract_mne_signal_blocks","--dataset-id","DS005620","--mock-fixture","--out",str(out)], check=True)
    md = (out / "report.md").read_text().lower()
    assert "optional mne adapter" in md and "fixed signal windows" in md and "without inferring labels or targets" in md
    for b in a.BANNED_PHRASES:
        assert b not in md
    omega = json.loads((out / "omega_event.json").read_text())
    om = json.dumps(omega).lower()
    assert "infer" in om and "without inferring labels or targets" in om


def test_cli_missing_input():
    rc = __import__("subprocess").run(["python","-m","sciencer_d.btc_icft.pipelines.extract_mne_signal_blocks","--dataset-id","DS005620"], check=False).returncode
    assert rc != 0


def test_cli_unsupported_extension(tmp_path):
    p=tmp_path/"u.xyz"; p.write_text("x")
    rc = __import__("subprocess").run(["python","-m","sciencer_d.btc_icft.pipelines.extract_mne_signal_blocks","--dataset-id","DS005620","--input",str(p),"--out",str(tmp_path/"o")], check=False).returncode
    assert rc == 0


def test_config_and_no_req_changes():
    c = Path("configs/btc_icft/eeg_mne_adapter.yaml").read_text()
    assert "required_outputs" in c and "guardrails" in c
    assert "import mne" not in Path("sciencer_d/btc_icft/io/eeg_mne_adapter.py").read_text().splitlines()[0:30]


def test_fake_mne_metadata_and_windows(monkeypatch, tmp_path):
    class Raw:
        def __init__(self): self.info={"sfreq":100.0}; self.ch_names=["C3","C4"]; self.n_times=450
        def get_data(self, picks=None, start=0, stop=1):
            import numpy as np
            rows = len(picks) if picks is not None else 2
            return np.ones((rows, stop-start))
    class IO:
        @staticmethod
        def read_raw_edf(*args, **kwargs): return Raw()
    class M:
        __version__="1.0"; io=IO()
    p = tmp_path/"a.edf"; p.write_text("x")
    monkeypatch.setattr(importlib.util, "find_spec", lambda _: object())
    monkeypatch.setattr(__import__("importlib"), "import_module", lambda _: M)
    md = a.load_mne_raw_metadata(str(p))
    assert md["n_channels"] == 2
    r = a.extract_mne_signal_windows(str(p), "DS", window_seconds=2.0, max_windows=2, picks=["C3"])
    assert r.n_windows == 2 and r.n_channels == 1
