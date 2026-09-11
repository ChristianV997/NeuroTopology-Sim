"""Resumable transfer abstraction, checksum verification, and retry backoff.

Supports atomic partial staging, transient error classification,
and strict fail-closed network policies.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import time
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from tools.data_access.chunk_cache.types import (
    CacheErrorCode,
    ChunkRange,
    TransferResult,
)

TRANSIENT_EXCEPTION_TYPES = (
    ConnectionResetError,
    ConnectionAbortedError,
    TimeoutError,
    OSError,  # includes socket reset on Windows
)


class TransferAdapter(ABC):
    """Abstract base class for chunk transfer implementations."""

    @abstractmethod
    def fetch_object_metadata(
        self,
        dataset_id: str,
        bids_path: str,
        source_uri: str,
        allow_network: bool = False,
    ) -> dict:
        """Fetch remote object metadata (size, etag/sha256) without downloading data bytes."""
        pass

    @abstractmethod
    def transfer_chunk(
        self,
        source_uri: str,
        target_path: Path,
        chunk_range: Optional[ChunkRange] = None,
        expected_checksum: Optional[str] = None,
        allow_network: bool = False,
        max_retries: int = 3,
        base_backoff_s: float = 0.05,
    ) -> TransferResult:
        """Download a chunk or full file to target_path atomically."""
        pass


def compute_file_sha256(path: Path) -> str:
    """Compute SHA-256 digest of a local file in 1MB blocks."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


