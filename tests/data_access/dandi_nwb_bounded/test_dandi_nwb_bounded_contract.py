"""Hermetic bounded DANDI/NWB contract tests (owned path).

Never contacts DANDI, AWS, or other remote services. Engineering integrity
only — not empirical or biological evidence.
"""
from __future__ import annotations

import hashlib
import json
import math
import py_compile
import subprocess
import sys
from pathlib import Path

import pytest

from data.dandi_nwb_ingest import (
    IngestionContractError,
    IngestionState,
    LocalFileWindowSource,
    LocalMetadataSource,
    ManagedNwbHandle,
    Provenance,
    WindowCache,
    WindowRequest,
    checksum_status,
    inspect_metadata,
    open_nwb_lazy,
    read_bounded_window,
    reject_full_object_materialization,
    reject_full_recording_materialization,
    release_window,
    require_output_root,
    resolve_asset_blobs,
    resolve_under_root,
)
from tools import stream_process_dandi000458 as stream

REPO_ROOT = Path(__file__).resolve().parents[3]
OWNED_PREFIXES = (
    "data/dandi_nwb_ingest.py",
    "tools/stream_process_dandi000458.py",
    "tests/data_access/dandi_nwb_bounded/",
    "docs/data_access/dandi_nwb_bounded.md",
    "tools/stream_pitnn_cohort_ds005620.py",
    "tests/test_pitnn_cohort_ds005620.py",
    "tools/streaming/",
    "tests/streaming/",
    "tests/performance/streaming_optimization/",
)
PROTECTED_PREFIXES = (
    "data/bids_ingest.py",
    "tools/data_access/policy_enforcement/",
    "apps/awareness_studio/",
)



def _provenance(**kwargs):
    values = dict(
        dataset_identity="fixture-ds",
        object_identity="run-01",
        source_kind="local_fixture",
        source_uri="fixture://run-01",
        synthetic=True,
    )
    values.update(kwargs)
    return Provenance(**values)


def _request(size=8, **kwargs):
    values = dict(
        provenance=_provenance(),
        start=0,
        stop=size,
        unit="bytes",
        expected_size=size,
        checksum_policy="sha256",
        expected_checksum=None,
        cache_budget_bytes=64,
        consumer_lease="consumer-a",
        eviction_policy="release_after_final_consumer",
        network_permission=False,
    )
    values.update(kwargs)
    return WindowRequest(**values)


class FakeSource:
    def __init__(self, payload=b"abcdefgh", *, source_size=8, failures=0, short=False, interrupt=False):
        self.payload = payload
        self.source_size = source_size
        self.failures = failures
        self.short = short
        self.interrupt = interrupt
        self.calls = 0
        self.closed = 0

    def size(self, request):
        return self.source_size

    def read_window(self, request):
        self.calls += 1
        if self.interrupt:
            raise InterruptedError("fixture interruption")
        if self.calls <= self.failures:
            raise OSError("transient fixture failure")
        return self.payload[:-1] if self.short else self.payload

    def close(self):
        self.closed += 1


def test_bounded_window_read():
    source = FakeSource()
    result = read_bounded_window(source, _request(expected_checksum=hashlib.sha256(b"abcdefgh").hexdigest()))
    assert result.state is IngestionState.COMPLETE
    assert result.data == b"abcdefgh"
    assert result.checksum_status == "verified"
    assert source.closed == 1


def test_full_materialization_rejection():
    with pytest.raises(IngestionContractError, match="full-recording"):
        reject_full_recording_materialization()
    with pytest.raises(IngestionContractError, match="full-recording"):
        reject_full_object_materialization()


def test_network_disabled_default():
    with pytest.raises(IngestionContractError, match="explicit network permission"):
        open_nwb_lazy("https://example.invalid/object.nwb")
    with pytest.raises(IngestionContractError, match="explicit network permission"):
        resolve_asset_blobs("000458", "0.230317.0039")
    with pytest.raises(IngestionContractError, match="explicit network permission"):
        stream.run(str(REPO_ROOT / "outputs" / "tmp"), 1.0, 1, 2, None, None, output_root=str(REPO_ROOT / "outputs"))


