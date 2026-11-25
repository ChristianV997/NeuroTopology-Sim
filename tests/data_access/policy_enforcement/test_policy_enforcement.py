"""Tests for the read-only data-access policy scanner."""

from __future__ import annotations

import json
import socket
from pathlib import Path

from tools.data_access.policy_enforcement.paths import check_path_containment
from tools.data_access.policy_enforcement.policy import (
    APPROVED_ACQUISITION_ADAPTERS,
    APPROVED_METADATA_OPERATIONS,
    DEFAULT_POLICY,
    DataAccessPolicy,
    POLICY_REGISTRATION_REQUIREMENTS,
    PR346_BOUNDED_ADAPTER_REGISTRATIONS,
)
from tools.data_access.policy_enforcement.scanner import scan_file, scan_repository


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _custom_policy() -> DataAccessPolicy:
    return DataAccessPolicy(
        reviewed_exceptions={},
        approved_adapters=(
            {"path": "tests/data_access/policy_enforcement/fixtures/approved_bounded.py", "symbols": ["bounded_transfer"], "access_class": "bounded"},
        ),
        approved_metadata_operations=(
            {"path": "tests/data_access/policy_enforcement/fixtures/approved_metadata.py", "symbol": "metadata_inventory", "operations": ["HEAD"]},
        ),
    )


def _rules(findings):
    return {finding.rule for finding in findings}


def test_approved_metadata_and_bounded_patterns_are_allowlisted():
    policy = _custom_policy()
    assert scan_file(FIXTURES / "approved_metadata.py", repository_root=ROOT, policy=policy) == []
    assert scan_file(FIXTURES / "approved_bounded.py", repository_root=ROOT, policy=policy) == []


def test_pr346_registration_uses_exact_paths_and_qualified_symbols():
    assert POLICY_REGISTRATION_REQUIREMENTS["owner"] == "tools/data_access/policy_enforcement"
    assert POLICY_REGISTRATION_REQUIREMENTS["schema_version"].endswith("Registration.v1")
    registrations = {item["path"]: item for item in PR346_BOUNDED_ADAPTER_REGISTRATIONS}
    assert set(registrations) == {
        "validation/s3_fetchers.py",
        "tools/stream_process_ds005917.py",
        "tools/stream_process_ds006644.py",
    }
    assert registrations["validation/s3_fetchers.py"]["symbols"] == [
        "BoundedS3ObjectStore.fetch_object",
        "BoundedS3ObjectStore.read_text_metadata",
    ]
    assert registrations["validation/s3_fetchers.py"]["control_profile"] == "s3_store"
    assert "explicit allow_network=False" in registrations["validation/s3_fetchers.py"]["requirements"]
    assert "explicit source object identity" in registrations["validation/s3_fetchers.py"]["requirements"]
    assert "head_object ContentLength expected size" in registrations["validation/s3_fetchers.py"]["requirements"]
    assert "observable eviction" in registrations["validation/s3_fetchers.py"]["requirements"]


def test_registered_s3_method_requires_structural_controls(tmp_path: Path):
    source = '''
class BoundedS3ObjectStore:
    def __init__(self, client, max_cache_bytes):
        self.client = client
        self.max_cache_bytes = max_cache_bytes

    def _contained(self, destination):
        return destination

    def _object_uri(self, bucket, key):
        return "s3://" + bucket + "/" + key

    def _evict_for(self, required, *, protected):
        return None

    def _head(self, bucket, key, *, allow_network):
        metadata = self.client.head_object(Bucket=bucket, Key=key)
        return {"size": metadata["ContentLength"], "checksum": metadata.get("ChecksumSHA256") or "unknown"}

    def fetch_object(self, bucket, key, destination, *, allow_network=False):
        source_uri = self._object_uri(bucket, key)
        metadata = self._head(bucket, key, allow_network=allow_network)
        destination = self._contained(destination)
        part_path = destination.with_name("payload.part")
        self._evict_for(metadata["size"], protected=destination)
        response = self.client.get_object(Bucket=bucket, Key=key, Range="bytes=0-1")
        os.replace(part_path, destination)
        return response, metadata["checksum"]
'''
    path = tmp_path / "validation" / "s3_fetchers.py"
    path.parent.mkdir()
    path.write_text(source, encoding="utf-8")
    policy = DataAccessPolicy(
        approved_adapters=(
            {
                "path": "validation/s3_fetchers.py",
                "symbols": ["BoundedS3ObjectStore.fetch_object"],
                "access_class": "manifest_first_bounded_s3_range",
                "registration": "test",
                "control_profile": "s3_store",
            },
        ),
    )
    assert scan_file(path, repository_root=tmp_path, policy=policy) == []


