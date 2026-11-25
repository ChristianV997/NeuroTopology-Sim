"""Offline tests for the chunked OpenNeuro stimulus-onset runner.

A local HTTP server with byte-range support stands in for the OpenNeuro S3 bucket, so these
tests never touch the network. They check exact chunk bytes, deletion after consumption,
fail-closed network denial, the sweep end to end, and the held-out and shuffle statistics.
"""

from __future__ import annotations

import http.server
import json
import threading
import urllib.parse
from pathlib import Path

import numpy as np
import pytest

from pipelines import openneuro_chunked as oc

BUCKET = "bucket"
CHANNELS = [
    "FP1", "FP2", "F3", "F4", "C3", "C4", "P3", "P4", "O1", "O2", "F7", "F8", "T7", "T8", "P7",
    "P8", "FZ", "CZ", "PZ", "IZ", "FC1", "FC2", "CP1", "CP2", "FC5", "FC6", "CP5", "CP6", "TP9", "TP10",
]
SFREQ = 5000


class _RangeHandler(http.server.BaseHTTPRequestHandler):
    root: Path

    def log_message(self, *args):  # keep test output quiet
        return

    def do_HEAD(self):  # noqa: N802 - http.server naming
        self._respond(head=True)

    def do_GET(self):  # noqa: N802 - http.server naming
        self._respond(head=False)

    def _send(self, code: int, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _respond(self, *, head: bool) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        parts = parsed.path.lstrip("/").split("/", 1)
        if not parts or parts[0] != BUCKET:
            return self._send(404, b"")
        if len(parts) == 1 or parts[1] == "":
            if not parsed.query:
                return self._send(404, b"")
            return self._listing(urllib.parse.parse_qs(parsed.query))
        target = self.root / parts[1]
        if not target.is_file():
            return self._send(404, b"")
        size = target.stat().st_size
        range_header = self.headers.get("Range")
        if range_header and not head:
            first, last = range_header.split("=", 1)[1].split("-", 1)
            start, end = int(first), min(int(last), size - 1)
            with target.open("rb") as fh:
                fh.seek(start)
                body = fh.read(end - start + 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(size))
        self.end_headers()
        if not head:
            self.wfile.write(target.read_bytes())

    def _listing(self, query: dict) -> None:
        prefix = query.get("prefix", [""])[0]
        delimiter = query.get("delimiter", [""])[0]
        contents: list[tuple[str, int]] = []
        common: set[str] = set()
        for path in sorted(self.root.rglob("*")):
            if not path.is_file():
                continue
            key = path.relative_to(self.root).as_posix()
            if not key.startswith(prefix):
                continue
            rest = key[len(prefix):]
            if delimiter and delimiter in rest:
                common.add(prefix + rest.split(delimiter, 1)[0] + delimiter)
            else:
                contents.append((key, path.stat().st_size))
        parts = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">',
                 "<IsTruncated>false</IsTruncated>"]
        parts += [f"<Contents><Key>{k}</Key><Size>{s}</Size></Contents>" for k, s in contents]
        parts += [f"<CommonPrefixes><Prefix>{p}</Prefix></CommonPrefixes>" for p in sorted(common)]
        parts.append("</ListBucketResult>")
        self._send(200, "".join(parts).encode("utf-8"))


def _vhdr(data_file: str) -> str:
    lines = [
        "Brain Vision Data Exchange Header File Version 1.0", "",
        "[Common Infos]", f"DataFile={data_file}", "DataOrientation=MULTIPLEXED",
        f"NumberOfChannels={len(CHANNELS)}", f"SamplingInterval={int(1e6 / SFREQ)}", "",
        "[Binary Infos]", "BinaryFormat=IEEE_FLOAT_32", "", "[Channel Infos]",
    ]
    lines += [f"Ch{i + 1}={name},,1" for i, name in enumerate(CHANNELS)]
    return "\n".join(lines) + "\n"


