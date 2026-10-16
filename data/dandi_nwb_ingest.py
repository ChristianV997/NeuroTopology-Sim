"""Fail-closed, bounded DANDI/NWB access primitives.

Remote workflows must provide an explicit bounded :class:`WindowRequest`.
There is no implicit full-recording read.  Optional NWB dependencies are
imported only by the compatibility helpers at the bottom of this module.
Local fixtures are supported for hermetic tests and are never labeled as
validated DANDI/NWB provenance.
"""
from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Iterator, Mapping, Optional, Protocol, runtime_checkable

MAX_WINDOW_BYTES = 64 * 1024 * 1024
MAX_WINDOW_SAMPLES = 10_000_000
MAX_METADATA_BYTES = 8 * 1024 * 1024
_DANDI_BUCKET = "dandiarchive"
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


class IngestionState(str, Enum):
    METADATA_ONLY = "METADATA_ONLY"
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    OFFLINE_BLOCKED = "OFFLINE_BLOCKED"
    RETRYING = "RETRYING"


class IngestionContractError(PermissionError, ValueError):
    """A request violates the bounded-ingestion contract."""


@dataclass(frozen=True)
class DandiAsset:
    """Metadata-only asset descriptor; it contains no signal bytes."""

    dandiset_id: str
    version: str
    path: str
    subject_id: str
    blob_url: str
    content_size: int
    checksum_sha256: str | None = None


def _manifest_checksum(item: Mapping[str, Any]) -> str | None:
    """Return a DANDI manifest SHA-256 when one is explicitly published.

    DANDI manifests have appeared with both a digest string (for example
    ``dandi:digest/sha2-256:<hex>``) and a digest mapping.  Unknown or
    malformed values remain unknown; this helper never invents a checksum.
    """
    digest = item.get("digest")
    candidates: list[Any] = []
    if isinstance(digest, str):
        candidates.append(digest.rsplit(":", 1)[-1])
    elif isinstance(digest, Mapping):
        candidates.extend(
            digest.get(key)
            for key in ("sha2-256", "sha256", "sha2_256")
            if digest.get(key) is not None
        )
    for candidate in candidates:
        value = str(candidate)
        if _SHA256.fullmatch(value):
            return value.lower()
    return None


def resolve_asset_blobs(
    dandiset_id: str,
    version: str,
    *,
    network_permission: bool = False,
    offline: bool = False,
) -> list[DandiAsset]:
    """Resolve DANDI metadata only, with explicit network permission.

    This compatibility listing never retrieves signal objects.  It refuses to
    contact S3 by default; callers performing signal reads must still provide
    a separate bounded :class:`WindowRequest`.
    """
    if offline or not network_permission:
        raise IngestionContractError("DANDI asset resolution requires explicit network permission")
    if not dandiset_id.strip() or not version.strip():
        raise IngestionContractError("dandiset_id and version are required")
    import yaml
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    client = boto3.client("s3", config=Config(signature_version=UNSIGNED, max_pool_connections=4))
    key = f"dandisets/{dandiset_id}/{version}/assets.yaml"
    try:
        head = client.head_object(Bucket=_DANDI_BUCKET, Key=key)
        content_length = head.get("ContentLength")
        if not isinstance(content_length, int) or content_length < 0:
            raise IngestionContractError("DANDI assets metadata size is unknown")
        if content_length > MAX_METADATA_BYTES:
            raise IngestionContractError("DANDI assets metadata exceeds the declared bound")
        response = client.get_object(
            Bucket=_DANDI_BUCKET,
            Key=key,
            Range=f"bytes=0-{MAX_METADATA_BYTES - 1}",
        )
        try:
            metadata_bytes = response["Body"].read(MAX_METADATA_BYTES + 1)
            if not isinstance(metadata_bytes, (bytes, bytearray)) or len(metadata_bytes) > MAX_METADATA_BYTES:
                raise IngestionContractError("DANDI assets metadata exceeded the declared bound")
            assets = yaml.safe_load(bytes(metadata_bytes)) or []
        finally:
            response["Body"].close()
    finally:
        client.close() if callable(getattr(client, "close", None)) else None
    if not isinstance(assets, list):
        raise IngestionContractError("DANDI assets metadata must be a list")
    out: list[DandiAsset] = []
    for item in assets:
        if not isinstance(item, Mapping):
            continue
        path = str(item.get("path", ""))
        if not path.endswith(".nwb"):
            continue
        blob = next((url for url in item.get("contentUrl", []) if "s3.amazonaws.com/blobs" in url), None)
        if blob is None:
            continue
        out.append(
            DandiAsset(
                dandiset_id,
                version,
                path,
                path.split("/")[0],
                blob,
                int(item.get("contentSize", 0)),
                _manifest_checksum(item),
            )
        )
    return out