def test_explicit_opt_in_required_for_remote_window():
    remote = _request(
        provenance=_provenance(
            source_kind="dandi_nwb",
            source_uri="https://example.invalid/object",
            validated_dandi_nwb=True,
            synthetic=False,
        ),
        network_permission=False,
    )
    result = read_bounded_window(FakeSource(), remote)
    assert result.state is IngestionState.BLOCKED
    assert "permission" in (result.error or "").lower()


def test_open_nwb_lazy_rejects_unsupported_schemes():
    with pytest.raises(IngestionContractError, match="unsupported|scheme"):
        open_nwb_lazy("ftp://dandiarchive.org/file.nwb", network_permission=True)
    with pytest.raises(IngestionContractError, match="unsupported|scheme"):
        open_nwb_lazy("gcs://bucket/file.nwb", network_permission=True)


def test_read_bounded_window_rejects_negative_retries():
    req = _request()
    with pytest.raises(ValueError, match="non-negative"):
        read_bounded_window(FakeSource(), req, max_retries=-1)



def test_missing_identity_blocked():
    incomplete = _request(provenance=Provenance("", "obj", "local_fixture", "fixture://x", synthetic=True))
    result = read_bounded_window(FakeSource(), incomplete)
    assert result.state is IngestionState.BLOCKED
    assert "provenance" in (result.error or "").lower() or "incomplete" in (result.error or "").lower()


def test_unknown_checksum_preserved():
    assert checksum_status(expected_checksum=None, observed_checksum="a" * 64) == "unknown"
    result = read_bounded_window(FakeSource(), _request(expected_checksum=None))
    assert result.state is IngestionState.COMPLETE
    assert result.checksum_status == "unknown"
    assert result.to_dict()["checksum_status"] == "unknown"
    # Computed digest may be present, but verification is never fabricated.
    assert result.checksum == hashlib.sha256(b"abcdefgh").hexdigest()


def test_checksum_mismatch():
    result = read_bounded_window(FakeSource(), _request(expected_checksum="0" * 64))
    assert result.state is IngestionState.FAILED
    assert result.checksum is None
    assert result.checksum_status == "mismatch"
    assert result.to_dict()["checksum"] is None
    assert result.to_dict()["checksum_status"] == "mismatch"


def test_output_escape_rejected(tmp_path):
    root = tmp_path / "outputs"
    root.mkdir()
    with pytest.raises(IngestionContractError, match="inside output_root"):
        require_output_root(str(root), str(tmp_path / "outside"))
    with pytest.raises(IngestionContractError, match="relative|escape"):
        resolve_under_root(root, "../escape.bin")
    with pytest.raises(IngestionContractError, match="output_root is required"):
        require_output_root(None, str(root / "run"))


def test_handle_closure(tmp_path):
    path = tmp_path / "fixture.bin"
    path.write_bytes(b"0123456789")
    source = LocalFileWindowSource(path)
    result = read_bounded_window(source, _request(size=4, stop=4, expected_size=4, checksum_policy="none"))
    assert result.state is IngestionState.COMPLETE
    assert source.closed == 1

    class _DummyH5:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

        def __getitem__(self, key):
            raise KeyError(key)

    class _DummyRemote:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    h5 = _DummyH5()
    remote = _DummyRemote()
    handle = ManagedNwbHandle(h5, remote_file=remote)
    with handle as opened:
        assert opened is h5
    assert handle.closed is True
    assert h5.closed is True
    assert remote.closed is True


def test_lease_release_and_eviction():
    cache = WindowCache(8)
    first = read_bounded_window(FakeSource(), _request(consumer_lease="a"), cache=cache)
    assert cache.current_bytes == 8
    blocked = read_bounded_window(
        FakeSource(),
        _request(consumer_lease="b", provenance=_provenance(object_identity="run-02")),
        cache=cache,
    )
    assert blocked.state is IngestionState.BLOCKED
    assert release_window(cache, first, final_consumer=True)
    assert cache.current_bytes == 0
    second = read_bounded_window(
        FakeSource(),
        _request(consumer_lease="b", provenance=_provenance(object_identity="run-02")),
        cache=cache,
    )
    assert second.state is IngestionState.COMPLETE