def test_same_basename_in_unregistered_class_is_not_approved(tmp_path: Path):
    path = tmp_path / "validation" / "s3_fetchers.py"
    path.parent.mkdir()
    path.write_text(
        """
class OtherStore:
    def fetch_object(self, bucket, key, destination, *, allow_network=False):
        return self.client.get_object(Bucket=bucket, Key=key)
""",
        encoding="utf-8",
    )
    policy = DataAccessPolicy(
        approved_adapters=(
            {
                "path": "validation/s3_fetchers.py",
                "symbols": ["BoundedS3ObjectStore.fetch_object"],
                "access_class": "manifest_first_bounded_s3_range",
                "registration": "test",
                "control_profile": "s3_store",
            },
        ),
    )
    rules = _rules(scan_file(path, repository_root=tmp_path, policy=policy))
    assert "UNBOUNDED_REMOTE_MATERIALIZATION" in rules
    assert "MISSING_CHECKSUM" in rules
    assert "MISSING_EVICTION" in rules


def test_delegated_pr346_wrapper_requires_explicit_bounds_and_opt_in(tmp_path: Path):
    path = tmp_path / "tools" / "stream_process_ds005917.py"
    path.parent.mkdir()
    path.write_text(
        """
def download_bold(subject, destination, *, allow_network=False, max_cache_bytes=1024, chunk_size=128):
    store = BoundedS3ObjectStore(client, destination, max_cache_bytes=max_cache_bytes, chunk_size=chunk_size)
    return store.fetch_object("bucket", subject, destination, allow_network=allow_network)
""",
        encoding="utf-8",
    )
    policy = DataAccessPolicy(
        approved_adapters=(
            {
                "path": "tools/stream_process_ds005917.py",
                "symbols": ["download_bold"],
                "access_class": "delegated_bounded_s3_range",
                "registration": "test",
                "control_profile": "delegated_s3_wrapper",
            },
        ),
    )
    assert scan_file(path, repository_root=tmp_path, policy=policy) == []


def test_delegated_metadata_wrapper_accepts_metadata_byte_bound(tmp_path: Path):
    path = tmp_path / "tools" / "stream_process_ds005917.py"
    path.parent.mkdir()
    path.write_text(
        """
def load_mdd_complete_subjects(*, metadata_cache_root=None, allow_network=False):
    store = BoundedS3ObjectStore(client, metadata_cache_root, metadata_max_bytes=4096)
    return store.read_text_metadata("bucket", "participants.tsv", allow_network=allow_network)
""",
        encoding="utf-8",
    )
    policy = DataAccessPolicy(
        approved_adapters=(
            {
                "path": "tools/stream_process_ds005917.py",
                "symbols": ["load_mdd_complete_subjects"],
                "access_class": "delegated_bounded_s3_range",
                "registration": "test",
                "control_profile": "delegated_s3_wrapper",
            },
        ),
    )
    assert scan_file(path, repository_root=tmp_path, policy=policy) == []


def test_registered_method_without_checksum_or_eviction_is_not_approved(tmp_path: Path):
    path = tmp_path / "validation" / "s3_fetchers.py"
    path.parent.mkdir()
    path.write_text(
        """
class BoundedS3ObjectStore:
    def fetch_object(self, bucket, key, destination, *, allow_network=False):
        response = self.client.get_object(Bucket=bucket, Key=key, Range="bytes=0-1")
        return response
""",
        encoding="utf-8",
    )
    policy = DataAccessPolicy(
        approved_adapters=(
            {
                "path": "validation/s3_fetchers.py",
                "symbols": ["BoundedS3ObjectStore.fetch_object"],
                "access_class": "manifest_first_bounded_s3_range",
                "registration": "test",
                "control_profile": "s3_store",
            },
        ),
    )
    findings = scan_file(path, repository_root=tmp_path, policy=policy)
    rules = _rules(findings)
    assert "MISSING_CHECKSUM" in rules
    assert "MISSING_EVICTION" in rules