class MockTransferAdapter(TransferAdapter):
    """Deterministic, in-memory/mock transfer adapter for offline unit testing."""

    def __init__(self) -> None:
        # Map source_uri -> {"data": bytes, "size": int, "sha256": str, "status_code": int}
        self._remote_store: Dict[str, dict] = {}
        # Transient failure counters: source_uri -> remaining failures before success
        self._transient_failures: Dict[str, int] = {}
        self._transient_error_type: type = ConnectionResetError

    def register_remote_object(
        self,
        source_uri: str,
        content: bytes,
        sha256: Optional[str] = None,
        status_code: int = 200,
    ) -> None:
        """Register a mock remote object."""
        calc_sha = hashlib.sha256(content).hexdigest()
        self._remote_store[source_uri] = {
            "data": content,
            "size": len(content),
            "sha256": sha256 if sha256 is not None else calc_sha,
            "status_code": status_code,
        }

    def set_transient_failure(self, source_uri: str, failure_count: int, error_type: type = ConnectionResetError) -> None:
        """Configure transient connection resets for failure_count attempts."""
        self._transient_failures[source_uri] = failure_count
        self._transient_error_type = error_type

    def fetch_object_metadata(
        self,
        dataset_id: str,
        bids_path: str,
        source_uri: str,
        allow_network: bool = False,
    ) -> dict:
        if not allow_network:
            raise PermissionError(f"Network access disabled: cannot fetch metadata for {source_uri}")

        if source_uri not in self._remote_store:
            raise FileNotFoundError(f"Remote object not found: {source_uri}")

        item = self._remote_store[source_uri]
        if item["status_code"] == 404:
            raise FileNotFoundError(f"Remote object 404 Not Found: {source_uri}")
        elif item["status_code"] == 403:
            raise PermissionError(f"Remote object 403 Permission Denied: {source_uri}")

        return {
            "size_bytes": item["size"],
            "expected_checksum": item["sha256"],
            "source_uri": source_uri,
        }

    def transfer_chunk(
        self,
        source_uri: str,
        target_path: Path,
        chunk_range: Optional[ChunkRange] = None,
        expected_checksum: Optional[str] = None,
        allow_network: bool = False,
        max_retries: int = 3,
        base_backoff_s: float = 0.01,
    ) -> TransferResult:
        if not allow_network:
            return TransferResult(
                success=False,
                dataset_id="",
                bids_path=target_path.name,
                chunk_index=0,
                bytes_transferred=0,
                error_code=CacheErrorCode.NETWORK_DISABLED.value,
                error_message="Network access is disabled (fail-closed policy)",
                attempts=0,
            )

        if source_uri not in self._remote_store:
            return TransferResult(
                success=False,
                dataset_id="",
                bids_path=target_path.name,
                chunk_index=0,
                bytes_transferred=0,
                error_code=CacheErrorCode.MISSING_OBJECT.value,
                error_message=f"Object not found: {source_uri}",
                attempts=1,
            )

        item = self._remote_store[source_uri]
        if item["status_code"] == 403:
            return TransferResult(
                success=False,
                dataset_id="",
                bids_path=target_path.name,
                chunk_index=0,
                bytes_transferred=0,
                error_code=CacheErrorCode.PERMISSION_DENIED.value,
                error_message=f"Access denied to {source_uri}",
                attempts=1,
            )
        elif item["status_code"] == 404:
            return TransferResult(
                success=False,
                dataset_id="",
                bids_path=target_path.name,
                chunk_index=0,
                bytes_transferred=0,
                error_code=CacheErrorCode.MISSING_OBJECT.value,
                error_message=f"404 Not Found: {source_uri}",
                attempts=1,
            )

        # Handle atomic write staging
        target_path.parent.mkdir(parents=True, exist_ok=True)
        part_path = target_path.with_name(f"{target_path.name}.part.{uuid.uuid4().hex[:8]}")

        raw_data = item["data"]
        if chunk_range is not None:
            raw_data = raw_data[chunk_range.start_byte : chunk_range.end_byte + 1]

        attempts = 0
        while attempts < max_retries:
            attempts += 1
            # Check transient failure
            rem_fails = self._transient_failures.get(source_uri, 0)
            if rem_fails > 0:
                self._transient_failures[source_uri] = rem_fails - 1
                # Transient backoff sleep
                time.sleep(min(0.1, base_backoff_s * (2 ** (attempts - 1))))
                if attempts >= max_retries:
                    if part_path.exists():
                        part_path.unlink()
                    return TransferResult(
                        success=False,
                        dataset_id="",
                        bids_path=target_path.name,
                        chunk_index=0,
                        bytes_transferred=0,
                        error_code=CacheErrorCode.NETWORK_ERROR.value,
                        error_message=f"Exhausted {max_retries} retries on transient reset",
                        attempts=attempts,
                    )
                continue

            # Write data atomically to partial file
            try:
                part_path.write_bytes(raw_data)
            except OSError as exc:
                if part_path.exists():
                    part_path.unlink()
                return TransferResult(
                    success=False,
                    dataset_id="",
                    bids_path=target_path.name,
                    chunk_index=0,
                    bytes_transferred=0,
                    error_code=CacheErrorCode.DISK_EXHAUSTION.value,
                    error_message=f"Write error: {exc}",
                    attempts=attempts,
                )

            actual_sha = hashlib.sha256(raw_data).hexdigest()
            checksum_verified = False
            if expected_checksum:
                if actual_sha.lower() != expected_checksum.lower():
                    # Correctness failure: never retry indefinitely!
                    if part_path.exists():
                        part_path.unlink()
                    return TransferResult(
                        success=False,
                        dataset_id="",
                        bids_path=target_path.name,
                        chunk_index=0,
                        bytes_transferred=len(raw_data),
                        error_code=CacheErrorCode.CHECKSUM_MISMATCH.value,
                        error_message=f"Checksum mismatch: expected {expected_checksum}, got {actual_sha}",
                        attempts=attempts,
                    )
                checksum_verified = True

            # Atomic rename into destination
            part_path.replace(target_path)
            return TransferResult(
                success=True,
                dataset_id="",
                bids_path=target_path.name,
                chunk_index=0,
                bytes_transferred=len(raw_data),
                cached_path=str(target_path),
                checksum_verified=checksum_verified,
                attempts=attempts,
            )

        if part_path.exists():
            part_path.unlink()
        return TransferResult(
            success=False,
            dataset_id="",
            bids_path=target_path.name,
            chunk_index=0,
            bytes_transferred=0,
            error_code=CacheErrorCode.NETWORK_ERROR.value,
            error_message="Retry limit reached",
            attempts=attempts,
        )