def _write_dataset(root: Path, dataset_id: str, *, n_recordings: int = 3, duration_s: float = 20.0,
                   n_stim: int = 14, seed: int = 0) -> None:
    ds = root / dataset_id
    ds.mkdir(parents=True, exist_ok=True)
    (ds / "dataset_description.json").write_text(
        json.dumps({"Name": "synthetic", "License": "CC0", "BIDSVersion": "1.3.0"}), encoding="utf-8")
    rng = np.random.default_rng(seed)
    n = int(duration_s * SFREQ)
    t = np.arange(n) / SFREQ
    phases = np.linspace(0.0, 2.0 * np.pi, len(CHANNELS), endpoint=False)
    for i in range(n_recordings):
        sub = f"sub-{100 + i}"
        eeg_dir = ds / sub / "eeg"
        eeg_dir.mkdir(parents=True, exist_ok=True)
        base = f"{sub}_task-tmseeg1"
        data = 8.0 * np.sin(2 * np.pi * 10.0 * t[:, None] + phases[None, :])
        data += rng.normal(0.0, 2.0, size=(n, len(CHANNELS)))
        stim = np.sort(rng.choice(np.arange(2 * SFREQ, n - 2 * SFREQ), size=n_stim, replace=False))
        k = np.arange(300)
        for s in stim:
            data[s:s + 300, :] += 150.0 * np.exp(-k / 30.0)[:, None] * rng.choice([-1.0, 1.0], size=(1, len(CHANNELS)))
        (eeg_dir / f"{base}_eeg.eeg").write_bytes(data.astype("<f4").tobytes())
        (eeg_dir / f"{base}_eeg.vhdr").write_text(_vhdr(f"{base}_eeg.eeg"), encoding="utf-8")
        rows = ["onset\tduration\tsample\ttype\tvalue", "0\t0.0002\t1\tNew Segment\tn/a"]
        rows += [f"{s / SFREQ:.4f}\t0.0002\t{int(s) + 1}\tResponse\tR128" for s in stim]
        (eeg_dir / f"{base}_events.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")


@pytest.fixture
def served_dataset(tmp_path, monkeypatch):
    # Keep loopback traffic off any configured proxy.
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    root = tmp_path / "bucket"
    _write_dataset(root, "ds900001")
    handler = type("Handler", (_RangeHandler,), {"root": root})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/{BUCKET}", root
    finally:
        server.shutdown()
        server.server_close()


def _adapter(tmp_path: Path):
    from tools.data_access.approved_adapter import ApprovedAcquisitionAdapter

    return ApprovedAcquisitionAdapter(cache_root=tmp_path / "cache")


# ── header, events, licence ──────────────────────────────────────────────────

def test_header_accepts_multiplexed_float32_and_rejects_other_orientations():
    header = oc.parse_brainvision_header(_vhdr("x_eeg.eeg"))
    assert header.n_channels == len(CHANNELS)
    assert header.sfreq == pytest.approx(SFREQ)
    assert header.frame_bytes == len(CHANNELS) * 4
    bad = _vhdr("x_eeg.eeg").replace("MULTIPLEXED", "VECTORIZED")
    with pytest.raises(ValueError, match="unsupported DataOrientation"):
        oc.parse_brainvision_header(bad)


def test_header_rejects_path_components_in_data_file():
    with pytest.raises(ValueError, match="bare file name"):
        oc.parse_brainvision_header(_vhdr("../escape.eeg"))


def test_tms_onsets_are_one_based_and_fail_closed_without_stimuli():
    events = "onset\tduration\tsample\ttype\tvalue\n0\t0\t1\tNew Segment\tn/a\n1.0\t0\t5001\tResponse\tR128\n"
    assert oc.tms_onset_samples(events).tolist() == [5000]
    with pytest.raises(ValueError, match="no stimulus events"):
        oc.tms_onset_samples("onset\tduration\tsample\ttype\tvalue\n0\t0\t1\tNew Segment\tn/a\n")