def test_registered_s3_symbol_cannot_hide_full_object_call(tmp_path: Path):
    path = tmp_path / "validation" / "s3_fetchers.py"
    path.parent.mkdir()
    path.write_text(
        """
class BoundedS3ObjectStore:
    def _object_uri(self, bucket, key):
        return "s3://" + bucket + "/" + key

    def _contained(self, destination):
        return destination

    def _evict_for(self, required, *, protected):
        return None

    def _head(self, bucket, key, *, allow_network):
        metadata = self.client.head_object(Bucket=bucket, Key=key)
        return {"size": metadata["ContentLength"], "checksum": metadata.get("ChecksumSHA256") or "unknown"}

    def fetch_object(self, bucket, key, destination, *, allow_network=False):
        source_uri = self._object_uri(bucket, key)
        metadata = self._head(bucket, key, allow_network=allow_network)
        destination = self._contained(destination)
        self._evict_for(metadata["size"], protected=destination)
        self.client.download_file(bucket, key, str(destination))
        return source_uri, metadata["checksum"]
""",
        encoding="utf-8",
    )
    policy = DataAccessPolicy(
        approved_adapters=(
            {
                "path": "validation/s3_fetchers.py",
                "symbols": ["BoundedS3ObjectStore.fetch_object"],
                "access_class": "manifest_first_bounded_s3_range",
                "registration": "test",
                "control_profile": "s3_store",
            },
        ),
    )
    rules = _rules(scan_file(path, repository_root=tmp_path, policy=policy))
    assert "UNBOUNDED_REMOTE_MATERIALIZATION" in rules


def test_path_only_allowlist_does_not_approve_unrelated_http_caller(tmp_path: Path):
    path = tmp_path / "validation" / "s3_fetchers.py"
    path.parent.mkdir()
    path.write_text(
        """
import urllib.request

def unrelated_reader(url):
    return urllib.request.urlopen(url, timeout=1)
""",
        encoding="utf-8",
    )
    findings = scan_file(path, repository_root=tmp_path)
    assert any(item.rule == "UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL" for item in findings)


def test_rejected_download_patterns_report_exact_lines_and_remediation():
    findings = scan_file(FIXTURES / "rejected_downloads.py", repository_root=ROOT)
    rules = _rules(findings)
    assert "UNAUTHORIZED_BOTO3_FULL_OBJECT" in rules
    assert "UNAUTHORIZED_AWS_FULL_TRANSFER" in rules
    assert "UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL" in rules
    assert all(finding.file.endswith("rejected_downloads.py") and finding.line > 0 for finding in findings)
    assert all(finding.remediation for finding in findings)


def test_openneuro_download_is_critical_and_unapproved():
    findings = scan_file(FIXTURES / "rejected_openneuro.py", repository_root=ROOT)
    finding = next(item for item in findings if item.rule == "UNAUTHORIZED_OPENNEURO_DOWNLOAD")
    assert finding.severity == "critical"
    assert finding.approved is False


def test_missing_runtime_controls_fail_closed():
    findings = scan_file(FIXTURES / "rejected_controls.py", repository_root=ROOT)
    rules = _rules(findings)
    assert {"OUTPUT_ROOT_ESCAPE", "MISSING_CACHE_BOUND", "MISSING_CHECKSUM", "MISSING_EVICTION", "NETWORK_ENABLED_BY_DEFAULT"} <= rules


def test_missing_checksum_is_explicitly_unknown_not_approved():
    findings = scan_file(FIXTURES / "rejected_controls.py", repository_root=ROOT)
    checksum = next(item for item in findings if item.rule == "MISSING_CHECKSUM")
    assert checksum.approved is False
    assert "unknown" in checksum.remediation.lower()


def test_dandi_lazy_reader_and_manifest_metadata_are_explicitly_allowlisted():
    findings = scan_file(ROOT / "data" / "dandi_nwb_ingest.py", repository_root=ROOT)
    assert findings == []


def test_local_cache_helper_is_not_misclassified_as_remote_transfer(tmp_path):
    local = tmp_path / "local_cache.py"
    local.write_text(
        """
def read_raw_cached(path, cache):
    cached = cache.get(path)
    if cached is not None:
        return cached
    value = open(path, 'rb').read()
    cache[path] = value
    return value
""",
        encoding="utf-8",
    )
    assert scan_file(local, repository_root=tmp_path) == []