def test_interrupted_read_recovery():
    interrupted = read_bounded_window(FakeSource(interrupt=True), _request())
    assert interrupted.state is IngestionState.PARTIAL
    assert interrupted.resume_from == 0
    assert interrupted.checksum_status == "unknown"
    recovered = read_bounded_window(FakeSource(failures=1), _request(), max_retries=1)
    assert recovered.state is IngestionState.COMPLETE
    assert recovered.attempts == 2


def test_finite_json():
    result = read_bounded_window(FakeSource(), _request())
    payload = result.to_dict()
    encoded = json.dumps(payload, allow_nan=False, sort_keys=True)
    assert "NaN" not in encoded and "Infinity" not in encoded
    for value in payload.values():
        if isinstance(value, float):
            assert math.isfinite(value)


def test_filesystem_fallback_rejected():
    fallback = _request(
        provenance=_provenance(source_kind="filesystem_fallback", validated_dandi_nwb=True, synthetic=False)
    )
    result = read_bounded_window(FakeSource(), fallback)
    assert result.state is IngestionState.BLOCKED
    assert "fallback" in (result.error or "").lower()


def test_metadata_preserves_known_fields_without_fabrication(tmp_path):
    metadata = tmp_path / "metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "sampling_rate_hz": 250.0,
                "timestamp_unit": "seconds",
                "units": "volts",
                "channel_identity": ["Cz", "Pz"],
                "montage": "standard_1020",
                "source_series": "ElectricalSeriesEEG",
            }
        ),
        encoding="utf-8",
    )
    result = inspect_metadata(LocalMetadataSource(metadata), "ds", "obj")
    assert result["state"] == "METADATA_ONLY"
    assert result["metadata"]["sampling_rate_hz"] == 250.0
    assert result["metadata"]["channel_identity"] == ["Cz", "Pz"]
    assert result["metadata"]["montage"] == "standard_1020"


def test_stream_processor_output_escape(tmp_path, monkeypatch):
    monkeypatch.setattr(stream, "resolve_asset_blobs", lambda *_a, **_k: pytest.fail("no network"))
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


def test_stream_processor_unknown_checksum_not_fabricated():
    from data.dandi_nwb_ingest import DandiAsset

    asset = DandiAsset("000458", "0.230317.0039", "sub-01/x.nwb", "sub-01", "https://example.invalid/x", 128, None)
    contract = stream._access_contract(asset, allow_network=True)
    body = contract.to_dict()
    assert body["checksum_status"] == "unknown"
    assert body["expected_checksum"] is None


def test_owned_python_compiles():
    files = [
        REPO_ROOT / "data" / "dandi_nwb_ingest.py",
        REPO_ROOT / "tools" / "stream_process_dandi000458.py",
        *sorted((REPO_ROOT / "tests" / "data_access" / "dandi_nwb_bounded").rglob("*.py")),
    ]
    errors = []
    for path in files:
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(str(exc))
    assert errors == []


def test_governance_validate():
    completed = subprocess.run(
        [sys.executable, "-m", "governance.validate"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_git_diff_check():
    rels = list(OWNED_PREFIXES)
    completed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--check", "--", *rels],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_preserve_owned_paths_only():
    completed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "diff", "--name-only", "origin/main", "--"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    changed = [line.strip() for line in completed.stdout.splitlines() if line.strip()]

    def owned(rel: str) -> bool:
        return any(rel == prefix or rel.startswith(prefix) for prefix in OWNED_PREFIXES)

    leaked = [path for path in changed if not owned(path)]
    assert leaked == [], f"non-owned paths changed: {leaked}"
    protected = [path for path in changed if any(path.startswith(p) for p in PROTECTED_PREFIXES)]
    assert protected == [], f"protected paths changed: {protected}"