class HTTPTransferAdapter(TransferAdapter):
    """Direct HTTP/HTTPS ranged download adapter."""

    def fetch_object_metadata(
        self,
        dataset_id: str,
        bids_path: str,
        source_uri: str,
        allow_network: bool = False,
    ) -> dict:
        if not allow_network:
            raise PermissionError(f"Network access disabled: cannot fetch metadata for {source_uri}")

        import urllib.request
        req = urllib.request.Request(source_uri, method="HEAD")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                cl = resp.headers.get("Content-Length")
                etag = resp.headers.get("ETag", "").strip('"')
                return {
                    "size_bytes": int(cl) if cl else 0,
                    "expected_checksum": etag if (etag and len(etag) == 64) else None,
                    "source_uri": source_uri,
                }
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise FileNotFoundError(f"Remote object not found: {source_uri}") from exc
            elif exc.code == 403:
                raise PermissionError(f"Remote object access denied: {source_uri}") from exc
            raise

    def transfer_chunk(
        self,
        source_uri: str,
        target_path: Path,
        chunk_range: Optional[ChunkRange] = None,
        expected_checksum: Optional[str] = None,
        allow_network: bool = False,
        max_retries: int = 3,
        base_backoff_s: float = 0.5,
    ) -> TransferResult:
        if not allow_network:
            return TransferResult(
                success=False,
                dataset_id="",
                bids_path=target_path.name,
                chunk_index=0,
                bytes_transferred=0,
                error_code=CacheErrorCode.NETWORK_DISABLED.value,
                error_message="Network access is disabled (fail-closed policy)",
                attempts=0,
            )

        import urllib.request
        target_path.parent.mkdir(parents=True, exist_ok=True)
        part_path = target_path.with_name(f"{target_path.name}.part.{uuid.uuid4().hex[:8]}")

        headers = {}
        if chunk_range is not None:
            headers["Range"] = f"bytes={chunk_range.start_byte}-{chunk_range.end_byte}"

        attempts = 0
        while attempts < max_retries:
            attempts += 1
            req = urllib.request.Request(source_uri, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=20) as resp, part_path.open("wb") as out:
                    shutil.copyfileobj(resp, out)

                actual_sha = compute_file_sha256(part_path)
                checksum_verified = False
                if expected_checksum:
                    if actual_sha.lower() != expected_checksum.lower():
                        part_path.unlink(missing_ok=True)
                        return TransferResult(
                            success=False,
                            dataset_id="",
                            bids_path=target_path.name,
                            chunk_index=0,
                            bytes_transferred=0,
                            error_code=CacheErrorCode.CHECKSUM_MISMATCH.value,
                            error_message=f"Checksum mismatch: expected {expected_checksum}, got {actual_sha}",
                            attempts=attempts,
                        )
                    checksum_verified = True

                part_path.replace(target_path)
                return TransferResult(
                    success=True,
                    dataset_id="",
                    bids_path=target_path.name,
                    chunk_index=0,
                    bytes_transferred=target_path.stat().st_size,
                    cached_path=str(target_path),
                    checksum_verified=checksum_verified,
                    attempts=attempts,
                )
            except urllib.error.HTTPError as exc:
                part_path.unlink(missing_ok=True)
                if exc.code in (403, 404):
                    code = CacheErrorCode.PERMISSION_DENIED.value if exc.code == 403 else CacheErrorCode.MISSING_OBJECT.value
                    return TransferResult(
                        success=False,
                        dataset_id="",
                        bids_path=target_path.name,
                        chunk_index=0,
                        bytes_transferred=0,
                        error_code=code,
                        error_message=f"HTTP {exc.code} for {source_uri}",
                        attempts=attempts,
                    )
                # Transient 503, 500, etc.
                time.sleep(min(2.0, base_backoff_s * (2 ** (attempts - 1))))
            except TRANSIENT_EXCEPTION_TYPES as exc:
                part_path.unlink(missing_ok=True)
                time.sleep(min(2.0, base_backoff_s * (2 ** (attempts - 1))))

        part_path.unlink(missing_ok=True)
        return TransferResult(
            success=False,
            dataset_id="",
            bids_path=target_path.name,
            chunk_index=0,
            bytes_transferred=0,
            error_code=CacheErrorCode.NETWORK_ERROR.value,
            error_message="Retry limit exceeded",
            attempts=attempts,
        )