def test_shell_entrypoint_patterns_are_scanned_without_execution(tmp_path):
    shell = tmp_path / "legacy.sh"
    shell.write_text("aws s3 sync s3://bucket/data ./data\ncurl https://example.invalid/data\n", encoding="utf-8")
    findings = scan_file(shell, repository_root=ROOT)
    assert {item.rule for item in findings} == {"UNAUTHORIZED_AWS_FULL_TRANSFER", "UNAUTHORIZED_SHELL_TRANSFER"}


def test_unparseable_production_file_fails_closed(tmp_path):
    malformed = tmp_path / "malformed.py"
    malformed.write_text("def broken(:\n    return None\n", encoding="utf-8")
    findings = scan_file(malformed, repository_root=ROOT)
    assert any(item.rule == "POLICY_PARSE_FAILURE" and item.severity == "critical" for item in findings)


def test_reviewed_exception_is_explicit_and_suppresses_only_matching_rule():
    policy = DataAccessPolicy(
        reviewed_exceptions={
            "tests/data_access/policy_enforcement/fixtures/rejected_openneuro.py": {
                "rule": "UNAUTHORIZED_OPENNEURO_DOWNLOAD",
                "reviewer": "fixture-review",
                "justification": "fixture-only negative test",
            }
        }
    )
    findings = scan_file(FIXTURES / "rejected_openneuro.py", repository_root=ROOT, policy=policy)
    assert "UNAUTHORIZED_OPENNEURO_DOWNLOAD" not in _rules(findings)


def test_repository_scan_emits_migration_inventory_for_legacy_callers():
    report = scan_repository(
        ROOT,
        paths=[
            "tools/streaming/base_runner.py",
            "scripts/eeg_topology_ds005620.py",
            "scripts/fetch_real_datasets.py",
        ],
    )
    assert report.compliant is False
    assert report.findings
    assert report.migration_inventory
    assert report.to_dict()["legacy_violation_count"] > 0
    assert report.network_calls_performed is False


def test_policy_represents_safe_runtime_requirements():
    data = DEFAULT_POLICY.to_dict()
    assert data["network_enabled_by_default"] is False
    assert data["manifest_required_before_data"] is True
    assert data["bounded_transfer_required"] is True
    assert "checksum" in data["checksum_policy"]
    assert "partial" in data["partial_transfer_policy"]
    assert "retry" in data["retry_policy"]
    assert "eviction" in data["eviction_policy"]
    assert APPROVED_ACQUISITION_ADAPTERS
    assert APPROVED_METADATA_OPERATIONS
    assert data["approved_lazy_readers"]


def test_windows_and_posix_path_containment():
    windows_ok = check_path_containment(r"C:\cache\root", r"C:\cache\root\dataset\part.bin")
    windows_escape = check_path_containment(r"C:\cache\root", r"C:\cache\other\part.bin")
    posix_ok = check_path_containment("/var/cache/data", "/var/cache/data/dataset/part.bin")
    posix_escape = check_path_containment("/var/cache/data", "/var/cache/data/../secret")
    assert windows_ok.contained is True
    assert windows_escape.contained is False
    assert posix_ok.contained is True
    assert posix_escape.contained is False


def test_path_containment_rejects_root_and_cross_drive():
    assert check_path_containment(r"C:\cache", r"C:\cache").contained is False
    assert check_path_containment(r"C:\cache", r"D:\cache\x").contained is False


def test_scanner_is_deterministic_finite_and_no_network(monkeypatch):
    def fail_socket(*args, **kwargs):
        raise AssertionError("scanner must not contact the network")

    monkeypatch.setattr(socket, "socket", fail_socket)
    first = scan_repository(ROOT, paths=["tests/data_access/policy_enforcement/fixtures/rejected_downloads.py"])
    second = scan_repository(ROOT, paths=["tests/data_access/policy_enforcement/fixtures/rejected_downloads.py"])
    assert first.to_json() == second.to_json()
    payload = json.loads(first.to_json())
    assert all(value is not None for value in [payload["finding_count"], payload["legacy_violation_count"]])
    json.dumps(payload, allow_nan=False)


def test_report_contains_no_network_calls_and_explicit_cache_policy():
    report = scan_repository(ROOT, paths=["tools/data_access/chunk_cache/transfer.py"])
    assert report.network_calls_performed is False
    assert report.policy.cache_root_policy == "explicit_and_contained"
    assert report.policy.output_root_policy == "explicit_and_contained"