@pytest.mark.parametrize(
    ("text", "state"),
    [
        ('{"License": "CC0"}', "open_cc0"),
        ('{"License": "CC-BY-4.0"}', "open_cc_by"),
        ('{"License": "CC-BY-NC-4.0"}', "unknown_blocked"),
        ('{"License": "Proprietary"}', "unknown_blocked"),
        ("not json", "unknown_blocked"),
    ],
)
def test_licence_mapping_keeps_unknown_licences_blocked(text, state):
    assert oc.license_state_from_description(text) == state


# ── statistics ───────────────────────────────────────────────────────────────

def test_auc_matches_sklearn_including_ties():
    from sklearn.metrics import roc_auc_score

    rng = np.random.default_rng(1)
    for _ in range(20):
        labels = rng.integers(0, 2, size=60)
        scores = np.round(rng.normal(size=60) + labels * 0.5, 1)  # forces ties
        assert oc.auc_score(labels, scores) == pytest.approx(roc_auc_score(labels, scores))


def test_sweep_offsets_exclude_the_artifact_window():
    offsets = oc.sweep_offsets((-200, 400), 10, (0, 50))
    assert offsets[0] == -200 and offsets[-1] == 400
    assert 0 not in offsets and 40 not in offsets and 50 in offsets
    assert len(offsets) == 56
    with pytest.raises(ValueError):
        oc.sweep_offsets((-200, 400), 0, (0, 50))


def test_heldout_selection_recovers_a_planted_offset_and_shuffle_null_is_calibrated():
    rng = np.random.default_rng(7)
    planted = 3
    recordings = []
    for _ in range(3):
        labels = np.repeat([1, 0], 40)
        scores = rng.normal(size=(80, 6))
        scores[:, planted] += labels * 2.5
        recordings.append((scores, labels))
    observed = oc.loso_heldout(recordings)
    assert observed["heldout_auc"] > 0.9  # expected ~0.96 for a 2.5 SD planted shift
    assert observed["selected_offset_index"] == [planted, planted, planted]
    null = oc.label_shuffle_null(recordings, n_shuffles=40, seed=2)
    assert oc.permutation_p_value(observed["heldout_auc"], null) <= 1.0 / 41 + 1e-12


def test_heldout_requires_three_recordings():
    labels = np.repeat([1, 0], 5)
    with pytest.raises(ValueError, match="at least 3"):
        oc.loso_heldout([(np.zeros((10, 2)), labels), (np.zeros((10, 2)), labels)])


# ── approved chunk path against the local range server ───────────────────────

def test_chunk_bytes_are_exact_and_the_chunk_is_deleted_after_consumption(tmp_path, served_dataset, monkeypatch):
    base_url, root = served_dataset
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    adapter = _adapter(tmp_path)
    reader = oc.ApprovedChunkReader(adapter, dataset_id="ds900001", base_url=base_url,
                                    allow_network=True, license_state="open_cc0")
    key = "sub-100/eeg/sub-100_task-tmseeg1_eeg.eeg"
    source = (root / "ds900001" / key).read_bytes()
    start, end = 1000 * len(CHANNELS) * 4, (1000 + 120) * len(CHANNELS) * 4 - 1
    chunk = reader.read_range(key=key, expected_size=len(source), start_byte=start, end_byte=end, chunk_index=0)
    assert chunk == source[start:end + 1]
    record = reader.records[-1]
    assert record.evicted is True
    assert oc.residual_cache_files(tmp_path / "cache") == []


def test_denied_network_fails_closed_without_any_transfer(tmp_path, served_dataset):
    base_url, root = served_dataset
    reader = oc.ApprovedChunkReader(_adapter(tmp_path), dataset_id="ds900001", base_url=base_url,
                                    allow_network=False, license_state="open_cc0")
    key = "sub-100/eeg/sub-100_task-tmseeg1_eeg.eeg"
    size = (root / "ds900001" / key).stat().st_size
    with pytest.raises(oc.ChunkAcquisitionError, match="NETWORK_DISABLED"):
        reader.read_range(key=key, expected_size=size, start_byte=0, end_byte=119, chunk_index=0)