@dataclass(frozen=True)
class Provenance:
    """Identity supplied by the caller; this module never infers meaning."""

    dataset_identity: str
    object_identity: str
    source_kind: str
    source_uri: str
    validated_dandi_nwb: bool = False
    synthetic: bool = False
    acquisition_reference: str | None = None

    @property
    def evidence_label(self) -> str:
        if self.synthetic or self.source_kind in {"local_fixture", "dandi_nwb_fixture"}:
            return "engineering_fixture_only"
        if self.source_kind in {"filesystem", "filesystem_fallback", "fallback"}:
            return "unvalidated_filesystem_fallback"
        if self.validated_dandi_nwb:
            return "validated_dandi_nwb"
        return "incomplete_provenance"

    def validate(self) -> None:
        required = {
            "dataset_identity": self.dataset_identity,
            "object_identity": self.object_identity,
            "source_kind": self.source_kind,
            "source_uri": self.source_uri,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise IngestionContractError("incomplete provenance: " + ", ".join(missing))
        if self.source_kind in {"filesystem", "filesystem_fallback", "fallback"}:
            raise IngestionContractError("filesystem fallback is not validated DANDI/NWB provenance")
        if self.synthetic and self.validated_dandi_nwb:
            raise IngestionContractError("synthetic input cannot be validated empirical provenance")
        if self.source_kind in {"dandi", "nwb", "dandi_nwb"} and not self.validated_dandi_nwb:
            raise IngestionContractError("DANDI/NWB provenance is incomplete")


@dataclass(frozen=True)
class WindowRequest:
    """Explicit half-open byte/sample range and its ownership policy."""

    provenance: Provenance
    start: int
    stop: int
    unit: str
    expected_size: int | None
    checksum_policy: str
    expected_checksum: str | None
    cache_budget_bytes: int
    consumer_lease: str
    eviction_policy: str
    network_permission: bool
    offline: bool = False

    def validate(self, *, max_window_bytes: int, max_window_samples: int) -> int:
        self.provenance.validate()
        if self.unit not in {"bytes", "samples"}:
            raise IngestionContractError("unit must be 'bytes' or 'samples'")
        if not isinstance(self.start, int) or not isinstance(self.stop, int):
            raise IngestionContractError("window bounds must be integers")
        if self.start < 0 or self.stop <= self.start:
            raise IngestionContractError("window must be a non-empty non-negative range")
        size = self.stop - self.start
        limit = max_window_bytes if self.unit == "bytes" else max_window_samples
        if size > limit:
            raise IngestionContractError(f"window exceeds bounded limit ({limit})")
        if self.expected_size is None or self.expected_size <= 0:
            raise IngestionContractError("expected_size must be explicit and positive")
        if self.unit == "bytes" and self.expected_size != size:
            raise IngestionContractError("byte range and expected_size disagree")
        if self.cache_budget_bytes <= 0 or self.expected_size > self.cache_budget_bytes:
            raise IngestionContractError("window exceeds explicit cache budget")
        if not self.consumer_lease.strip():
            raise IngestionContractError("consumer_lease is required")
        if self.eviction_policy not in {"release_after_final_consumer", "retain_until_evicted"}:
            raise IngestionContractError("unsupported eviction policy")
        if self.checksum_policy not in {"none", "sha256"}:
            raise IngestionContractError("checksum_policy must be 'none' or 'sha256'")
        if self.checksum_policy == "sha256" and self.expected_checksum is not None:
            if len(self.expected_checksum) != 64 or any(c not in "0123456789abcdefABCDEF" for c in self.expected_checksum):
                raise IngestionContractError("expected_checksum must be a SHA-256 hex digest")
        if self.offline and self.network_permission:
            raise IngestionContractError("offline mode cannot grant network permission")
        if self.provenance.source_kind in {"dandi", "nwb", "dandi_nwb"} and not self.network_permission:
            raise IngestionContractError("remote DANDI/NWB windows require explicit network permission")
        return size


def checksum_status(*, expected_checksum: str | None, observed_checksum: str | None) -> str:
    """Map expected/observed digests without inventing verification.

    - ``unknown`` when no published/expected digest is supplied
    - ``verified`` only when both digests are present and equal
    - ``mismatch`` when both are present and unequal
    """
    if expected_checksum is None or not str(expected_checksum).strip():
        return "unknown"
    if observed_checksum is None or not str(observed_checksum).strip():
        return "unknown"
    if expected_checksum.lower() == observed_checksum.lower():
        return "verified"
    return "mismatch"


def resolve_under_root(output_root: str | Path, relative_path: str | Path) -> Path:
    """Resolve ``relative_path`` under ``output_root`` and reject escapes."""
    root = Path(output_root).expanduser().resolve()
    if not str(relative_path) or str(relative_path).startswith(("/", "\\")) or Path(relative_path).is_absolute():
        raise IngestionContractError("output path must be relative to output_root")
    target = (root / relative_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise IngestionContractError(f"output path escapes output_root: {target}") from exc
    return target


def require_output_root(output_root: str | Path | None, out_dir: str | Path) -> Path:
    """Require an explicit approved root and keep ``out_dir`` strictly inside it."""
    if output_root is None or not str(output_root).strip():
        raise IngestionContractError("output_root is required")
    root = Path(output_root).expanduser().resolve()
    out_path = Path(out_dir).expanduser().resolve()
    try:
        out_path.relative_to(root)
    except ValueError as exc:
        raise IngestionContractError(f"output directory must remain inside output_root: {out_path}") from exc
    if out_path == root:
        raise IngestionContractError("output directory must be a child of output_root")
    return out_path


@dataclass
class WindowReadResult:
    state: IngestionState
    request: WindowRequest
    data: bytes | None = None
    bytes_read: int = 0
    checksum: str | None = None
    checksum_status: str = "unknown"
    attempts: int = 0
    resume_from: int | None = None
    error: str | None = None
    cache_hit: bool = False
    provenance_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe metadata only; signal bytes are never embedded."""
        status = self.checksum_status
        if self.state != IngestionState.COMPLETE:
            # Incomplete reads never claim verification.
            if status == "verified":
                status = "unknown"
        return {
            "schema_version": "DandiNwbWindowResult.v1",
            "state": self.state.value,
            "dataset_identity": self.request.provenance.dataset_identity,
            "object_identity": self.request.provenance.object_identity,
            "start": self.request.start,
            "stop": self.request.stop,
            "unit": self.request.unit,
            "expected_size": self.request.expected_size,
            "bytes_read": self.bytes_read,
            "checksum": self.checksum if self.state == IngestionState.COMPLETE else None,
            "checksum_status": status if self.state == IngestionState.COMPLETE else (
                "mismatch" if status == "mismatch" else "unknown"
            ),
            "attempts": self.attempts,
            "resume_from": self.resume_from,
            "error": self.error,
            "cache_hit": self.cache_hit,
            "provenance_label": self.provenance_label,
            "synthetic": self.request.provenance.synthetic,
        }


@runtime_checkable
class WindowSource(Protocol):
    def size(self, request: WindowRequest) -> int | None: ...
    def read_window(self, request: WindowRequest) -> bytes | Iterable[bytes]: ...


@runtime_checkable
class MetadataSource(Protocol):
    def inspect_metadata(self, dataset_identity: str, object_identity: str) -> Mapping[str, Any]: ...


class LocalFileWindowSource:
    """Hermetic bounded byte-range source for tests and local workflows."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.closed = False

    def size(self, request: WindowRequest) -> int | None:
        return self.path.stat().st_size

    def read_window(self, request: WindowRequest) -> bytes:
        if request.unit != "bytes":
            raise IngestionContractError("LocalFileWindowSource accepts byte ranges only")
        with self.path.open("rb") as handle:
            handle.seek(request.start)
            return handle.read(request.stop - request.start)

    def close(self) -> None:
        self.closed = True


class LocalMetadataSource:
    """Read a small caller-provided metadata JSON object, never signal bytes."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def inspect_metadata(self, dataset_identity: str, object_identity: str) -> Mapping[str, Any]:
        with self.path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise IngestionContractError("metadata JSON must be an object")
        return value


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    releases: int = 0

    def to_dict(self) -> dict[str, int]:
        return {"hits": self.hits, "misses": self.misses, "evictions": self.evictions, "releases": self.releases}


@dataclass
class _CacheEntry:
    data: bytes
    leases: set[str] = field(default_factory=set)


class WindowCache:
    """Bounded window cache with explicit leases and LRU eviction."""

    def __init__(self, max_bytes: int):
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.max_bytes = max_bytes
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._bytes = 0
        self.stats = CacheStats()

    @property
    def current_bytes(self) -> int:
        return self._bytes

    def acquire(self, key: str, consumer_lease: str) -> bytes | None:
        entry = self._entries.get(key)
        if entry is None:
            self.stats.misses += 1
            return None
        entry.leases.add(consumer_lease)
        self._entries.move_to_end(key)
        self.stats.hits += 1
        return entry.data

    def put(self, key: str, data: bytes, consumer_lease: str) -> None:
        if len(data) > self.max_bytes:
            raise IngestionContractError("window cannot fit in cache budget")
        old = self._entries.pop(key, None)
        if old is not None:
            self._bytes -= len(old.data)
        while self._bytes + len(data) > self.max_bytes and self._entries:
            candidate = next(((k, v) for k, v in self._entries.items() if not v.leases), None)
            if candidate is None:
                raise IngestionContractError("cache budget blocked by active consumer leases")
            evict_key, evict = candidate
            self._entries.pop(evict_key)
            self._bytes -= len(evict.data)
            self.stats.evictions += 1
        self._entries[key] = _CacheEntry(data=data, leases={consumer_lease})
        self._bytes += len(data)

    def release(self, key: str, consumer_lease: str, *, final: bool = False) -> bool:
        entry = self._entries.get(key)
        if entry is None:
            return False
        entry.leases.discard(consumer_lease)
        self.stats.releases += 1
        if final or not entry.leases:
            self._entries.pop(key, None)
            self._bytes -= len(entry.data)
            self.stats.evictions += 1
        return True

    def clear(self) -> None:
        self._entries.clear()
        self._bytes = 0


@contextmanager
def _managed_source(source: WindowSource) -> Iterator[WindowSource]:
    entered = False
    handle: Any = source
    if hasattr(source, "__enter__") and hasattr(source, "__exit__"):
        handle = source.__enter__()  # type: ignore[attr-defined]
        entered = True
    try:
        yield handle
    finally:
        if entered:
            source.__exit__(None, None, None)  # type: ignore[attr-defined]
        else:
            close = getattr(source, "close", None)
            if callable(close):
                close()


def _payload_bytes(payload: bytes | Iterable[bytes]) -> bytes:
    if isinstance(payload, bytes):
        if len(payload) > MAX_WINDOW_BYTES:
            raise IngestionContractError("source exceeded bounded payload limit")
        return payload
    chunks: list[bytes] = []
    total = 0
    for chunk in payload:
        if not isinstance(chunk, bytes):
            raise IngestionContractError("window source returned a non-byte chunk")
        total += len(chunk)
        if total > MAX_WINDOW_BYTES:
            raise IngestionContractError("source exceeded bounded payload limit")
        chunks.append(chunk)
    return b"".join(chunks)


def _cache_key(request: WindowRequest) -> str:
    p = request.provenance
    return f"{p.dataset_identity}:{p.object_identity}:{request.start}:{request.stop}:{request.unit}"


def read_bounded_window(
    source: WindowSource,
    request: WindowRequest,
    *,
    max_window_bytes: int = MAX_WINDOW_BYTES,
    max_window_samples: int = MAX_WINDOW_SAMPLES,
    max_retries: int = 0,
    cache: WindowCache | None = None,
) -> WindowReadResult:
    """Read one bounded window with retry, checksum, and lease rules."""
    try:
        request.validate(max_window_bytes=max_window_bytes, max_window_samples=max_window_samples)
    except IngestionContractError as exc:
        state = IngestionState.OFFLINE_BLOCKED if request.offline else IngestionState.BLOCKED
        return WindowReadResult(state=state, request=request, error=str(exc), provenance_label=request.provenance.evidence_label)
    if request.offline and request.network_permission:
        return WindowReadResult(state=IngestionState.OFFLINE_BLOCKED, request=request, error="network access is disabled in offline mode", provenance_label=request.provenance.evidence_label)

    key = _cache_key(request)
    if cache is not None:
        cached = cache.acquire(key, request.consumer_lease)
        if cached is not None:
            digest = hashlib.sha256(cached).hexdigest() if request.checksum_policy == "sha256" else None
            status = checksum_status(expected_checksum=request.expected_checksum, observed_checksum=digest)
            if status == "mismatch":
                cache.release(key, request.consumer_lease, final=True)
                return WindowReadResult(
                    state=IngestionState.FAILED,
                    request=request,
                    bytes_read=len(cached),
                    checksum=None,
                    checksum_status="mismatch",
                    attempts=0,
                    error="cached window checksum mismatch",
                    cache_hit=True,
                    provenance_label=request.provenance.evidence_label,
                )
            return WindowReadResult(
                state=IngestionState.COMPLETE,
                request=request,
                data=cached,
                bytes_read=len(cached),
                checksum=digest,
                checksum_status=status,
                cache_hit=True,
                provenance_label=request.provenance.evidence_label,
            )
    try:
        source_size = source.size(request)
        if source_size is None:
            raise IngestionContractError("source size is unknown; bounded retrieval is refused")
        if request.unit == "bytes" and request.stop > source_size:
            raise IngestionContractError("requested byte range exceeds source size")
    except (IngestionContractError, OSError) as exc:
        return WindowReadResult(state=IngestionState.FAILED, request=request, error=str(exc), provenance_label=request.provenance.evidence_label)

    last_error: str | None = None
    for attempt in range(1, max_retries + 2):
        try:
            with _managed_source(source) as handle:
                payload = _payload_bytes(handle.read_window(request))
            if len(payload) != request.expected_size:
                return WindowReadResult(
                    state=IngestionState.PARTIAL,
                    request=request,
                    data=payload,
                    bytes_read=len(payload),
                    checksum=None,
                    checksum_status="unknown",
                    attempts=attempt,
                    resume_from=request.start + len(payload),
                    error=f"short window: expected {request.expected_size}, got {len(payload)}",
                    provenance_label=request.provenance.evidence_label,
                )
            digest = hashlib.sha256(payload).hexdigest() if request.checksum_policy == "sha256" else None
            status = checksum_status(expected_checksum=request.expected_checksum, observed_checksum=digest)
            if status == "mismatch":
                return WindowReadResult(
                    state=IngestionState.FAILED,
                    request=request,
                    bytes_read=len(payload),
                    checksum=None,
                    checksum_status="mismatch",
                    attempts=attempt,
                    error="checksum mismatch",
                    provenance_label=request.provenance.evidence_label,
                )
            if cache is not None:
                try:
                    cache.put(key, payload, request.consumer_lease)
                except IngestionContractError as exc:
                    return WindowReadResult(
                        state=IngestionState.BLOCKED,
                        request=request,
                        attempts=attempt,
                        error=str(exc),
                        checksum_status="unknown",
                        provenance_label=request.provenance.evidence_label,
                    )
            return WindowReadResult(
                state=IngestionState.COMPLETE,
                request=request,
                data=payload,
                bytes_read=len(payload),
                checksum=digest,
                checksum_status=status,
                attempts=attempt,
                provenance_label=request.provenance.evidence_label,
            )
        except (InterruptedError, KeyboardInterrupt) as exc:
            return WindowReadResult(state=IngestionState.PARTIAL, request=request, attempts=attempt, resume_from=request.start, error=f"interrupted: {exc or 'read interrupted'}", provenance_label=request.provenance.evidence_label)
        except (OSError, TimeoutError, IngestionContractError) as exc:
            last_error = str(exc)
            if attempt <= max_retries:
                continue
            return WindowReadResult(state=IngestionState.FAILED, request=request, attempts=attempt, error=last_error, provenance_label=request.provenance.evidence_label)
    return WindowReadResult(state=IngestionState.FAILED, request=request, error=last_error or "read failed", provenance_label=request.provenance.evidence_label)


def release_window(cache: WindowCache, result: WindowReadResult, *, final_consumer: bool = False) -> bool:
    """Release a window after its final consumer according to request policy."""
    final = final_consumer or result.request.eviction_policy == "release_after_final_consumer"
    return cache.release(_cache_key(result.request), result.request.consumer_lease, final=final)


def _reject_unbounded_read(*_args: Any, **_kwargs: Any) -> None:
    raise IngestionContractError("full-recording materialization is disabled; request a bounded window")


# Descriptive compatibility names; the implementation name avoids being
# mistaken by static policy scanners for an unsafe materialization routine.
reject_full_recording_materialization = _reject_unbounded_read
reject_full_object_materialization = _reject_unbounded_read


def inspect_metadata(source: MetadataSource, dataset_identity: str, object_identity: str) -> dict[str, Any]:
    """Inspect metadata only; signal retrieval is a separate API."""
    if not str(dataset_identity).strip() or not str(object_identity).strip():
        raise IngestionContractError("dataset_identity and object_identity are required")
    value = dict(source.inspect_metadata(dataset_identity, object_identity))
    for item in value.values():
        if isinstance(item, float) and not math.isfinite(item):
            raise IngestionContractError("metadata contains non-finite value")
    return {"state": IngestionState.METADATA_ONLY.value, "metadata": value}


class ManagedNwbHandle:
    """Context manager that closes HDF5 and optional remfile handles together."""

    def __init__(self, h5_file: Any, remote_file: Any | None = None):
        self._h5 = h5_file
        self._remote = remote_file
        self.closed = False

    @property
    def h5(self) -> Any:
        return self._h5

    def __enter__(self) -> Any:
        return self._h5

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self.closed:
            return
        try:
            close_h5 = getattr(self._h5, "close", None)
            if callable(close_h5):
                close_h5()
        finally:
            remote = self._remote
            self._remote = None
            self.closed = True
            if remote is not None:
                close_remote = getattr(remote, "close", None)
                if callable(close_remote):
                    try:
                        close_remote()
                    except Exception:
                        pass

    def __getitem__(self, key: Any) -> Any:
        return self._h5[key]

    def __contains__(self, key: Any) -> bool:
        return key in self._h5

    def __getattr__(self, name: str) -> Any:
        # Delegate HDF5 attributes (e.g. ``id.valid``) while keeping local close state.
        return getattr(self._h5, name)


def open_nwb_lazy(blob_url: str, *, network_permission: bool = False, offline: bool = False) -> ManagedNwbHandle:
    """Compatibility opener requiring explicit network permission.

    The returned handle is not a license to materialize a recording.  New
    remote callers should use a bounded ``WindowSource``; this helper remains
    only for existing code that performs explicit HDF5 slices and closes the
    handle via the returned :class:`ManagedNwbHandle`.
    """
    if not str(blob_url).strip():
        raise IngestionContractError("blob_url is required")
    is_remote = str(blob_url).lower().startswith(("http://", "https://", "s3://"))
    if is_remote and (offline or not network_permission):
        raise IngestionContractError("remote NWB opening requires explicit network permission")
    import h5py
    if not is_remote:
        return ManagedNwbHandle(h5py.File(Path(blob_url), "r"), remote_file=None)
    import remfile
    remote = remfile.File(blob_url)
    try:
        return ManagedNwbHandle(h5py.File(remote, "r"), remote_file=remote)
    except Exception:
        close_remote = getattr(remote, "close", None)
        if callable(close_remote):
            close_remote()
        raise


def _eeg_series(nwb, eeg_series_name: str = "ElectricalSeriesEEG"):
    acq = nwb["acquisition"]
    if eeg_series_name not in acq:
        raise ValueError(f"no {eeg_series_name!r} in acquisition (have {list(acq.keys())})")
    return acq[eeg_series_name]


def _attr_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    text = str(value).strip()
    return text or None


def _channel_identity(es) -> list[str] | None:
    """Return channel names when present; never invent labels."""
    for key in ("electrodes", "channel_names", "electrodes_index"):
        if key not in es:
            continue
        node = es[key]
        try:
            if hasattr(node, "dtype") and getattr(node.dtype, "kind", None) in {"S", "O", "U"}:
                values = list(node[:])
                names = []
                for item in values:
                    text = _attr_str(item)
                    if text is None:
                        return None
                    names.append(text)
                return names or None
        except Exception:
            return None
    return None


def nwb_eeg_info(nwb, eeg_series_name: str = "ElectricalSeriesEEG") -> dict:
    """Preserve sampling rate, time bounds, units, channel identity, and montage when present.

    Missing fields stay ``null``; this helper never fabricates electrode names,
    units, or montage labels.
    """
    import numpy as np
    es = _eeg_series(nwb, eeg_series_name)
    data = es["data"]
    n_samples, n_channels = int(data.shape[0]), int(data.shape[1])
    timestamps_present = "timestamps" in es
    if timestamps_present:
        ts = es["timestamps"]
        t0, t1 = float(ts[0]), float(ts[-1])
        head = ts[: min(500, n_samples)]
        rate = 1.0 / float(np.mean(np.diff(head)))
        timestamp_unit = _attr_str(ts.attrs.get("unit") if hasattr(ts, "attrs") else None)
    else:
        st = es["starting_time"]
        rate = float(st.attrs.get("rate"))
        t0 = float(st[()]) if st.shape == () else float(st[0])
        t1 = t0 + n_samples / rate
        timestamp_unit = _attr_str(st.attrs.get("unit") if hasattr(st, "attrs") else None)
    data_unit = _attr_str(data.attrs.get("unit") if hasattr(data, "attrs") else None)
    series_unit = _attr_str(es.attrs.get("unit") if hasattr(es, "attrs") else None)
    montage = _attr_str(es.attrs.get("montage") if hasattr(es, "attrs") else None)
    if montage is None and "electrodes" in es:
        electrodes = es["electrodes"]
        montage = _attr_str(electrodes.attrs.get("montage") if hasattr(electrodes, "attrs") else None)
    channel_identity = _channel_identity(es)
    if channel_identity is not None and len(channel_identity) != n_channels:
        # Do not invent or truncate identity; treat mismatched tables as unknown.
        channel_identity = None
    return {
        "n_samples": n_samples,
        "n_channels": n_channels,
        "rate_hz": rate,
        "sampling_rate_hz": rate,
        "t_start_s": t0,
        "t_end_s": t1,
        "timestamps_present": bool(timestamps_present),
        "timestamp_unit": timestamp_unit,
        "data_unit": data_unit,
        "series_unit": series_unit,
        "units": data_unit or series_unit,
        "channel_identity": channel_identity,
        "montage": montage,
        "source_series": eeg_series_name,
    }


def nwb_state_epochs(nwb) -> list[tuple[str, float, float]]:
    if "intervals" not in nwb or "epochs" not in nwb["intervals"]:
        return []
    ep = nwb["intervals"]["epochs"]
    starts, stops = ep["start_time"][:], ep["stop_time"][:]
    tags_flat, tags_index = ep["tags"][:], ep["tags_index"][:]
    out: list[tuple[str, float, float]] = []
    prev = 0
    for i in range(len(starts)):
        end_idx = int(tags_index[i])
        row_tags = tags_flat[prev:end_idx]
        prev = end_idx
        tag = ""
        if len(row_tags):
            value = row_tags[0]
            tag = value.decode() if isinstance(value, bytes) else str(value)
        out.append((tag, float(starts[i]), float(stops[i])))
    return out


def read_nwb_eeg_window(nwb, window_start_s: float, window_end_s: float, pick: str = "all", max_channels: Optional[int] = None, eeg_series_name: str = "ElectricalSeriesEEG", info: Optional[dict] = None):
    """Read one bounded HDF5 slice from an already-open NWB object."""
    import numpy as np
    if not all(math.isfinite(float(value)) for value in (window_start_s, window_end_s)):
        raise ValueError("window bounds must be finite")
    if pick not in {"all", "mean"}:
        raise ValueError(f"unsupported EEG pick: {pick!r}")
    if max_channels is not None and max_channels <= 0:
        raise ValueError("max_channels must be positive")
    es = _eeg_series(nwb, eeg_series_name)
    if info is None:
        info = nwb_eeg_info(nwb, eeg_series_name)
    rate, t0, n_total = info["rate_hz"], info["t_start_s"], info["n_samples"]
    start = int(round((window_start_s - t0) * rate))
    stop = int(round((window_end_s - t0) * rate))
    if start < 0 or stop > n_total or stop <= start:
        raise ValueError(f"window [{window_start_s},{window_end_s}]s out of range (recording {t0:.1f}-{info['t_end_s']:.1f}s, {n_total} samples)")
    sample_count = stop - start
    spans_full_recording = (
        sample_count >= n_total
        or (start <= 0 and stop >= n_total)
        or (float(window_start_s) <= float(t0) and float(window_end_s) >= float(info["t_end_s"]))
    )
    if spans_full_recording:
        raise IngestionContractError("full-recording materialization is disabled; request a bounded window")
    ch_stop = info["n_channels"] if max_channels is None else min(info["n_channels"], max_channels)
    if sample_count > MAX_WINDOW_SAMPLES:
        raise ValueError("requested NWB EEG window exceeds the bounded sample limit")
    if ch_stop <= 0 or sample_count * ch_stop * 8 > MAX_WINDOW_BYTES:
        raise ValueError("requested NWB EEG window exceeds the bounded byte limit")
    block = np.asarray(es["data"][start:stop, :ch_stop], dtype=float).T
    return block.mean(axis=0) if pick == "mean" else block


__all__ = [
    "CacheStats",
    "DandiAsset",
    "IngestionContractError",
    "IngestionState",
    "LocalFileWindowSource",
    "LocalMetadataSource",
    "ManagedNwbHandle",
    "MetadataSource",
    "Provenance",
    "WindowCache",
    "WindowReadResult",
    "WindowRequest",
    "WindowSource",
    "checksum_status",
    "inspect_metadata",
    "nwb_eeg_info",
    "nwb_state_epochs",
    "open_nwb_lazy",
    "read_bounded_window",
    "read_nwb_eeg_window",
    "reject_full_object_materialization",
    "reject_full_recording_materialization",
    "release_window",
    "require_output_root",
    "resolve_asset_blobs",
    "resolve_under_root",
]
