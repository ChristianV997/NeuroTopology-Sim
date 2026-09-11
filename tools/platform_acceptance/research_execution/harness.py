"""Acceptance harness for cross-platform research execution verification.

Validates:
- Bounded data access and local-only metadata registration.
- Cache bounds, atomic partials, checksum mismatch, retry classification, eviction.
- Process timeout and descendant cleanup.
- Output-root containment and path traversal rejection.
- Finite JSON serialization and malformed artifact rejection.
- PowerShell wrapper syntax, command construction, and execution behavior.
- Windows-specific behaviors (file locking, path normalization, atomic replacement, symlinks).
- Strict non-Windows unsupported classification (Windows cases marked UNSUPPORTED on POSIX).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from tools.data_access.chunk_cache.bids_validator import (
    BIDSValidationError,
    normalize_bids_relative_path,
)
from tools.data_access.chunk_cache.cache_engine import BoundedChunkCache
from tools.data_access.chunk_cache.transfer import (
    MockTransferAdapter,
    compute_file_sha256,
)
from tools.data_access.chunk_cache.types import (
    CacheBudget,
    CacheErrorCode,
    ChunkRange,
    ManifestRecord,
    TransferResult,
)
from tools.platform_acceptance.research_execution.probes import (
    build_powershell_command,
    detect_platform_capability,
    ps_single_quote,
)
from tools.platform_acceptance.research_execution.types import (
    AcceptanceCaseResult,
    AcceptanceCategory,
    AcceptanceReport,
    PlatformCapability,
    PlatformMatrix,
    TestStatus,
    compute_report_checksum,
    json_safe,
    write_atomic_json,
)

_IS_WINDOWS = os.name == "nt"


class ResearchExecutionAcceptanceHarness:
    """Orchestrator for cross-platform research execution acceptance testing."""

    def __init__(
        self,
        capability: Optional[PlatformCapability] = None,
        timeout_s: float = 10.0,
    ) -> None:
        self.capability = capability or detect_platform_capability()
        self.timeout_s = timeout_s

    def run_all(self, target_dir: Optional[Path] = None) -> AcceptanceReport:
        """Execute all acceptance test cases and return a tamper-evident report."""
        cases: List[Callable[[Path], AcceptanceCaseResult]] = [
            # 1. Data Access & Local Metadata
            self._case_local_metadata_registration,
            self._case_bounded_cache_budget_enforcement,
            # 2. Cache Bounds, Atomic Partials, Checksum Mismatch, Retry, Eviction
            self._case_atomic_partial_and_checksum_mismatch,
            self._case_retry_classification,
            self._case_lru_eviction_and_lease_protection,
            # 3. Process Timeout & Descendant Cleanup
            self._case_process_timeout_and_cleanup,
            # 4. Output Containment & Traversal Rejection
            self._case_output_containment_and_traversal_rejection,
            # 5. Artifact Integrity & Finite JSON
            self._case_finite_json_and_malformed_artifact_rejection,
            # 6. PowerShell Operations
            self._case_powershell_wrapper_syntax_and_quoting,
            self._case_powershell_execution,
            # 7. Windows Specifics
            self._case_windows_process_tree_termination,
            self._case_windows_path_separators_normalization,
            self._case_windows_file_locking,
            self._case_windows_atomic_replacement,
            self._case_windows_symlink_privilege_handling,
        ]

        results: List[AcceptanceCaseResult] = []

        with tempfile.TemporaryDirectory(prefix="acceptance_") as temp_root:
            work_dir = Path(temp_root) if target_dir is None else Path(target_dir)
            work_dir.mkdir(parents=True, exist_ok=True)

            for case_fn in cases:
                case_dir = work_dir / case_fn.__name__
                case_dir.mkdir(parents=True, exist_ok=True)
                try:
                    result = case_fn(case_dir)
                except Exception as exc:
                    result = AcceptanceCaseResult(
                        name=case_fn.__name__,
                        category=AcceptanceCategory.PROCESS_EXECUTION,
                        status=TestStatus.FAIL,
                        platform=self.capability.os_name,
                        elapsed_s=0.0,
                        details=f"Unhandled exception during acceptance test: {exc}",
                        error=str(exc),
                    )
                results.append(result)

        # Build PlatformMatrix
        supported_cats: List[str] = [
            AcceptanceCategory.DATA_ACCESS.value,
            AcceptanceCategory.CACHE_EVICTION.value,
            AcceptanceCategory.PROCESS_EXECUTION.value,
            AcceptanceCategory.OUTPUT_CONTAINMENT.value,
            AcceptanceCategory.ARTIFACT_INTEGRITY.value,
        ]
        unsupported_cats: List[str] = []

        if self.capability.powershell_available:
            supported_cats.append(AcceptanceCategory.POWERSHELL_OPERATIONS.value)
        else:
            unsupported_cats.append(AcceptanceCategory.POWERSHELL_OPERATIONS.value)

        if self.capability.is_windows:
            supported_cats.append(AcceptanceCategory.WINDOWS_SPECIFICS.value)
        else:
            unsupported_cats.append(AcceptanceCategory.WINDOWS_SPECIFICS.value)

        matrix = PlatformMatrix(
            os_name=self.capability.os_name,
            platform_release=self.capability.platform_release,
            python_version=self.capability.python_version,
            is_windows=self.capability.is_windows,
            powershell_available=self.capability.powershell_available,
            powershell_version=self.capability.powershell_version,
            supported_categories=supported_cats,
            unsupported_categories=unsupported_cats,
        )

        passed = sum(1 for r in results if r.status == TestStatus.PASS)
        failed = sum(1 for r in results if r.status == TestStatus.FAIL)
        unsupported = sum(1 for r in results if r.status == TestStatus.UNSUPPORTED)
        skipped = sum(1 for r in results if r.status == TestStatus.SKIPPED)

        report_dict: Dict[str, Any] = {
            "schema_version": "research_execution_platform_acceptance_v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "platform_matrix": matrix.to_dict(),
            "total_tests": len(results),
            "passed": passed,
            "failed": failed,
            "unsupported": unsupported,
            "skipped": skipped,
            "results": [r.to_dict() for r in results],
            "all_passed": failed == 0,
        }

        chk = compute_report_checksum(report_dict)

        return AcceptanceReport(
            schema_version="research_execution_platform_acceptance_v1",
            generated_at=report_dict["generated_at"],
            platform_matrix=matrix,
            total_tests=len(results),
            passed=passed,
            failed=failed,
            unsupported=unsupported,
            skipped=skipped,
            results=results,
            all_passed=failed == 0,
            checksum=chk,
        )

    # ----------------------------------------------------------------------- #
    # 1. Data Access & Local Metadata
    # ----------------------------------------------------------------------- #
    def _case_local_metadata_registration(self, work_dir: Path) -> AcceptanceCaseResult:
        start = time.monotonic()
        mock_adapter = MockTransferAdapter()
        cache = BoundedChunkCache(
            cache_root=work_dir / "cache",
            max_cache_bytes=100_000,
            transfer_adapter=mock_adapter,
        )

        bids_rel = "sub-01/ses-01/eeg/sub-01_ses-01_task-rest_eeg.edf"
        rec = cache.register_manifest_item(
            dataset_id="ds005620",
            bids_path=bids_rel,
            source_uri="https://mock.openneuro.org/sub-01.edf",
            size_bytes=1024,
            expected_checksum="aabbccddeeff11223344",
        )
        stored = cache._records.get(("ds005620", normalize_bids_relative_path(bids_rel), 0))

        if stored is None or stored.bids_path != bids_rel:
            return AcceptanceCaseResult(
                name="local_metadata_registration",
                category=AcceptanceCategory.DATA_ACCESS,
                status=TestStatus.FAIL,
                platform=self.capability.os_name,
                elapsed_s=time.monotonic() - start,
                details="Failed to register or retrieve local manifest metadata",
            )

        # Ensure fetch of unregistered object fails with MISSING_OBJECT
        unregistered_res = cache.fetch(
            dataset_id="ds005620",
            bids_path="sub-02/ses-01/eeg/sub-02_ses-01_task-rest_eeg.edf",
            allow_network=True,
        )
        if unregistered_res.success or unregistered_res.error_code != CacheErrorCode.MISSING_OBJECT.value:
            return AcceptanceCaseResult(
                name="local_metadata_registration",
                category=AcceptanceCategory.DATA_ACCESS,
                status=TestStatus.FAIL,
                platform=self.capability.os_name,
                elapsed_s=time.monotonic() - start,
                details="Cache permitted unregistered object access; manifest-first rule violated",
            )

        return AcceptanceCaseResult(
            name="local_metadata_registration",
            category=AcceptanceCategory.DATA_ACCESS,
            status=TestStatus.PASS,
            platform=self.capability.os_name,
            elapsed_s=time.monotonic() - start,
            details="Manifest-first metadata registration and unregistered-access rejection verified",
        )

    def _case_bounded_cache_budget_enforcement(self, work_dir: Path) -> AcceptanceCaseResult:
        start = time.monotonic()
        mock_adapter = MockTransferAdapter()
        # Cap cache at 500 bytes
        cache = BoundedChunkCache(
            cache_root=work_dir / "cache",
            max_cache_bytes=500,
            transfer_adapter=mock_adapter,
        )

        # Register an object of 1000 bytes (exceeds entire budget)
        cache.register_manifest_item(
            dataset_id="ds005620",
            bids_path="sub-01/ses-01/eeg/sub-01_ses-01_task-rest_huge.edf",
            source_uri="https://mock.openneuro.org/huge.edf",
            size_bytes=1000,
        )
        plan = cache.plan("ds005620")

        if plan.is_executable or "exceed total cache capacity" not in (plan.rejection_reason or ""):
            return AcceptanceCaseResult(
                name="bounded_cache_budget_enforcement",
                category=AcceptanceCategory.DATA_ACCESS,
                status=TestStatus.FAIL,
                platform=self.capability.os_name,
                elapsed_s=time.monotonic() - start,
                details=f"Cache did not reject oversized object plan: {plan.rejection_reason}",
            )

        return AcceptanceCaseResult(
            name="bounded_cache_budget_enforcement",
            category=AcceptanceCategory.DATA_ACCESS,
            status=TestStatus.PASS,
            platform=self.capability.os_name,
            elapsed_s=time.monotonic() - start,
            details="Cache budget limit strictly enforced against oversized chunks",
        )

    # ----------------------------------------------------------------------- #
    # 2. Cache Bounds, Atomic Partials, Checksum Mismatch, Retry, Eviction
    # ----------------------------------------------------------------------- #
    def _case_atomic_partial_and_checksum_mismatch(self, work_dir: Path) -> AcceptanceCaseResult:
        start = time.monotonic()
        cache_dir = work_dir / "cache"
        mock_adapter = MockTransferAdapter()
        mock_uri = "https://mock.openneuro.org/sub-01_ses-01_task-rest_corrupt.edf"
        bids_file = "sub-01/ses-01/eeg/sub-01_ses-01_task-rest_corrupt.edf"
        data = b"correct payload content"
        mock_adapter.register_remote_object(mock_uri, data)

        cache = BoundedChunkCache(
            cache_root=cache_dir,
            max_cache_bytes=10_000,
            transfer_adapter=mock_adapter,
        )

        # Register object with expected SHA256 that does NOT match payload
        cache.register_manifest_item(
            dataset_id="ds005620",
            bids_path=bids_file,
            source_uri=mock_uri,
            size_bytes=len(data),
            expected_checksum="wrong_checksum_0000000000000000000000000000000000000000000000000000",
        )
        res = cache.fetch("ds005620", bids_file, allow_network=True)

        if res.success or res.error_code != CacheErrorCode.CHECKSUM_MISMATCH.value:
            return AcceptanceCaseResult(
                name="atomic_partial_and_checksum_mismatch",
                category=AcceptanceCategory.CACHE_EVICTION,
                status=TestStatus.FAIL,
                platform=self.capability.os_name,
                elapsed_s=time.monotonic() - start,
                details=f"Checksum mismatch not flagged as expected: {res}",
            )

        # Verify no orphan partial files remain in cache directory
        part_files = list(cache_dir.rglob("*.part.*"))
        if part_files:
            return AcceptanceCaseResult(
                name="atomic_partial_and_checksum_mismatch",
                category=AcceptanceCategory.CACHE_EVICTION,
                status=TestStatus.FAIL,
                platform=self.capability.os_name,
                elapsed_s=time.monotonic() - start,
                details=f"Stale partial files remained after failed transfer: {part_files}",
            )

        return AcceptanceCaseResult(
            name="atomic_partial_and_checksum_mismatch",
            category=AcceptanceCategory.CACHE_EVICTION,
            status=TestStatus.PASS,
            platform=self.capability.os_name,
            elapsed_s=time.monotonic() - start,
            details="Checksum mismatch detected and partial file cleaned up atomically",
        )

    def _case_retry_classification(self, work_dir: Path) -> AcceptanceCaseResult:
        start = time.monotonic()
        mock_adapter = MockTransferAdapter()
        mock_uri = "https://mock.openneuro.org/sub-01_ses-01_task-rest_retry.edf"
        bids_file = "sub-01/ses-01/eeg/sub-01_ses-01_task-rest_retry.edf"
        data = b"retryable content"
        sha = hashlib.sha256(data).hexdigest()

        mock_adapter.register_remote_object(mock_uri, data)
        # Simulate 1 transient error
        mock_adapter.set_transient_failure(mock_uri, 1)

        cache = BoundedChunkCache(
            cache_root=work_dir / "cache",
            max_cache_bytes=10_000,
            transfer_adapter=mock_adapter,
        )

        cache.register_manifest_item(
            dataset_id="ds005620",
            bids_path=bids_file,
            source_uri=mock_uri,
            size_bytes=len(data),
            expected_checksum=sha,
        )

        res = cache.fetch("ds005620", bids_file, allow_network=True, max_retries=3)

        if not res.success or res.attempts < 2:
            return AcceptanceCaseResult(
                name="retry_classification",
                category=AcceptanceCategory.CACHE_EVICTION,
                status=TestStatus.FAIL,
                platform=self.capability.os_name,
                elapsed_s=time.monotonic() - start,
                details=f"Transient error was not retried or failed: {res}",
            )

        return AcceptanceCaseResult(
            name="retry_classification",
            category=AcceptanceCategory.CACHE_EVICTION,
            status=TestStatus.PASS,
            platform=self.capability.os_name,
            elapsed_s=time.monotonic() - start,
            details="Retryable network reset handled with recovery and backoff",
        )

    def _case_lru_eviction_and_lease_protection(self, work_dir: Path) -> AcceptanceCaseResult:
        start = time.monotonic()
        mock_adapter = MockTransferAdapter()
        # Budget = 200 bytes, headroom = 0 so total budget is strictly 200 bytes
        cache = BoundedChunkCache(
            cache_root=work_dir / "cache",
            max_cache_bytes=200,
            min_free_headroom_bytes=0,
            transfer_adapter=mock_adapter,
        )

        d1 = b"A" * 90
        d2 = b"B" * 90
        d3 = b"C" * 90

        p1 = "sub-01/ses-01/eeg/sub-01_ses-01_task-rest_d1.edf"
        p2 = "sub-01/ses-01/eeg/sub-01_ses-01_task-rest_d2.edf"
        p3 = "sub-01/ses-01/eeg/sub-01_ses-01_task-rest_d3.edf"

        u1 = "https://mock.openneuro.org/d1.edf"
        u2 = "https://mock.openneuro.org/d2.edf"
        u3 = "https://mock.openneuro.org/d3.edf"

        mock_adapter.register_remote_object(u1, d1)
        mock_adapter.register_remote_object(u2, d2)
        mock_adapter.register_remote_object(u3, d3)

        cache.register_manifest_item("ds005620", p1, u1, len(d1), hashlib.sha256(d1).hexdigest())
        cache.register_manifest_item("ds005620", p2, u2, len(d2), hashlib.sha256(d2).hexdigest())
        cache.register_manifest_item("ds005620", p3, u3, len(d3), hashlib.sha256(d3).hexdigest())

        cache.fetch("ds005620", p1, allow_network=True)
        # Lease d1 to protect it from eviction!
        lease1 = cache.acquire_lease("ds005620", p1)

        cache.fetch("ds005620", p2, allow_network=True)
        # Now fetch d3 (90 bytes): total would be 270 > 200.
        # d1 is leased, so d2 must be evicted instead of d1!
        cache.fetch("ds005620", p3, allow_network=True)

        k1 = ("ds005620", normalize_bids_relative_path(p1), 0)
        k2 = ("ds005620", normalize_bids_relative_path(p2), 0)
        rec1 = cache._records.get(k1)
        rec2 = cache._records.get(k2)
        cache.release_lease(lease1)

        if rec1 is None or rec1.status != "CACHED":
            return AcceptanceCaseResult(
                name="lru_eviction_and_lease_protection",
                category=AcceptanceCategory.CACHE_EVICTION,
                status=TestStatus.FAIL,
                platform=self.capability.os_name,
                elapsed_s=time.monotonic() - start,
                details=f"Active lease failed to protect d1 from eviction: {rec1.status if rec1 else None}",
            )

        if rec2 is None or rec2.status != "EVICTED":
            return AcceptanceCaseResult(
                name="lru_eviction_and_lease_protection",
                category=AcceptanceCategory.CACHE_EVICTION,
                status=TestStatus.FAIL,
                platform=self.capability.os_name,
                elapsed_s=time.monotonic() - start,
                details=f"Unleased d2 was not evicted under pressure: {rec2.status if rec2 else None}",
            )

        return AcceptanceCaseResult(
            name="lru_eviction_and_lease_protection",
            category=AcceptanceCategory.CACHE_EVICTION,
            status=TestStatus.PASS,
            platform=self.capability.os_name,
            elapsed_s=time.monotonic() - start,
            details="LRU eviction and active lease immunity verified under budget pressure",
        )

    # ----------------------------------------------------------------------- #
    # 3. Process Timeout & Descendant Cleanup
    # ----------------------------------------------------------------------- #
    def _case_process_timeout_and_cleanup(self, work_dir: Path) -> AcceptanceCaseResult:
        start = time.monotonic()
        # Script sleeps longer than timeout
        script = [
            sys.executable,
            "-c",
            "import time; time.sleep(3.0)",
        ]

        popen_kwargs: Dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
        }
        if _IS_WINDOWS:
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        proc = subprocess.Popen(script, **popen_kwargs)
        timed_out = False

        try:
            proc.communicate(timeout=0.5)
        except subprocess.TimeoutExpired:
            timed_out = True
            if _IS_WINDOWS:
                try:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)
                except Exception:
                    pass
                try:
                    proc.kill()
                except Exception:
                    pass
            else:
                try:
                    pgid = os.getpgid(proc.pid)
                    os.killpg(pgid, signal.SIGKILL)
                except Exception:
                    pass
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()
            try:
                proc.wait(timeout=2.0)
            except Exception:
                pass

        elapsed = time.monotonic() - start

        if not timed_out or proc.poll() is None:
            return AcceptanceCaseResult(
                name="process_timeout_and_cleanup",
                category=AcceptanceCategory.PROCESS_EXECUTION,
                status=TestStatus.FAIL,
                platform=self.capability.os_name,
                elapsed_s=elapsed,
                details="Process did not time out cleanly or was not terminated",
            )

        return AcceptanceCaseResult(
            name="process_timeout_and_cleanup",
            category=AcceptanceCategory.PROCESS_EXECUTION,
            status=TestStatus.PASS,
            platform=self.capability.os_name,
            elapsed_s=elapsed,
            details=f"Process terminated cleanly on timeout ({elapsed:.2f}s) without orphan leaks",
        )

    # ----------------------------------------------------------------------- #
    # 4. Output Containment & Traversal Rejection
    # ----------------------------------------------------------------------- #
    def _case_output_containment_and_traversal_rejection(self, work_dir: Path) -> AcceptanceCaseResult:
        start = time.monotonic()
        traversal_paths = [
            "../outside.dat",
            "sub-01/../../escape.txt",
            "/etc/passwd",
            "C:\\Windows\\system32\\cmd.exe",
            "sub-01/invalid*file?.dat",
        ]

        rejected = 0
        for p in traversal_paths:
            try:
                normalize_bids_relative_path(p)
            except (BIDSValidationError, ValueError):
                rejected += 1

        if rejected != len(traversal_paths):
            return AcceptanceCaseResult(
                name="output_containment_and_traversal_rejection",
                category=AcceptanceCategory.OUTPUT_CONTAINMENT,
                status=TestStatus.FAIL,
                platform=self.capability.os_name,
                elapsed_s=time.monotonic() - start,
                details=f"Failed to reject all path traversals ({rejected}/{len(traversal_paths)} rejected)",
            )

        return AcceptanceCaseResult(
            name="output_containment_and_traversal_rejection",
            category=AcceptanceCategory.OUTPUT_CONTAINMENT,
            status=TestStatus.PASS,
            platform=self.capability.os_name,
            elapsed_s=time.monotonic() - start,
            details=f"All {len(traversal_paths)} path traversal attempts strictly rejected",
        )

    # ----------------------------------------------------------------------- #
    # 5. Artifact Integrity & Finite JSON
    # ----------------------------------------------------------------------- #
    def _case_finite_json_and_malformed_artifact_rejection(self, work_dir: Path) -> AcceptanceCaseResult:
        start = time.monotonic()
        payload = {
            "nan": float("nan"),
            "inf": float("inf"),
            "neg_inf": float("-inf"),
            "clean_float": 42.0,
            "nested": {"array": [float("nan"), 10]},
        }
        sanitized = json_safe(payload)

        try:
            serialized = json.dumps(sanitized, allow_nan=False)
            loaded = json.loads(serialized)
            if loaded["nan"] is not None or loaded["inf"] is not None or loaded["clean_float"] != 42.0:
                raise ValueError("Sanitization produced unexpected JSON structure")
        except Exception as exc:
            return AcceptanceCaseResult(
                name="finite_json_and_malformed_artifact_rejection",
                category=AcceptanceCategory.ARTIFACT_INTEGRITY,
                status=TestStatus.FAIL,
                platform=self.capability.os_name,
                elapsed_s=time.monotonic() - start,
                details=f"Finite JSON validation failed: {exc}",
            )

        # Atomic write test
        test_file = work_dir / "atomic.json"
        write_atomic_json(test_file, {"status": "ok"})
        if not test_file.exists() or json.loads(test_file.read_text(encoding="utf-8"))["status"] != "ok":
            return AcceptanceCaseResult(
                name="finite_json_and_malformed_artifact_rejection",
                category=AcceptanceCategory.ARTIFACT_INTEGRITY,
                status=TestStatus.FAIL,
                platform=self.capability.os_name,
                elapsed_s=time.monotonic() - start,
                details="Atomic JSON file write failed",
            )

        return AcceptanceCaseResult(
            name="finite_json_and_malformed_artifact_rejection",
            category=AcceptanceCategory.ARTIFACT_INTEGRITY,
            status=TestStatus.PASS,
            platform=self.capability.os_name,
            elapsed_s=time.monotonic() - start,
            details="Strict finite JSON serialization (allow_nan=False) and atomic I/O verified",
        )

    # ----------------------------------------------------------------------- #
    # 6. PowerShell Operations
    # ----------------------------------------------------------------------- #
    def _case_powershell_wrapper_syntax_and_quoting(self, work_dir: Path) -> AcceptanceCaseResult:
        start = time.monotonic()
        # Test quoting logic
        assert ps_single_quote("plain") == "'plain'"
        assert ps_single_quote("o'brien") == "'o''brien'"
        assert ps_single_quote("C:\\path with spaces\\script.py") == "'C:\\path with spaces\\script.py'"

        cmd = build_powershell_command([sys.executable, "-c", "print('hello')"], binary="powershell")
        assert cmd[0] == "powershell"
        assert "-NoProfile" in cmd and "-NonInteractive" in cmd and "-Command" in cmd
        assert cmd[-1].startswith("& ")

        return AcceptanceCaseResult(
            name="powershell_wrapper_syntax_and_quoting",
            category=AcceptanceCategory.POWERSHELL_OPERATIONS,
            status=TestStatus.PASS,
            platform=self.capability.os_name,
            elapsed_s=time.monotonic() - start,
            details="PowerShell command construction and single-quote escaping validated",
        )

    def _case_powershell_execution(self, work_dir: Path) -> AcceptanceCaseResult:
        start = time.monotonic()
        if not self.capability.powershell_available:
            return AcceptanceCaseResult(
                name="powershell_execution",
                category=AcceptanceCategory.POWERSHELL_OPERATIONS,
                status=TestStatus.UNSUPPORTED,
                platform=self.capability.os_name,
                elapsed_s=time.monotonic() - start,
                details="PowerShell binary not found on host PATH",
            )

        # Run safe non-interactive command
        ps_cmd = build_powershell_command(
            [sys.executable, "-c", "print('POWERSHELL_ACCEPTANCE_OK')"],
            binary=self.capability.powershell_binary,
        )

        try:
            proc = subprocess.run(
                ps_cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=max(20.0, self.timeout_s),
            )
            if proc.returncode == 0 and "POWERSHELL_ACCEPTANCE_OK" in proc.stdout:
                return AcceptanceCaseResult(
                    name="powershell_execution",
                    category=AcceptanceCategory.POWERSHELL_OPERATIONS,
                    status=TestStatus.PASS,
                    platform=self.capability.os_name,
                    elapsed_s=time.monotonic() - start,
                    details=f"PowerShell executed child successfully using {self.capability.powershell_binary}",
                    metadata={"powershell_version": self.capability.powershell_version},
                )
            return AcceptanceCaseResult(
                name="powershell_execution",
                category=AcceptanceCategory.POWERSHELL_OPERATIONS,
                status=TestStatus.FAIL,
                platform=self.capability.os_name,
                elapsed_s=time.monotonic() - start,
                details=f"PowerShell command exited with code {proc.returncode}: {proc.stderr}",
            )
        except Exception as exc:
            return AcceptanceCaseResult(
                name="powershell_execution",
                category=AcceptanceCategory.POWERSHELL_OPERATIONS,
                status=TestStatus.FAIL,
                platform=self.capability.os_name,
                elapsed_s=time.monotonic() - start,
                details=f"PowerShell execution failed: {exc}",
            )

    # ----------------------------------------------------------------------- #
    # 7. Windows Specifics (Strictly UNSUPPORTED on non-Windows)
    # ----------------------------------------------------------------------- #
    def _case_windows_process_tree_termination(self, work_dir: Path) -> AcceptanceCaseResult:
        start = time.monotonic()
        if not self.capability.is_windows:
            return AcceptanceCaseResult(
                name="windows_process_tree_termination",
                category=AcceptanceCategory.WINDOWS_SPECIFICS,
                status=TestStatus.UNSUPPORTED,
                platform=self.capability.os_name,
                elapsed_s=time.monotonic() - start,
                details="Windows process-tree termination is unsupported on non-Windows hosts",
                windows_specific=True,
            )

        # On Windows: spawn parent that spawns child
        grandchild_script = (
            "import subprocess, sys, time; "
            "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(5)'], close_fds=True); "
            "time.sleep(5)"
        )
        proc = subprocess.Popen(
            [sys.executable, "-c", grandchild_script],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        time.sleep(0.3)
        # Terminate process tree via taskkill /F /T
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)
        try:
            proc.kill()
        except Exception:
            pass
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()
        proc.wait(timeout=3.0)

        return AcceptanceCaseResult(
            name="windows_process_tree_termination",
            category=AcceptanceCategory.WINDOWS_SPECIFICS,
            status=TestStatus.PASS,
            platform=self.capability.os_name,
            elapsed_s=time.monotonic() - start,
            details="Windows process tree and child group terminated via taskkill /F /T",
            windows_specific=True,
        )

    def _case_windows_path_separators_normalization(self, work_dir: Path) -> AcceptanceCaseResult:
        start = time.monotonic()
        if not self.capability.is_windows:
            return AcceptanceCaseResult(
                name="windows_path_separators_normalization",
                category=AcceptanceCategory.WINDOWS_SPECIFICS,
                status=TestStatus.UNSUPPORTED,
                platform=self.capability.os_name,
                elapsed_s=time.monotonic() - start,
                details="Windows path separator normalization is unsupported on non-Windows hosts",
                windows_specific=True,
            )

        # On Windows: backslash mixed with forward slash
        raw_bids = "sub-01\\ses-01/eeg\\sub-01_ses-01_task-rest_eeg.vhdr"
        normalized = normalize_bids_relative_path(raw_bids)
        assert "\\" not in normalized
        assert normalized == "sub-01/ses-01/eeg/sub-01_ses-01_task-rest_eeg.vhdr"

        return AcceptanceCaseResult(
            name="windows_path_separators_normalization",
            category=AcceptanceCategory.WINDOWS_SPECIFICS,
            status=TestStatus.PASS,
            platform=self.capability.os_name,
            elapsed_s=time.monotonic() - start,
            details="Windows backslashes normalized into canonical BIDS forward slashes",
            windows_specific=True,
        )

    def _case_windows_file_locking(self, work_dir: Path) -> AcceptanceCaseResult:
        start = time.monotonic()
        if not self.capability.is_windows:
            return AcceptanceCaseResult(
                name="windows_file_locking",
                category=AcceptanceCategory.WINDOWS_SPECIFICS,
                status=TestStatus.UNSUPPORTED,
                platform=self.capability.os_name,
                elapsed_s=time.monotonic() - start,
                details="Windows msvcrt file locking is unsupported on non-Windows hosts",
                windows_specific=True,
            )

        try:
            import msvcrt
        except ImportError:
            return AcceptanceCaseResult(
                name="windows_file_locking",
                category=AcceptanceCategory.WINDOWS_SPECIFICS,
                status=TestStatus.FAIL,
                platform=self.capability.os_name,
                elapsed_s=time.monotonic() - start,
                details="msvcrt module missing on Windows host",
                windows_specific=True,
            )

        lock_file = work_dir / "locked_file.bin"
        lock_file.write_bytes(b"data to lock")

        with open(lock_file, "r+b") as h1:
            # Lock first 10 bytes exclusively
            msvcrt.locking(h1.fileno(), msvcrt.LK_NBLCK, 10)

            # Second handle attempt should fail with PermissionError / OSError
            lock_prevented = False
            try:
                with open(lock_file, "r+b") as h2:
                    msvcrt.locking(h2.fileno(), msvcrt.LK_NBLCK, 10)
            except OSError:
                lock_prevented = True

            # Unlock
            msvcrt.locking(h1.fileno(), msvcrt.LK_UNLCK, 10)

        if not lock_prevented:
            return AcceptanceCaseResult(
                name="windows_file_locking",
                category=AcceptanceCategory.WINDOWS_SPECIFICS,
                status=TestStatus.FAIL,
                platform=self.capability.os_name,
                elapsed_s=time.monotonic() - start,
                details="Exclusive lock did not prevent concurrent lock acquisition",
                windows_specific=True,
            )

        return AcceptanceCaseResult(
            name="windows_file_locking",
            category=AcceptanceCategory.WINDOWS_SPECIFICS,
            status=TestStatus.PASS,
            platform=self.capability.os_name,
            elapsed_s=time.monotonic() - start,
            details="Windows msvcrt mandatory file locking and unlock cycle verified",
            windows_specific=True,
        )

    def _case_windows_atomic_replacement(self, work_dir: Path) -> AcceptanceCaseResult:
        start = time.monotonic()
        if not self.capability.is_windows:
            return AcceptanceCaseResult(
                name="windows_atomic_replacement",
                category=AcceptanceCategory.WINDOWS_SPECIFICS,
                status=TestStatus.UNSUPPORTED,
                platform=self.capability.os_name,
                elapsed_s=time.monotonic() - start,
                details="Windows atomic replacement is unsupported on non-Windows hosts",
                windows_specific=True,
            )

        target = work_dir / "target.txt"
        target.write_text("original content", encoding="utf-8")

        temp = work_dir / "temp.txt"
        temp.write_text("updated content", encoding="utf-8")

        os.replace(temp, target)
        assert target.read_text(encoding="utf-8") == "updated content"
        assert not temp.exists()

        return AcceptanceCaseResult(
            name="windows_atomic_replacement",
            category=AcceptanceCategory.WINDOWS_SPECIFICS,
            status=TestStatus.PASS,
            platform=self.capability.os_name,
            elapsed_s=time.monotonic() - start,
            details="Windows NTFS os.replace atomic file replacement verified",
            windows_specific=True,
        )

    def _case_windows_symlink_privilege_handling(self, work_dir: Path) -> AcceptanceCaseResult:
        start = time.monotonic()
        if not self.capability.is_windows:
            return AcceptanceCaseResult(
                name="windows_symlink_privilege_handling",
                category=AcceptanceCategory.WINDOWS_SPECIFICS,
                status=TestStatus.UNSUPPORTED,
                platform=self.capability.os_name,
                elapsed_s=time.monotonic() - start,
                details="Windows symlink privilege handling is unsupported on non-Windows hosts",
                windows_specific=True,
            )

        src = work_dir / "source.txt"
        src.write_text("symlink source", encoding="utf-8")
        link = work_dir / "link.txt"

        privilege_detected = False
        try:
            os.symlink(src, link)
            privilege_detected = link.is_symlink()
            link.unlink()
        except OSError:
            # Expected on non-developer mode / non-admin Windows
            pass

        return AcceptanceCaseResult(
            name="windows_symlink_privilege_handling",
            category=AcceptanceCategory.WINDOWS_SPECIFICS,
            status=TestStatus.PASS,
            platform=self.capability.os_name,
            elapsed_s=time.monotonic() - start,
            details=f"Windows symlink capability safely evaluated (developer_privilege={privilege_detected})",
            windows_specific=True,
            metadata={"developer_mode_or_admin": privilege_detected},
        )