def test_sweep_end_to_end_is_deterministic_and_leaves_no_chunks(tmp_path, served_dataset):
    base_url, _root = served_dataset
    kwargs = dict(dataset_id="ds900001", base_url=base_url, allow_network=True, max_recordings=3,
                  max_epochs_per_recording=5, n_shuffles=6, seed=3)
    first = oc.run_stimulus_sweep(adapter=_adapter(tmp_path / "a"), **kwargs)
    second = oc.run_stimulus_sweep(adapter=_adapter(tmp_path / "b"), **kwargs)
    m = first.metrics
    assert m["n_recordings"] == 3
    assert m["n_epochs_tms"] == 15 and m["n_epochs_control"] == 15
    assert m["chunks_consumed"] == 30 and m["chunks_evicted"] == 30
    assert m["residual_cache_files"] == 0
    # 1100 ms chunk at 5 kHz across 30 channels of float32 = 5500 frames * 120 bytes per chunk.
    assert m["bytes_transferred"] == 30 * 5500 * len(CHANNELS) * 4
    assert 0.0 <= m["heldout_auc"] <= 1.0
    assert 0.0 < m["p_value"] <= 1.0
    assert second.metrics["heldout_auc"] == m["heldout_auc"]
    assert second.metrics["p_value"] == m["p_value"]
    assert all(row["subject"] for row in first.epoch_rows)
    assert first.scope["license_state"] == "open_cc0"
    assert first.scope["transition_index_definition"] == oc.TRANSITION_INDEX_DEFINITION


def test_sweep_refuses_to_run_without_approved_network(tmp_path, served_dataset):
    base_url, _root = served_dataset
    with pytest.raises(PermissionError, match="not approved"):
        oc.run_stimulus_sweep(adapter=_adapter(tmp_path), dataset_id="ds900001", base_url=base_url,
                              allow_network=False, max_recordings=3, max_epochs_per_recording=2, n_shuffles=2)


# ── hypothesis dispatch for declared OpenNeuro data ──────────────────────────

REPO = Path(__file__).resolve().parents[1]


def _tms_spec(path: Path, dataset: str) -> Path:
    path.write_text(
        "id: HYP-TEST-003\nclaim_type: C\nlayer: Topology\n"
        "discriminator:\n  mode: stimulus_sweep\n  config:\n    sweep_range_ms: [-200, 400]\n    step_ms: 10\n"
        f"data:\n  mode: openneuro\n  dataset_id: {dataset}\n  params:\n    max_files: 50\n"
        "pass_fail:\n  criteria: test\n  thresholds:\n    auc_min: 0.65\n    p_max: 0.01\n    n_shuffles: 6\n",
        encoding="utf-8",
    )
    return path


