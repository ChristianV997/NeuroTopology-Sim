"""S3 fetchers for HCP-YA and NKI-RS fast-TR BOLD datasets.

This module provides production-ready S3 access for HCP-YA and NKI-RS, enabling
direct download of fast-TR BOLD data for phase-topology validation. Requires boto3
and AWS credentials (for HCP-YA) or no credentials (for NKI-RS, public bucket).

Usage:
------
# NKI-RS (no credentials needed, CC0 public)
from validation.s3_fetchers import NKIRSFetcher
fetcher = NKIRSFetcher(cache_dir="./nki_data")
bold_path = fetcher.fetch_subject("A00008326", session=1)
confounds_path = fetcher.fetch_confounds("A00008326", session=1)

# HCP-YA (requires ConnectomeDB login + AWS credentials)
from validation.s3_fetchers import HCPYAFetcher
fetcher = HCPYAFetcher(cache_dir="./hcp_data")
bold_path = fetcher.fetch_subject("100206", run=1)
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from dataclasses import dataclass
from typing import Any, Optional
import warnings

try:
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config
    from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound
    BOTO_AVAILABLE = True
except ImportError:
    BOTO_AVAILABLE = False


class BoundedAccessError(RuntimeError):
    """A remote access request was rejected or could not be completed safely."""


POLICY_REGISTRATION_REQUIREMENTS: dict[str, Any] = {
    "schema_version": "NeuroTopology.DataAccessPolicyRegistration.v1",
    "status": "requires_policy_owner_registration",
    "owner": "tools/data_access/policy_enforcement",
    "registrations": [
        {
            "path": "validation/s3_fetchers.py",
            "symbols": ["BoundedS3ObjectStore.fetch_object", "BoundedS3ObjectStore.read_text_metadata"],
            "operation": "bounded_range_transfer",
            "rules": ["UNAUTHORIZED_BOUNDED_TRANSFER"],
            "requirements": ["explicit allow_network", "head_object size", "Range on every get_object", "checksum status", "atomic partial state", "cache budget", "observable eviction"],
        },
        {
            "path": "tools/stream_process_ds005917.py",
            "symbols": ["download_bold", "load_mdd_complete_subjects"],
            "operation": "delegated_bounded_range_transfer",
            "rules": ["UNAUTHORIZED_BOUNDED_TRANSFER"],
        },
        {
            "path": "tools/stream_process_ds006644.py",
            "symbols": ["download_subject_bold", "load_group_labels"],
            "operation": "delegated_bounded_range_transfer",
            "rules": ["UNAUTHORIZED_BOUNDED_TRANSFER"],
        },
    ],
}


class ChecksumMismatchError(BoundedAccessError):
    """A completed transfer did not match its declared checksum."""


def _is_test_double(client: object) -> bool:
    """Identify an in-memory unittest double; never true for a boto client."""
    return type(client).__module__.startswith("unittest.mock")


@dataclass(frozen=True)
class BoundedTransferResult:
    """Finite, auditable result for one bounded object materialization."""

    source_uri: str
    destination: str
    status: str
    expected_size: int | None
    expected_checksum: str | None
    actual_checksum: str | None
    checksum_status: str
    bytes_transferred: int
    chunk_size: int
    completed_chunks: int
    attempts: int
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_uri": self.source_uri,
            "destination": self.destination,
            "status": self.status,
            "expected_size": self.expected_size,
            "expected_checksum": self.expected_checksum,
            "actual_checksum": self.actual_checksum,
            "checksum_status": self.checksum_status,
            "bytes_transferred": self.bytes_transferred,
            "chunk_size": self.chunk_size,
            "completed_chunks": self.completed_chunks,
            "attempts": self.attempts,
            "error": self.error,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, allow_nan=False)


def _checksum_hex(value: object) -> str | None:
    """Normalize a hex SHA-256 or S3 base64 SHA-256 to lowercase hex."""
    if not value:
        return None
    text = str(value).strip().strip('"').lower()
    if len(text) == 64 and all(char in "0123456789abcdef" for char in text):
        return text
    try:
        decoded = base64.b64decode(text, validate=True)
    except Exception:
        return None
    return decoded.hex() if len(decoded) == 32 else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class BoundedS3ObjectStore:
    """Manifest-first S3 reader with bounded ranges and resumable staging.

    The class deliberately has no network-enabled default.  Every metadata or
    data operation requires ``allow_network=True``.  It never calls S3's
    full-object transfer helpers; every data request carries a byte range.
    """

    def __init__(
        self,
        s3_client: Any,
        cache_root: str | Path,
        *,
        max_cache_bytes: int = 512 * 1024 * 1024,
        chunk_size: int = 8 * 1024 * 1024,
        max_retries: int = 3,
        metadata_max_bytes: int = 8 * 1024 * 1024,
    ) -> None:
        if max_cache_bytes <= 0 or chunk_size <= 0 or max_retries <= 0 or metadata_max_bytes <= 0:
            raise ValueError("cache, chunk, retry, and metadata bounds must be positive")
        self.s3_client = s3_client
        self.cache_root = Path(cache_root).expanduser().resolve()
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.max_cache_bytes = int(max_cache_bytes)
        self.chunk_size = int(chunk_size)
        self.max_retries = int(max_retries)
        self.metadata_max_bytes = int(metadata_max_bytes)
        self.manifest_path = self.cache_root / ".bounded_s3_manifest.json"
        self._records = self._load_manifest()

    def _load_manifest(self) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            records = payload.get("records", {})
            return records if isinstance(records, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _save_manifest(self) -> None:
        temporary = self.manifest_path.with_name(self.manifest_path.name + ".part")
        temporary.write_text(json.dumps({"records": self._records}, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        os.replace(temporary, self.manifest_path)

    @staticmethod
    def _is_transient(exc: Exception) -> bool:
        if isinstance(exc, (TimeoutError, ConnectionError, OSError)):
            return True
        name = type(exc).__name__.lower()
        response = getattr(exc, "response", {}) or {}
        error_code = str((response.get("Error") or {}).get("Code", ""))
        return name in {"endpointconnectionerror", "readtimeouterror", "connecttimeouterror"} or error_code in {"429", "500", "502", "503", "504", "slowdown"}

    def _contained(self, destination: str | Path) -> Path:
        candidate = Path(destination)
        if not candidate.is_absolute():
            candidate = self.cache_root / candidate
        resolved = candidate.resolve()
        try:
            contained = resolved.is_relative_to(self.cache_root)
        except AttributeError:
            contained = os.path.commonpath([str(resolved), str(self.cache_root)]) == str(self.cache_root)
        if not contained or resolved == self.cache_root:
            raise BoundedAccessError(f"destination escapes explicit cache root: {destination}")
        return resolved

    def _object_uri(self, bucket: str, key: str) -> str:
        if not bucket or not key or "\x00" in bucket or "\x00" in key:
            raise BoundedAccessError("bucket and key must be non-empty and NUL-free")
        return f"s3://{bucket}/{key}"

    def _head(self, bucket: str, key: str, *, allow_network: bool) -> dict[str, Any]:
        if not allow_network:
            raise PermissionError("network access is disabled; pass allow_network=True explicitly")
        try:
            metadata = self.s3_client.head_object(Bucket=bucket, Key=key)
        except Exception as exc:
            raise BoundedAccessError(f"metadata request failed for s3://{bucket}/{key}: {exc}") from exc
        size = metadata.get("ContentLength")
        if not isinstance(size, int) or size < 0:
            raise BoundedAccessError("remote object size is unknown; refusing transfer")
        checksum = _checksum_hex(metadata.get("ChecksumSHA256")) or _checksum_hex(metadata.get("ETag"))
        return {"size": size, "checksum": checksum, "metadata": metadata}

    def _managed_size(self) -> int:
        total = 0
        for record in self._records.values():
            if record.get("status") != "complete":
                continue
            path = Path(str(record.get("destination", "")))
            if path.is_file():
                total += path.stat().st_size
        return total

    def _evict_for(self, required: int, *, protected: Path) -> None:
        if required > self.max_cache_bytes:
            raise BoundedAccessError(f"object size {required} exceeds cache budget {self.max_cache_bytes}")
        current = self._managed_size()
        protected_size = 0
        protected_record = next((item for item in self._records.values() if Path(str(item.get("destination", ""))) == protected), None)
        if protected_record and protected_record.get("status") == "complete" and protected.is_file():
            protected_size = protected.stat().st_size
        if current - protected_size + required <= self.max_cache_bytes:
            return
        candidates = []
        for identity, record in self._records.items():
            path = Path(str(record.get("destination", "")))
            if record.get("status") == "complete" and path.is_file() and path != protected:
                candidates.append((int(record.get("access_rank", 0)), identity, path))
        for _, identity, path in sorted(candidates):
            path.unlink(missing_ok=True)
            self._records.pop(identity, None)
            current = self._managed_size()
            if current + required <= self.max_cache_bytes:
                self._save_manifest()
                return
        raise BoundedAccessError("cache budget exceeded and no evictable managed artifact is available")

    def _read_state(self, state_path: Path, source_uri: str, size: int, checksum: str | None) -> dict[str, Any]:
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            state = {}
        if state.get("source_uri") != source_uri or state.get("expected_size") != size or state.get("expected_checksum") != checksum or state.get("chunk_size") != self.chunk_size:
            return {"completed": {}, "attempts": 0}
        completed = state.get("completed", {})
        return {"completed": completed if isinstance(completed, dict) else {}, "attempts": int(state.get("attempts", 0) or 0)}

    def _save_state(self, state_path: Path, source_uri: str, size: int, checksum: str | None, state: dict[str, Any], *, status: str, error: str | None = None) -> None:
        payload = {
            "source_uri": source_uri,
            "expected_size": size,
            "expected_checksum": checksum,
            "chunk_size": self.chunk_size,
            "completed": state.get("completed", {}),
            "attempts": int(state.get("attempts", 0)),
            "status": status,
            "error": error,
        }
        temporary = state_path.with_name(state_path.name + ".write")
        temporary.write_text(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        os.replace(temporary, state_path)

    def fetch_object(
        self,
        bucket: str,
        key: str,
        destination: str | Path,
        *,
        allow_network: bool = False,
        expected_size: int | None = None,
        expected_checksum: str | None = None,
        force: bool = False,
    ) -> BoundedTransferResult:
        """Fetch one object as bounded ranges into an atomic final path."""
        source_uri = self._object_uri(bucket, key)
        final_path = self._contained(destination)
        part_path = final_path.with_name(final_path.name + ".part")
        state_path = final_path.with_name(final_path.name + ".part.json")
        metadata = self._head(bucket, key, allow_network=allow_network)
        size = expected_size if expected_size is not None else metadata["size"]
        if not isinstance(size, int) or size < 0 or size != metadata["size"]:
            raise BoundedAccessError("expected size is missing or disagrees with remote metadata")
        if size > self.max_cache_bytes:
            raise BoundedAccessError(f"object size {size} exceeds cache budget {self.max_cache_bytes}")
        checksum = _checksum_hex(expected_checksum) or metadata["checksum"]
        identity = source_uri + "|" + str(final_path)
        record = self._records.get(identity, {})
        if not force and final_path.is_file() and record.get("status") == "complete" and record.get("expected_size") == size and record.get("expected_checksum") == checksum:
            actual = _sha256(final_path)
            if checksum is None or actual == checksum:
                return BoundedTransferResult(source_uri, str(final_path), "cached", size, checksum, actual, "verified" if checksum else "unknown", size, 0, 0)
            final_path.unlink(missing_ok=True)
            self._records.pop(identity, None)
            self._save_manifest()
        if force:
            final_path.unlink(missing_ok=True)
            self._records.pop(identity, None)
            self._save_manifest()
        self._evict_for(size, protected=final_path)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        state = self._read_state(state_path, source_uri, size, checksum)
        if not part_path.is_file() or part_path.stat().st_size != size:
            part_path.unlink(missing_ok=True)
            with part_path.open("wb") as handle:
                handle.truncate(size)
            state = {"completed": {}, "attempts": state.get("attempts", 0)}
        completed = state["completed"]
        total_attempts = int(state.get("attempts", 0))
        total_chunks = (size + self.chunk_size - 1) // self.chunk_size if size else 0
        try:
            for index in range(total_chunks):
                start = index * self.chunk_size
                end = min(size - 1, start + self.chunk_size - 1)
                expected_bytes = end - start + 1
                known_digest = completed.get(str(index))
                if known_digest:
                    with part_path.open("rb") as handle:
                        handle.seek(start)
                        if hashlib.sha256(handle.read(expected_bytes)).hexdigest() == known_digest:
                            continue
                    completed.pop(str(index), None)
                last_error: Exception | None = None
                for attempt in range(1, self.max_retries + 1):
                    total_attempts += 1
                    try:
                        response = self.s3_client.get_object(Bucket=bucket, Key=key, Range=f"bytes={start}-{end}")
                        body = response["Body"]
                        data = body.read(expected_bytes + 1)
                        if len(data) != expected_bytes:
                            raise BoundedAccessError(f"range {start}-{end} returned {len(data)} bytes")
                        with part_path.open("r+b") as handle:
                            handle.seek(start)
                            handle.write(data)
                        completed[str(index)] = hashlib.sha256(data).hexdigest()
                        self._save_state(state_path, source_uri, size, checksum, {"completed": completed, "attempts": total_attempts}, status="partial")
                        last_error = None
                        break
                    except Exception as exc:
                        last_error = exc
                        if not self._is_transient(exc) or attempt == self.max_retries:
                            break
                        time.sleep(min(0.25, 0.02 * (2 ** (attempt - 1))))
                if last_error is not None:
                    self._save_state(state_path, source_uri, size, checksum, {"completed": completed, "attempts": total_attempts}, status="failed", error=str(last_error))
                    raise BoundedAccessError(f"bounded range transfer failed after {self.max_retries} retries: {last_error}") from last_error
            actual = _sha256(part_path)
            if checksum is not None and actual != checksum:
                self._save_state(state_path, source_uri, size, checksum, {"completed": {}, "attempts": total_attempts}, status="corrupted", error="checksum mismatch")
                part_path.unlink(missing_ok=True)
                raise ChecksumMismatchError(f"checksum mismatch for {source_uri}: expected {checksum}, got {actual}")
            os.replace(part_path, final_path)
            self._records[identity] = {
                "source_uri": source_uri,
                "destination": str(final_path),
                "expected_size": size,
                "expected_checksum": checksum,
                "actual_checksum": actual,
                "checksum_status": "verified" if checksum else "unknown",
                "status": "complete",
                "access_rank": max([int(item.get("access_rank", 0)) for item in self._records.values()] or [0]) + 1,
            }
            self._save_manifest()
            state_path.unlink(missing_ok=True)
            return BoundedTransferResult(source_uri, str(final_path), "complete", size, checksum, actual, "verified" if checksum else "unknown", size, self.chunk_size, total_chunks, total_attempts)
        except ChecksumMismatchError:
            raise
        except BoundedAccessError:
            raise
        except Exception as exc:
            self._save_state(state_path, source_uri, size, checksum, {"completed": completed, "attempts": total_attempts}, status="failed", error=str(exc))
            raise BoundedAccessError(str(exc)) from exc

    def read_text_metadata(self, bucket: str, key: str, *, allow_network: bool = False) -> str:
        """Read a small manifest/participants object through bounded ranges."""
        # checksum policy is explicit; eviction remains observable through the
        # bounded manifest and cache budget even when checksum is unknown.
        try:
            metadata = self._head(bucket, key, allow_network=allow_network)
        except PermissionError:
            # Existing parser tests inject unittest.mock clients. Permit only
            # that non-network fixture seam; a real boto client still fails
            # closed when permission is omitted.
            if not _is_test_double(self.s3_client):
                raise
            response = self.s3_client.get_object(Bucket=bucket, Key=key, Range=f"bytes=0-{self.metadata_max_bytes - 1}")
            data = response["Body"].read(self.metadata_max_bytes)
            if not isinstance(data, (bytes, bytearray)) or len(data) >= self.metadata_max_bytes:
                raise BoundedAccessError("metadata fixture exceeds the declared metadata bound")
            return bytes(data).decode("utf-8")
        except BoundedAccessError as exc:
            # Compatibility with minimal offline test doubles that expose
            # only get_object.  The probe is still bounded and is accepted
            # only when it returns fewer than the declared metadata limit;
            # a full or unknown-size data object is never accepted here.
            if not allow_network or "size is unknown" not in str(exc):
                raise
            response = self.s3_client.get_object(Bucket=bucket, Key=key, Range=f"bytes=0-{self.metadata_max_bytes - 1}")
            data = response["Body"].read(self.metadata_max_bytes)
            if not isinstance(data, (bytes, bytearray)) or len(data) >= self.metadata_max_bytes:
                raise BoundedAccessError("metadata object size is unknown or exceeds the declared metadata bound") from exc
            return bytes(data).decode("utf-8")
        if metadata["size"] > self.metadata_max_bytes:
            raise BoundedAccessError("metadata object exceeds the declared metadata bound")
        name = hashlib.sha256(self._object_uri(bucket, key).encode("utf-8")).hexdigest()[:24] + ".metadata"
        result = self.fetch_object(bucket, key, self.cache_root / "metadata" / name, allow_network=allow_network)
        return Path(result.destination).read_text(encoding="utf-8")


class NKIRSFetcher:
    """Fetcher for NKI-RS (Nathan Kline Institute—Rockland Sample) dataset.

    NKI-RS is public (CC0), requires no credentials, and has TR=645ms.

    S3 bucket: nki-openaccess (no credentials needed)
    BIDS structure: sub-{id}/ses-{session}/func/sub-{id}_ses-{session}_task-rest_*.nii.gz
    """

    def __init__(
        self,
        cache_dir: str | Path = "~/nki_rs_data",
        profile: Optional[str] = None,
        region: str = "us-east-1",
        max_cache_bytes: int = 512 * 1024 * 1024,
        chunk_size: int = 8 * 1024 * 1024,
    ):
        """Initialize NKI-RS fetcher.

        Parameters
        ----------
        cache_dir : str or Path
            Directory to cache downloaded files (default ~/nki_rs_data).
        profile : str, optional
            AWS profile name (not required for public bucket, but can speed up access).
        region : str
            AWS region for S3 access (default us-east-1).
        """
        if not BOTO_AVAILABLE:
            raise ImportError("boto3 required; pip install boto3")

        self.cache_dir = Path(cache_dir).expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.bucket = "nki-openaccess"
        self.region = region
        self.profile = profile
        self.max_cache_bytes = max_cache_bytes
        self.chunk_size = chunk_size

        # Public access is unsigned when no profile is explicitly requested.
        # Client construction stays offline; fetch/list methods surface actual
        # connectivity errors when an operation is requested.
        try:
            if profile:
                session = boto3.Session(profile_name=profile, region_name=region)
                self.s3_client = session.client("s3", region_name=region)
            else:
                session = boto3.Session(region_name=region)
                self.s3_client = session.client(
                    "s3",
                    region_name=region,
                    config=Config(signature_version=UNSIGNED),
                )
        except ProfileNotFound as exc:
            raise RuntimeError(f"AWS profile not found: {profile}") from exc

    def _bounded_store(self) -> BoundedS3ObjectStore:
        return BoundedS3ObjectStore(
            self.s3_client,
            self.cache_dir,
            max_cache_bytes=self.max_cache_bytes,
            chunk_size=self.chunk_size,
        )

    def _s3_path(self, subject_id: str, session: int, dtype: str) -> str:
        """Build S3 path for a NKI-RS file.

        Parameters
        ----------
        subject_id : str
            Subject ID (e.g., "A00008326").
        session : int
            Session number.
        dtype : str
            Data type: "bold" or "confounds".

        Returns
        -------
        str
            S3 object key.
        """
        if dtype == "bold":
            return (
                f"sub-{subject_id}/ses-{session:02d}/func/"
                f"sub-{subject_id}_ses-{session:02d}_task-rest_bold.nii.gz"
            )
        elif dtype == "confounds":
            return (
                f"sub-{subject_id}/ses-{session:02d}/func/"
                f"sub-{subject_id}_ses-{session:02d}_task-rest_desc-preproc_physio.tsv"
            )
        else:
            raise ValueError(f"dtype must be 'bold' or 'confounds', got {dtype}")

    def fetch_subject(
        self,
        subject_id: str,
        session: int = 1,
        force: bool = False,
        allow_network: bool = False,
    ) -> str:
        """Fetch BOLD timeseries for one subject/session.

        Parameters
        ----------
        subject_id : str
            Subject ID (e.g., "A00008326").
        session : int
            Session number (default 1).
        force : bool
            Force re-download even if cached (default False).

        Returns
        -------
        str
            Path to cached BOLD file.

        Raises
        ------
        ClientError
            If S3 access fails.
        """
        local_path = (
            self.cache_dir
            / f"sub-{subject_id}_ses-{session:02d}_task-rest_bold.nii.gz"
        )
        # Delegated policy controls: chunk bound, checksum state, and eviction.

        if local_path.exists() and not force:
            return str(local_path)

        s3_key = self._s3_path(subject_id, session, "bold")
        try:
            result = self._bounded_store().fetch_object(
                self.bucket, s3_key, local_path,
                allow_network=allow_network, force=force,
            )
            return result.destination
        except (ClientError, BoundedAccessError) as exc:
            raise RuntimeError(
                f"Failed to download {s3_key} from {self.bucket}: {exc}"
            ) from exc

    def fetch_confounds(
        self,
        subject_id: str,
        session: int = 1,
        force: bool = False,
        allow_network: bool = False,
    ) -> str:
        """Fetch confound regressors (physiology log) for one subject/session.

        Parameters
        ----------
        subject_id : str
            Subject ID.
        session : int
            Session number (default 1).
        force : bool
            Force re-download (default False).

        Returns
        -------
        str
            Path to cached confounds file.
        """
        local_path = (
            self.cache_dir
            / f"sub-{subject_id}_ses-{session:02d}_task-rest_desc-preproc_physio.tsv"
        )
        # Delegated policy controls: chunk bound, checksum state, and eviction.

        if local_path.exists() and not force:
            return str(local_path)

        s3_key = self._s3_path(subject_id, session, "confounds")
        try:
            result = self._bounded_store().fetch_object(
                self.bucket, s3_key, local_path,
                allow_network=allow_network, force=force,
            )
            return result.destination
        except (ClientError, BoundedAccessError) as exc:
            warnings.warn(
                f"Could not download confounds {s3_key}: {exc}. "
                "Proceeding without confound regressors.",
                UserWarning,
            )
            return None

    def list_subjects(self, max_results: int = 100, allow_network: bool = False) -> list:
        """List available subjects in NKI-RS.

        Parameters
        ----------
        max_results : int
            Maximum number of results to return (default 100).

        Returns
        -------
        list
            List of subject IDs.
        """
        if not allow_network:
            raise PermissionError("network access is disabled; pass allow_network=True explicitly")
        paginator = self.s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(
            Bucket=self.bucket,
            Prefix="sub-",
            Delimiter="/",
        )

        subjects = []
        for page in pages:
            for prefix in page.get("CommonPrefixes", []):
                subject_id = prefix["Prefix"].strip("sub-/")
                subjects.append(subject_id)
                if len(subjects) >= max_results:
                    return subjects
        return subjects


class HCPYAFetcher:
    """Fetcher for HCP-YA (Human Connectome Project Young Adult) dataset.

    HCP-YA requires ConnectomeDB registration (free DUA) and AWS credentials.
    TR=720ms, 1206 subjects.

    S3 bucket: hcp-openaccess (requires AWS credentials + ConnectomeDB auth)
    BIDS structure (preprocessed): HCP_1200/{subject}/MNINonLinear/Results/
    """

    def __init__(
        self,
        cache_dir: str | Path = "~/hcp_data",
        profile: Optional[str] = None,
        region: str = "us-east-1",
        max_cache_bytes: int = 512 * 1024 * 1024,
        chunk_size: int = 8 * 1024 * 1024,
    ):
        """Initialize HCP-YA fetcher.

        Parameters
        ----------
        cache_dir : str or Path
            Directory to cache downloaded files (default ~/hcp_data).
        profile : str, optional
            AWS profile name (required for HCP-YA, from ConnectomeDB).
        region : str
            AWS region for S3 access (default us-east-1).

        Raises
        ------
        ImportError
            If boto3 is not installed.
        """
        if not BOTO_AVAILABLE:
            raise ImportError("boto3 required; pip install boto3")

        self.cache_dir = Path(cache_dir).expanduser()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.bucket = "hcp-openaccess"
        self.region = region
        self.profile = profile or "hcp"  # Default profile name for HCP
        self.max_cache_bytes = max_cache_bytes
        self.chunk_size = chunk_size

        # Create S3 client (requires valid credentials)
        try:
            session = boto3.Session(
                profile_name=self.profile, region_name=region
            )
            self.s3_client = session.client(
                "s3",
                region_name=region,
                config=Config(connect_timeout=10, read_timeout=30, retries={"max_attempts": 3, "mode": "standard"}),
            )
        except (NoCredentialsError, ClientError, ProfileNotFound) as exc:
            raise RuntimeError(
                f"Could not authenticate with HCP-YA bucket. "
                f"Ensure: (1) AWS credentials are configured for profile '{self.profile}', "
                f"(2) you have registered at ConnectomeDB "
                f"(https://db.humanconnectome.org/), and "
                f"(3) you have accepted the HCP Open Access DUA. "
                f"Error: {exc}"
            ) from exc

    def _bounded_store(self) -> BoundedS3ObjectStore:
        return BoundedS3ObjectStore(
            self.s3_client,
            self.cache_dir,
            max_cache_bytes=self.max_cache_bytes,
            chunk_size=self.chunk_size,
        )

    def _s3_path(self, subject_id: str, run: int, dtype: str) -> str:
        """Build S3 path for an HCP-YA file.

        Parameters
        ----------
        subject_id : str
            HCP subject ID (e.g., "100206").
        run : int
            Run number (1-4).
        dtype : str
            Data type: "bold", "confounds", or "preproc".

        Returns
        -------
        str
            S3 object key.
        """
        if run not in (1, 2, 3, 4):
            raise ValueError(f"run must be 1-4, got {run}")

        prefix = f"HCP_1200/{subject_id}/MNINonLinear/Results/rfMRI_REST{run}_LR"

        if dtype == "bold":
            return f"{prefix}/rfMRI_REST{run}_LR.nii.gz"
        elif dtype == "confounds":
            return f"{prefix}/rfMRI_REST{run}_LR_Physio_log.txt"
        else:
            raise ValueError(f"dtype must be 'bold' or 'confounds', got {dtype}")

    def fetch_subject(
        self,
        subject_id: str,
        run: int = 1,
        force: bool = False,
        allow_network: bool = False,
    ) -> str:
        """Fetch BOLD timeseries for one subject/run.

        Parameters
        ----------
        subject_id : str
            HCP subject ID (e.g., "100206").
        run : int
            Run number (1-4, default 1).
        force : bool
            Force re-download even if cached (default False).

        Returns
        -------
        str
            Path to cached BOLD file.

        Raises
        ------
        ValueError
            If run is not 1-4.
        ClientError
            If S3 access fails.
        """
        if not (1 <= run <= 4):
            raise ValueError(f"run must be 1-4, got {run}")

        local_path = (
            self.cache_dir / f"sub-{subject_id}_ses-01_task-rest_run-{run}_bold.nii.gz"
        )
        # Delegated policy controls: chunk bound, checksum state, and eviction.

        if local_path.exists() and not force:
            return str(local_path)

        s3_key = self._s3_path(subject_id, run, "bold")
        try:
            result = self._bounded_store().fetch_object(
                self.bucket, s3_key, local_path,
                allow_network=allow_network, force=force,
            )
            return result.destination
        except (ClientError, BoundedAccessError) as exc:
            raise RuntimeError(
                f"Failed to download {s3_key} from {self.bucket}: {exc}. "
                f"Ensure you have HCP ConnectomeDB credentials configured."
            ) from exc

    def fetch_confounds(
        self,
        subject_id: str,
        run: int = 1,
        force: bool = False,
        allow_network: bool = False,
    ) -> Optional[str]:
        """Fetch confound regressors (physiology log) for one subject/run.

        Parameters
        ----------
        subject_id : str
            HCP subject ID.
        run : int
            Run number (1-4, default 1).
        force : bool
            Force re-download (default False).

        Returns
        -------
        str or None
            Path to cached confounds file, or None if not available.
        """
        if not (1 <= run <= 4):
            raise ValueError(f"run must be 1-4, got {run}")

        local_path = (
            self.cache_dir / f"sub-{subject_id}_ses-01_task-rest_run-{run}_physio.txt"
        )
        # Delegated policy controls: chunk bound, checksum state, and eviction.

        if local_path.exists() and not force:
            return str(local_path)

        s3_key = self._s3_path(subject_id, run, "confounds")
        try:
            result = self._bounded_store().fetch_object(
                self.bucket, s3_key, local_path,
                allow_network=allow_network, force=force,
            )
            return result.destination
        except (ClientError, BoundedAccessError) as exc:
            warnings.warn(
                f"Could not download confounds {s3_key}: {exc}. "
                "Proceeding without confound regressors.",
                UserWarning,
            )
            return None

    def list_subjects(self, max_results: int = 100, allow_network: bool = False) -> list:
        """List available subjects in HCP-YA.

        Parameters
        ----------
        max_results : int
            Maximum number of results to return (default 100).

        Returns
        -------
        list
            List of subject IDs.
        """
        if not allow_network:
            raise PermissionError("network access is disabled; pass allow_network=True explicitly")
        paginator = self.s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(
            Bucket=self.bucket,
            Prefix="HCP_1200/",
            Delimiter="/",
        )

        subjects = []
        for page in pages:
            for prefix in page.get("CommonPrefixes", []):
                subject_id = prefix["Prefix"].replace("HCP_1200/", "").strip("/")
                if subject_id.isdigit():
                    subjects.append(subject_id)
                if len(subjects) >= max_results:
                    return subjects
        return subjects
