"""S3 listing and atomic partial-file transfer behaviour (fully mocked)."""
from __future__ import annotations

from pathlib import Path

from tools.streaming import base_runner

from tests.performance.streaming_optimization.conftest import FakePaginator, FakeS3Client


def test_task_label_listing_stops_after_max_subjects(fake_s3_modules):
    prefixes = [{"Prefix": f"dsX/sub-{i:02d}/"} for i in range(1, 21)]

    def handler(kwargs):
        prefix = kwargs.get("Prefix", "")
        if kwargs.get("Delimiter") == "/":
            return [{"CommonPrefixes": prefixes}]
        # Per-subject object listing
        subject = prefix.rstrip("/").split("/")[-1]
        return [{"Contents": [{"Key": f"dsX/{subject}/eeg/{subject}_task-awake_eeg.edf"}]}]

    paginator = FakePaginator(handler)
    fake_s3_modules["client"] = FakeS3Client(paginator)
    labels = base_runner.list_s3_task_labels("openneuro.org", "dsX", max_subjects=3)
    assert labels == ["awake"]
    prefix_scans = [c for c in paginator.calls if c.get("Delimiter") == "/"]
    assert len(prefix_scans) == 1
    subject_scans = [c for c in paginator.calls if c.get("Delimiter") != "/"]
    assert len(subject_scans) == 3
    scanned_subjects = [c["Prefix"].rstrip("/").split("/")[-1] for c in subject_scans]
    assert scanned_subjects == ["sub-01", "sub-02", "sub-03"]


def test_empty_download_batches_do_not_spawn_a_pool(tmp_path, fake_s3_modules, monkeypatch):
    spawned = {"n": 0}
    real_pool = base_runner.ThreadPoolExecutor

    class CountingPool(real_pool):
        def __init__(self, *args, **kwargs):
            spawned["n"] += 1
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(base_runner, "ThreadPoolExecutor", CountingPool)

    def handler(kwargs):
        return [{"Contents": []}]

    fake_s3_modules["client"] = FakeS3Client(FakePaginator(handler))
    dest = base_runner.sync_s3_subject("openneuro.org", "dsX", "sub-01", tmp_path)
    assert dest == tmp_path / "sub-01"
    assert spawned["n"] == 0


def test_atomic_partial_is_not_promoted_and_stale_part_is_dropped(
    tmp_path, fake_s3_modules
):
    dest_root = tmp_path / "work"
    subject = "sub-01"
    key = f"dsX/{subject}/file.bin"
    target = dest_root / subject / "file.bin"
    target.parent.mkdir(parents=True, exist_ok=True)
    stale = target.with_name(target.name + ".part")
    stale.write_bytes(b"NO")  # truncated leftover must not be treated as complete

    attempts = {"n": 0}

    def download_impl(bucket, key, filename, Config=None):
        attempts["n"] += 1
        assert filename.endswith(".part")
        Path(filename).write_bytes(b"DATA")

    def handler(kwargs):
        return [{"Contents": [{"Key": key, "Size": 4}]}]

    fake_s3_modules["client"] = FakeS3Client(FakePaginator(handler), download_impl=download_impl)
    dest = base_runner.sync_s3_subject("openneuro.org", "dsX", subject, dest_root)
    assert dest == dest_root / subject
    assert target.read_bytes() == b"DATA"
    assert not stale.exists()
    assert attempts["n"] == 1


def test_matching_size_reuses_existing_file_without_redownload(tmp_path, fake_s3_modules):
    dest_root = tmp_path / "work"
    subject = "sub-01"
    key = f"dsX/{subject}/file.bin"
    target = dest_root / subject / "file.bin"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"DATA")

    def download_impl(bucket, key, filename, Config=None):
        raise AssertionError("must not re-transfer a complete object")

    def handler(kwargs):
        return [{"Contents": [{"Key": key, "Size": 4}]}]

    fake_s3_modules["client"] = FakeS3Client(FakePaginator(handler), download_impl=download_impl)
    base_runner.sync_s3_subject("openneuro.org", "dsX", subject, dest_root)
    assert target.read_bytes() == b"DATA"