def test_governed_openneuro_spec_runs_through_the_chunked_path(tmp_path, served_dataset, monkeypatch):
    from pipelines.hypothesis import run

    base_url, _root = served_dataset
    monkeypatch.setitem(oc.TASK_BY_DATASET, "ds900001", "tmseeg1")
    out = tmp_path / "out"
    summary = run(_tms_spec(tmp_path / "spec.yaml", "ds900001"), out, allow_network=True,
                  cache_root=tmp_path / "cache", max_recordings=3, max_epochs_per_recording=4,
                  source_base_url=base_url)
    assert summary["verdict"] in ("PASS", "FAIL"), summary
    assert summary["data_mode"] == "openneuro"
    assert summary["scope"]["declared_max_files"] == 50
    assert summary["metrics_summary"]["n_shuffles"] == 6
    record = json.loads((out / "RunRecord.json").read_text(encoding="utf-8"))
    assert record["data_mode"] == "openneuro" and record["dataset_id"] == "ds900001"
    manifest = json.loads((out / "acquisition_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["chunks"]) == 24
    assert all(chunk["evicted"] for chunk in manifest["chunks"])
    assert oc.residual_cache_files(tmp_path / "cache") == []


def test_openneuro_spec_without_approval_is_ambiguous_and_transfers_nothing(tmp_path, served_dataset, monkeypatch):
    from pipelines.hypothesis import run

    base_url, _root = served_dataset
    monkeypatch.setitem(oc.TASK_BY_DATASET, "ds900001", "tmseeg1")
    out = tmp_path / "out"
    summary = run(_tms_spec(tmp_path / "spec.yaml", "ds900001"), out, allow_network=False,
                  cache_root=tmp_path / "cache", source_base_url=base_url)
    assert summary["verdict"] == "ambiguous"
    assert "not approved" in summary["verdict_reason"]
    assert summary["data_mode"] is None
    assert oc.residual_cache_files(tmp_path / "cache") == []


def test_dataset_contrast_discriminator_stays_ambiguous_without_any_transfer(tmp_path):
    from pipelines.hypothesis import run

    summary = run(REPO / "governance" / "specs" / "HYP-20260506-002.yaml", tmp_path / "out", allow_network=True)
    assert summary["verdict"] == "ambiguous"
    assert "dataset_contrast" in summary["verdict_reason"]
    assert summary["data_mode"] is None


def test_bundled_stimulus_spec_without_approval_is_ambiguous(tmp_path):
    from pipelines.hypothesis import run

    summary = run(REPO / "governance" / "specs" / "HYP-20260506-003.yaml", tmp_path / "out", allow_network=False)
    assert summary["verdict"] == "ambiguous"
    assert "not approved" in summary["verdict_reason"]


def test_auc_threshold_is_not_evaluable_on_synthetic_data(tmp_path):
    from pipelines.hypothesis import run

    spec = tmp_path / "spec.yaml"
    spec.write_text("spec_id: SYN-AUC\nthreshold:\n  auc_min: 0.5\nsim_params:\n  N: 8\n  n_steps: 3\n  seed: 1\n",
                    encoding="utf-8")
    summary = run(spec, tmp_path / "out")
    assert summary["verdict"] == "ambiguous"
    assert "cannot be evaluated on synthetic data" in summary["verdict_reason"]


# ── transition-index readout: exact zeros and grid values ────────────────────

def _plane_wave_epoch(n_samples: int = 5500) -> np.ndarray:
    """A spatially uniform phase gradient has no windings anywhere, so the index must be exactly zero."""
    t = np.arange(n_samples) / SFREQ
    phase_offsets = np.linspace(0.0, 2.0 * np.pi, len(CHANNELS), endpoint=False)
    return 10.0 * np.sin(2 * np.pi * 10.0 * t[None, :] + phase_offsets[:, None])


def _epoch_geometry():
    names, xy, triangles, index = oc._geometry(tuple(CHANNELS), SFREQ)
    return xy, triangles, index


def test_transition_index_is_exactly_zero_without_topological_change():
    xy, triangles, index = _epoch_geometry()
    samples = _plane_wave_epoch()[index, :]
    offsets = oc.sweep_offsets((-200, 400), 10, (0, 50))
    values = oc.transition_index_vector(samples, sfreq=SFREQ, xy=xy, triangles=triangles,
                                        onset_index=2500, offsets_ms=offsets)
    assert values.shape == (len(offsets),)
    assert np.all(values == 0.0)  # exact, not merely small


def test_transition_index_values_lie_on_the_integer_winding_grid():
    xy, triangles, index = _epoch_geometry()
    rng = np.random.default_rng(11)
    samples = rng.normal(size=(len(CHANNELS), 5500)) * 100.0
    offsets = oc.sweep_offsets((-200, 400), 10, (0, 50))
    values = oc.transition_index_vector(samples[index, :], sfreq=SFREQ, xy=xy, triangles=triangles,
                                        onset_index=2500, offsets_ms=offsets)
    scaled = values * 51.0
    assert np.max(np.abs(scaled - np.round(scaled))) < 1e-9
