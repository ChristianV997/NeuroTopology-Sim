"""Deterministic, fail-closed packing of selected public-source text files.

This module treats source trees and archives as untrusted bytes. It does not
import, build, install, or execute content from the harvested source.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import stat
import struct
import sys
import tarfile
import tempfile
import unicodedata
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable
from urllib.parse import urlsplit

from .license_scanner import ALLOWED as REUSE_ALLOWED_LICENSES

PACKER_VERSION = "1.0.0"
SOURCE_MANIFEST_SCHEMA = "PublicRepoSourceManifest.v1"
PACK_MANIFEST_PATH = "source-pack-manifest.json"
MAX_SOURCE_MANIFEST_BYTES = 256 * 1024
MAX_CLASSIC_ZIP_SIZE = (1 << 32) - 1
MAX_CLASSIC_ZIP_ENTRIES = (1 << 16) - 2

_LICENSE_STATUSES = {
    "compatible", "pattern_only", "incompatible", "unknown", "needs_manual_review"
}
_COMPATIBILITY_STATUSES = {
    "safe_to_adapt", "pattern_only_reimplementation_required", "blocked_license",
    "blocked_dependency_surface", "blocked_security_risk", "manual_review_required"
}
_REVIEW_STATUSES = {
    "unreviewed", "human_reviewed_compatible", "human_reviewed_incompatible"
}
_LICENSE_RECORD_FIELDS = {
    "repo", "detected_license", "detected_licenses", "license_name", "license_spdx",
    "license_status", "compatibility_status", "can_copy_code", "can_copy_docs",
    "manual_review_required", "review_status", "conflicting", "conflicting_licenses",
    "license_hint", "likely_license", "decision_rationale", "attribution_required",
    "notice_required", "can_adapt_patterns",
}
_LICENSE_ALIASES = {
    "mit license": "MIT",
    "apache license 2.0": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "bsd 2-clause license": "BSD-2-Clause",
    "bsd 3-clause license": "BSD-3-Clause",
    "isc license": "ISC",
}

_EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".tox", ".nox", ".venv", "venv", "env", "node_modules",
    "vendor", "build", "dist", "target", "coverage", "cache", "caches", ".cache",
    ".terraform",
}
_CREDENTIAL_DIRS = {".aws", ".ssh", ".gnupg", ".kube", ".azure"}
_CREDENTIAL_NAMES = {
    ".env", ".netrc", ".npmrc", ".pypirc", ".dockerconfigjson", "credentials",
    "credentials.json", "secrets.json", "secrets.yaml", "secrets.yml", "id_rsa",
    "id_dsa", "id_ecdsa", "id_ed25519", "known_hosts", "service-account.json",
}
_BINARY_SUFFIXES = {
    ".7z", ".a", ".bin", ".bmp", ".class", ".crt", ".cer", ".db", ".dylib",
    ".dll", ".doc", ".docx", ".exe", ".gif", ".gz", ".h5", ".hdf5", ".ico",
    ".jar", ".jpeg", ".jpg", ".keystore", ".key", ".kdbx", ".lib", ".mat",
    ".mdb", ".mp3", ".mp4", ".npy", ".npz", ".o", ".pdf", ".p12", ".pfx",
    ".pickle", ".pkl", ".png", ".pt", ".pth", ".pyc", ".rar", ".so", ".sqlite",
    ".sqlite3", ".tar", ".tgz", ".wasm", ".webp", ".whl", ".woff", ".woff2",
    ".xls", ".xlsx", ".xz", ".zip",
}
_SECRET_FILE_PATTERN = re.compile(
    r"(?:^|[._-])(?:secret|secrets|credential|credentials|passwords?|tokens?|api[-_]?keys?|"
    r"private[-_]?keys?|access[-_]?keys?|service[-_]?account|auth[-_]?tokens?)(?:[._-]|$)",
    re.IGNORECASE,
)
_SECRET_CONTENT_PATTERNS = (
    re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"\bsk_(?:live|test|proj)_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\b(?:xox[baprs]-[A-Za-z0-9-]{16,}|AIza[0-9A-Za-z_-]{30,})\b"),
    re.compile(r"(?im)\baws_(?:access_key_id|secret_access_key)\b\s*=\s*[A-Z0-9/+=]{16,}"),
    re.compile(r"https?://[^\s/:@]+:[^\s/@]{8,}@"),
    re.compile(
        r"(?im)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|secret[_-]?key|password|passwd)"
        r"\b\s*[:=]\s*['\"](?!(?:YOUR_|CHANGEME|REDACTED|EXAMPLE|PLACEHOLDER))[^'\"\r\n]{8,}['\"]"
    ),
)


class SourcePackError(ValueError):
    """Raised when source-pack input violates a safety or provenance contract."""


@dataclass(frozen=True)
class SourcePackLimits:
    """Explicit resource bounds for one deterministic source pack."""

    max_files: int = 256
    max_file_bytes: int = 1_048_576
    max_total_bytes: int = 16_777_216
    max_depth: int = 12
    max_output_bytes: int = 20_000_000
    max_archive_bytes: int = 32_000_000
    max_archive_entries: int = 1024
    max_compression_ratio: int = 100

    def __post_init__(self) -> None:
        integer_fields = (
            "max_files", "max_file_bytes", "max_total_bytes", "max_depth",
            "max_output_bytes", "max_archive_bytes", "max_archive_entries",
            "max_compression_ratio",
        )
        for name in integer_fields:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise SourcePackError(f"{name} must be a positive integer")
        if self.max_files > MAX_CLASSIC_ZIP_ENTRIES or self.max_archive_entries > MAX_CLASSIC_ZIP_ENTRIES:
            raise SourcePackError("file and archive-entry limits must fit a non-ZIP64 archive")
        for name in ("max_file_bytes", "max_total_bytes", "max_output_bytes", "max_archive_bytes"):
            if getattr(self, name) > MAX_CLASSIC_ZIP_SIZE:
                raise SourcePackError(f"{name} exceeds the supported non-ZIP64 bound")


def _reject_json_constant(token: str) -> None:
    raise SourcePackError(f"non-finite JSON constant is forbidden: {token}")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SourcePackError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def load_source_manifest(path: str | Path) -> dict[str, Any]:
    """Read a small, strict UTF-8 source manifest without accepting symlinks."""
    manifest_path = Path(path)
    try:
        if manifest_path.is_symlink() or getattr(manifest_path, "is_junction", lambda: False)():
            raise SourcePackError("source manifest may not be a symlink or junction")
        info = manifest_path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_SOURCE_MANIFEST_BYTES:
            raise SourcePackError("source manifest must be a small regular file")
        raw = _bounded_file_read(
            manifest_path,
            info.st_size,
            MAX_SOURCE_MANIFEST_BYTES,
            expected_info=info,
        )
        if len(raw) > MAX_SOURCE_MANIFEST_BYTES:
            raise SourcePackError("source manifest exceeds the size limit")
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except SourcePackError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SourcePackError("source manifest is malformed or unreadable") from exc
    if not isinstance(value, dict):
        raise SourcePackError("source manifest root must be an object")
    return value


def _canonical_source_url(value: object) -> str:
    if not isinstance(value, str) or len(value) > 512:
        raise SourcePackError("source_url must be a canonical GitHub repository URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise SourcePackError("source_url is malformed") from exc
    if (
        parsed.scheme.lower() != "https"
        or (parsed.hostname or "").lower() != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
    ):
        raise SourcePackError("source_url must use plain HTTPS github.com without credentials or query data")
    raw_path = parsed.path.strip("/")
    if "%" in raw_path or "\\" in raw_path:
        raise SourcePackError("source_url path may not use encoded or ambiguous separators")
    if raw_path.endswith(".git"):
        raw_path = raw_path[:-4]
    parts = raw_path.split("/")
    if len(parts) != 2 or any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", part) for part in parts):
        raise SourcePackError("source_url must identify exactly one owner and repository")
    if any(part in {".", ".."} for part in parts):
        raise SourcePackError("source_url contains an unsafe path component")
    return f"https://github.com/{parts[0].lower()}/{parts[1].lower()}"


def _safe_relative_path(value: object, *, directory: bool = False, max_depth: int | None = None) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise SourcePackError("selected paths must be non-empty strings under 4096 characters")
    if "\x00" in value or "\\" in value or unicodedata.normalize("NFC", value) != value:
        raise SourcePackError(f"path is non-canonical or contains an unsafe character: {value!r}")
    if value.startswith("/") or PureWindowsPath(value).drive or PureWindowsPath(value).is_absolute():
        raise SourcePackError(f"absolute or drive-qualified path is forbidden: {value!r}")
    if any(ch in value for ch in '<>:"|?*') or any(ord(ch) < 32 for ch in value):
        raise SourcePackError(f"path contains a non-portable character: {value!r}")
    raw = value[:-1] if directory and value.endswith("/") else value
    parts = raw.split("/")
    if not raw or any(part in {"", ".", ".."} for part in parts):
        raise SourcePackError(f"path contains an empty or traversal component: {value!r}")
    for part in parts:
        if part.endswith((".", " ")):
            raise SourcePackError(f"path component aliases on Windows: {value!r}")
        stem = part.split(".", 1)[0].upper()
        if stem in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(?:COM|LPT)[1-9]", stem):
            raise SourcePackError(f"reserved Windows path component: {value!r}")
    if max_depth is not None and len(parts) > max_depth:
        raise SourcePackError(f"path exceeds the configured directory depth: {value!r}")
    return "/".join(parts)


def _track_casefold_spelling(path: str, spellings: dict[str, str]) -> None:
    parts = path.split("/")
    for depth in range(1, len(parts) + 1):
        prefix = "/".join(parts[:depth])
        key = prefix.casefold()
        previous = spellings.get(key)
        if previous is not None and previous != prefix:
            raise SourcePackError(f"duplicate or case-ambiguous path component: {prefix}")
        spellings[key] = prefix


def _license_alias(value: str) -> str:
    cleaned = " ".join(value.strip().split())
    return _LICENSE_ALIASES.get(cleaned.casefold(), cleaned)


def _normalize_license_record(value: object) -> dict[str, Any]:
    if value is None:
        record: dict[str, Any] = {}
    elif isinstance(value, dict):
        unknown = set(value) - _LICENSE_RECORD_FIELDS
        if unknown:
            raise SourcePackError(f"license_record has unsupported fields: {', '.join(sorted(unknown))}")
        record = value
    else:
        raise SourcePackError("license_record must be an object when provided")

    candidates: list[str] = []
    listed = record.get("detected_licenses", [])
    if not isinstance(listed, list) or any(not isinstance(item, str) for item in listed):
        raise SourcePackError("license_record.detected_licenses must be a string array")
    candidates.extend(listed)
    for key in ("detected_license", "license_spdx", "license_name"):
        item = record.get(key)
        if item is not None:
            if not isinstance(item, str):
                raise SourcePackError(f"license_record.{key} must be a string")
            candidates.append(item)
    detected_values: list[str] = []
    for item in candidates:
        cleaned = _license_alias(item)
        if not re.fullmatch(r"[A-Za-z0-9.+ -]{1,128}", cleaned):
            raise SourcePackError("license identifiers must be short, non-empty, printable strings")
        if cleaned.upper() not in {"UNKNOWN", "UNLICENSED", "NOASSERTION"}:
            detected_values.append(cleaned)
    canonical_detected = sorted(set(detected_values), key=lambda item: (item.casefold(), item))

    license_status = record.get("license_status", "unknown")
    compatibility_status = record.get("compatibility_status", "manual_review_required")
    review_status = record.get("review_status", "unreviewed")
    if not isinstance(license_status, str) or license_status not in _LICENSE_STATUSES:
        raise SourcePackError("license_record.license_status is not recognized")
    if not isinstance(compatibility_status, str) or compatibility_status not in _COMPATIBILITY_STATUSES:
        raise SourcePackError("license_record.compatibility_status is not recognized")
    if not isinstance(review_status, str) or review_status not in _REVIEW_STATUSES:
        raise SourcePackError("license_record.review_status is not recognized")
    for key in ("can_copy_code", "manual_review_required", "conflicting"):
        if key in record and not isinstance(record[key], bool):
            raise SourcePackError(f"license_record.{key} must be boolean")
    conflict_list = record.get("conflicting_licenses", [])
    if not isinstance(conflict_list, list) or any(not isinstance(item, str) for item in conflict_list):
        raise SourcePackError("license_record.conflicting_licenses must be a string array")
    if any(len(item) > 128 for item in conflict_list):
        raise SourcePackError("conflicting license identifiers must be short")
    is_conflicting = bool(record.get("conflicting", False)) or bool(conflict_list) or len(canonical_detected) > 1

    hint = record.get("license_hint", record.get("likely_license", "unknown"))
    if not isinstance(hint, str) or len(hint) > 64 or not re.fullmatch(r"[A-Za-z0-9.+ -]+", hint or ""):
        raise SourcePackError("license hint must be a short license-like identifier")

    explicit_copy_gate = (
        len(canonical_detected) == 1
        and canonical_detected[0] in REUSE_ALLOWED_LICENSES
        and license_status == "compatible"
        and compatibility_status == "safe_to_adapt"
        and review_status == "human_reviewed_compatible"
        and record.get("can_copy_code") is True
        and record.get("manual_review_required") is False
        and not is_conflicting
    )
    reasons: list[str] = []
    if is_conflicting:
        reasons.append("conflicting_license_information")
    if not canonical_detected:
        reasons.append("license_unknown_or_not_detected")
    if not explicit_copy_gate and not is_conflicting and canonical_detected:
        reasons.append("explicit_human_compatibility_review_missing")
    return {
        "detected_licenses": canonical_detected,
        "license_hint": hint,
        "license_status": license_status,
        "compatibility_status": compatibility_status,
        "review_status": review_status,
        "can_copy_code": bool(record.get("can_copy_code", False)),
        "conflicting": is_conflicting,
        "reuse_status": "human_reviewed_compatible" if explicit_copy_gate else "blocked",
        "reuse_block_reasons": reasons,
    }


def validate_source_manifest(raw: object, *, max_files: int = 256, max_depth: int = 12) -> dict[str, Any]:
    """Validate caller-supplied provenance and selection; never infer it."""
    if isinstance(max_files, bool) or not isinstance(max_files, int) or max_files <= 0:
        raise SourcePackError("max_files must be a positive integer")
    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth <= 0:
        raise SourcePackError("max_depth must be a positive integer")
    if not isinstance(raw, dict):
        raise SourcePackError("source manifest root must be an object")
    allowed = {
        "schema_version", "source_url", "source_commit", "access_date", "selected_paths", "license_record"
    }
    unknown = set(raw) - allowed
    if unknown:
        raise SourcePackError(f"source manifest has unsupported fields: {', '.join(sorted(unknown))}")
    if raw.get("schema_version") != SOURCE_MANIFEST_SCHEMA:
        raise SourcePackError(f"schema_version must be {SOURCE_MANIFEST_SCHEMA}")
    source_url = _canonical_source_url(raw.get("source_url"))
    commit = raw.get("source_commit")
    if commit is not None:
        if not isinstance(commit, str) or not re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", commit):
            raise SourcePackError("source_commit must be a full 40- or 64-character hexadecimal object ID")
        commit = commit.lower()
    access_date = raw.get("access_date")
    if access_date is not None:
        if not isinstance(access_date, str):
            raise SourcePackError("access_date must be an explicit YYYY-MM-DD string")
        try:
            parsed_date = dt.date.fromisoformat(access_date)
        except ValueError as exc:
            raise SourcePackError("access_date must be a valid YYYY-MM-DD date") from exc
        if parsed_date.isoformat() != access_date:
            raise SourcePackError("access_date must use canonical YYYY-MM-DD format")
    if commit is None and access_date is None:
        raise SourcePackError("an immutable source_commit or explicit access_date is required")
    paths = raw.get("selected_paths")
    if not isinstance(paths, list) or not paths:
        raise SourcePackError("selected_paths must be a non-empty list")
    if len(paths) > max_files:
        raise SourcePackError("selected_paths exceeds the configured maximum file count")
    selected: list[str] = []
    seen: set[str] = set()
    component_spellings: dict[str, str] = {}
    for value in paths:
        path = _safe_relative_path(value, max_depth=max_depth)
        _track_casefold_spelling(path, component_spellings)
        key = path.casefold()
        if key in seen:
            raise SourcePackError(f"duplicate or case-ambiguous selected path: {path}")
        if path == PACK_MANIFEST_PATH:
            raise SourcePackError(f"selected path collides with generated manifest: {path}")
        seen.add(key)
        selected.append(path)
    return {
        "schema_version": SOURCE_MANIFEST_SCHEMA,
        "source_url": source_url,
        "source_commit": commit,
        "access_date": access_date,
        "selected_paths": sorted(selected, key=lambda item: (item.casefold(), item)),
        "license_record": _normalize_license_record(raw.get("license_record")),
    }


def _path_exclusion(path: str) -> str | None:
    parts = path.split("/")
    folded = [part.casefold() for part in parts]
    if any(part in _CREDENTIAL_DIRS for part in folded[:-1]):
        return "credential_directory"
    if any(part in _EXCLUDED_DIRS for part in folded[:-1]):
        return "cache_or_repository_metadata"
    name = folded[-1]
    if name.startswith(".env") or name in _CREDENTIAL_NAMES:
        return "credential_filename"
    if _SECRET_FILE_PATTERN.search(name):
        return "likely_secret_filename"
    if Path(name).suffix.casefold() in _BINARY_SUFFIXES:
        return "binary_file_type"
    if path == PACK_MANIFEST_PATH:
        return "reserved_manifest_path"
    return None


def _binary_or_secret_reason(path: str, data: bytes) -> str | None:
    if Path(path).suffix.casefold() in _BINARY_SUFFIXES:
        return "binary_file_type"
    if b"\x00" in data:
        return "binary_content"
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return "non_utf8_binary_content"
    if any((ord(ch) < 32 and ch not in "\t\n\r\f") for ch in text):
        return "binary_control_bytes"
    if text.startswith(("MZ", "\x7fELF", "%PDF-", "SQLite format 3\x00")):
        return "binary_signature"
    if any(pattern.search(text) for pattern in _SECRET_CONTENT_PATTERNS):
        return "likely_secret_content"
    return None


def _check_regular_file(path: Path) -> os.stat_result:
    try:
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            raise SourcePackError(f"symlink or junction is not packable: {path.name}")
        info = path.lstat()
    except OSError as exc:
        raise SourcePackError("selected source path is unreadable") from exc
    if not stat.S_ISREG(info.st_mode):
        raise SourcePackError(f"selected source path is not a regular file: {path.name}")
    return info


def _bounded_file_read(
    path: Path,
    expected_size: int,
    max_file_bytes: int,
    *,
    expected_info: os.stat_result | None = None,
) -> bytes:
    if expected_size > max_file_bytes:
        raise SourcePackError(f"selected file exceeds max_file_bytes: {path.name}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        before = _check_regular_file(path)
        if expected_info is not None and (
            (before.st_dev, before.st_ino, before.st_size)
            != (expected_info.st_dev, expected_info.st_ino, expected_info.st_size)
        ):
            raise SourcePackError(f"selected file changed during pack: {path.name}")
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_size != expected_size
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            ):
                raise SourcePackError(f"selected file changed during pack: {path.name}")
            chunks: list[bytes] = []
            remaining = max_file_bytes + 1
            while remaining:
                chunk = handle.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
            after = os.fstat(handle.fileno())
        if (
            len(data) != expected_size
            or len(data) > max_file_bytes
            or after.st_size != before.st_size
            or after.st_mtime_ns != before.st_mtime_ns
        ):
            raise SourcePackError(f"selected file size changed or exceeded bounds: {path.name}")
        return data
    except SourcePackError:
        raise
    except OSError as exc:
        raise SourcePackError("selected source file could not be read safely") from exc


def _check_inventory_path(path: str, *, directory: bool, limits: SourcePackLimits) -> str:
    return _safe_relative_path(path, directory=directory, max_depth=limits.max_depth)


def _check_archive_inventory(
    entries: list[tuple[str, bool, int]], limits: SourcePackLimits
) -> dict[str, tuple[bool, int]]:
    if len(entries) > limits.max_archive_entries:
        raise SourcePackError("archive exceeds max_archive_entries")
    inventory: dict[str, tuple[bool, int]] = {}
    folded: dict[str, str] = {}
    component_spellings: dict[str, str] = {}
    total_bytes = 0
    file_count = 0
    for raw_path, is_dir, size in entries:
        path = _check_inventory_path(raw_path, directory=is_dir, limits=limits)
        _track_casefold_spelling(path, component_spellings)
        key = path.casefold()
        if key in folded:
            raise SourcePackError(f"duplicate or case-ambiguous archive path: {path}")
        folded[key] = path
        if is_dir:
            if size != 0:
                raise SourcePackError("archive directory entry unexpectedly contains data")
        else:
            file_count += 1
            if file_count > limits.max_files:
                raise SourcePackError("archive exceeds max_files")
            if size < 0 or size > limits.max_file_bytes:
                raise SourcePackError(f"archive entry exceeds max_file_bytes: {path}")
            total_bytes += size
            if total_bytes > limits.max_total_bytes:
                raise SourcePackError("archive exceeds max_total_bytes")
        for parent in PurePosixPath(path).parents:
            if str(parent) == ".":
                continue
            parent_entry = inventory.get(str(parent).casefold())
            if parent_entry is not None and not parent_entry[0]:
                raise SourcePackError(f"archive file/directory path collision: {path}")
        if not is_dir and any(existing.startswith(key + "/") for existing in folded):
            raise SourcePackError(f"archive file/directory path collision: {path}")
        inventory[key] = (is_dir, size)
    return inventory


def _preflight_zip_central_directory(archive_file: Any, archive_size: int, max_entries: int) -> None:
    """Bound the central-directory count before zipfile allocates ZipInfo objects."""
    tail_size = min(archive_size, 22 + 65_535)
    archive_file.seek(archive_size - tail_size)
    tail = archive_file.read(tail_size)
    signature = b"PK\x05\x06"
    search_before = len(tail)
    record = None
    while True:
        offset = tail.rfind(signature, 0, search_before)
        if offset < 0:
            break
        if offset + 22 <= len(tail):
            fields = struct.unpack_from("<4s4H2LH", tail, offset)
            comment_length = fields[7]
            if offset + 22 + comment_length == len(tail):
                record = (offset, fields)
                break
        search_before = offset
    if record is None:
        raise SourcePackError("malformed ZIP end-of-central-directory record")
    offset, fields = record
    _, disk_number, directory_disk, disk_entries, total_entries, directory_size, directory_offset, _ = fields
    if disk_number != 0 or directory_disk != 0 or disk_entries != total_entries:
        raise SourcePackError("multi-disk ZIP archives are not supported")
    if (
        disk_entries == 0xFFFF
        or total_entries == 0xFFFF
        or directory_size == 0xFFFFFFFF
        or directory_offset == 0xFFFFFFFF
    ):
        raise SourcePackError("ZIP64 archives are not supported")
    if total_entries > max_entries:
        raise SourcePackError("archive exceeds max_archive_entries")
    eocd_absolute_offset = archive_size - tail_size + offset
    if directory_offset + directory_size != eocd_absolute_offset:
        raise SourcePackError("ZIP central directory extent is ambiguous or malformed")


def _selected_archive_payloads(
    selected_paths: list[str],
    archive_names: dict[str, str],
    read_member: Callable[[str], bytes],
    limits: SourcePackLimits,
) -> tuple[dict[str, bytes], list[dict[str, str]], int]:
    selected: dict[str, bytes] = {}
    excluded: list[dict[str, str]] = []
    requested_keys = {path.casefold() for path in selected_paths}
    unselected_count = len(set(archive_names) - requested_keys)
    for path in selected_paths:
        key = path.casefold()
        archive_path = archive_names.get(key)
        if archive_path is None:
            raise SourcePackError(f"selected path is absent from archive: {path}")
        if archive_path != path:
            raise SourcePackError(f"selected path spelling does not match archive entry: {path}")
        reason = _path_exclusion(path)
        if reason:
            excluded.append({"path": path, "reason": reason})
            continue
        data = read_member(archive_path)
        if len(data) > limits.max_file_bytes:
            raise SourcePackError(f"selected archive member exceeds max_file_bytes: {path}")
        reason = _binary_or_secret_reason(path, data)
        if reason:
            excluded.append({"path": path, "reason": reason})
            continue
        selected[path] = data
    return selected, sorted(excluded, key=lambda item: (item["path"].casefold(), item["reason"])), unselected_count


def _pack_zip(
    archive_file: Any, archive_size: int, selected_paths: list[str], limits: SourcePackLimits
) -> tuple[str, dict[str, bytes], list[dict[str, str]], int]:
    if archive_size > limits.max_archive_bytes:
        raise SourcePackError("archive exceeds max_archive_bytes")
    try:
        _preflight_zip_central_directory(archive_file, archive_size, limits.max_archive_entries)
        archive_file.seek(0)
        with zipfile.ZipFile(archive_file, "r") as archive:
            infos = archive.infolist()
            raw_entries: list[tuple[str, bool, int]] = []
            name_by_key: dict[str, str] = {}
            regular_names: dict[str, str] = {}
            for info in infos:
                is_dir = info.is_dir()
                raw_name = getattr(info, "orig_filename", info.filename)
                if raw_name != info.filename:
                    raise SourcePackError("ZIP entry name was truncated or contains an ambiguous NUL")
                mode = (info.external_attr >> 16) & 0xFFFF
                file_type = stat.S_IFMT(mode)
                if file_type == stat.S_IFLNK:
                    raise SourcePackError(f"archive symlink rejected: {info.filename}")
                if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise SourcePackError(f"archive special file rejected: {info.filename}")
                if info.flag_bits & 0x1:
                    raise SourcePackError("encrypted ZIP entries are not supported")
                if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                    raise SourcePackError("ZIP compression method is not allowed")
                path = _check_inventory_path(raw_name, directory=is_dir, limits=limits)
                key = path.casefold()
                if key in name_by_key:
                    raise SourcePackError(f"duplicate or case-ambiguous archive path: {path}")
                name_by_key[key] = path
                if not is_dir:
                    regular_names[key] = path
                raw_entries.append((path, is_dir, info.file_size))
                if not is_dir:
                    if info.file_size and info.compress_size == 0:
                        raise SourcePackError("archive entry has an impossible compressed size")
                    ratio = info.file_size / max(info.compress_size, 1)
                    if ratio > limits.max_compression_ratio:
                        raise SourcePackError(f"archive compression ratio exceeds limit: {path}")
            inventory = _check_archive_inventory(raw_entries, limits)
            for info in infos:
                try:
                    handle = archive.open(info, "r")
                    handle.close()
                except (OSError, RuntimeError, zipfile.BadZipFile, NotImplementedError) as exc:
                    raise SourcePackError("ZIP local header is malformed or inconsistent") from exc
            for path in selected_paths:
                if path.casefold() in inventory and inventory[path.casefold()][0]:
                    raise SourcePackError(f"selected path is a directory, not a file: {path}")

            by_name = {info.filename.rstrip("/").casefold(): info for info in infos if not info.is_dir()}

            def read_member(name: str) -> bytes:
                info = by_name.get(name.rstrip("/").casefold())
                if info is None:
                    raise SourcePackError(f"selected archive member not found: {name}")
                try:
                    with archive.open(info, "r") as handle:
                        data = handle.read(limits.max_file_bytes + 1)
                except (OSError, RuntimeError, zipfile.BadZipFile, NotImplementedError) as exc:
                    raise SourcePackError(f"archive member could not be read safely: {name}") from exc
                if len(data) != info.file_size:
                    raise SourcePackError(f"archive member size does not match its header: {name}")
                return data

            selected, excluded, unselected = _selected_archive_payloads(
                selected_paths, regular_names, read_member, limits
            )
            return "zip", selected, excluded, unselected
    except SourcePackError:
        raise
    except (OSError, RuntimeError, NotImplementedError, zipfile.BadZipFile, zipfile.LargeZipFile, EOFError) as exc:
        raise SourcePackError("malformed or unreadable ZIP archive") from exc


def _pack_tar(
    archive_file: Any, archive_size: int, selected_paths: list[str], limits: SourcePackLimits
) -> tuple[str, dict[str, bytes], list[dict[str, str]], int]:
    if archive_size > limits.max_archive_bytes:
        raise SourcePackError("archive exceeds max_archive_bytes")
    try:
        with tarfile.open(fileobj=archive_file, mode="r:") as archive:
            members = []
            declared_total = 0
            while True:
                member = archive.next()
                if member is None:
                    break
                members.append(member)
                if len(members) > limits.max_archive_entries:
                    raise SourcePackError("archive exceeds max_archive_entries")
                if member.isfile():
                    if member.size < 0 or member.size > limits.max_file_bytes:
                        raise SourcePackError(f"archive entry exceeds max_file_bytes: {member.name}")
                    declared_total += member.size
                    if declared_total > limits.max_total_bytes:
                        raise SourcePackError("archive exceeds max_total_bytes")
            raw_entries: list[tuple[str, bool, int]] = []
            member_by_key: dict[str, tarfile.TarInfo] = {}
            regular_names: dict[str, str] = {}
            for member in members:
                if member.issym() or member.islnk():
                    raise SourcePackError(f"archive symlink or hardlink rejected: {member.name}")
                if not (member.isfile() or member.isdir()):
                    raise SourcePackError(f"archive special file rejected: {member.name}")
                if getattr(member, "issparse", lambda: False)():
                    raise SourcePackError(f"sparse archive member rejected: {member.name}")
                if any(key in member.pax_headers for key in ("path", "linkpath", "size", "GNU.sparse.map")):
                    raise SourcePackError("ambiguous PAX path/size metadata is not allowed")
                path = _check_inventory_path(member.name, directory=member.isdir(), limits=limits)
                key = path.casefold()
                if key in member_by_key:
                    raise SourcePackError(f"duplicate or case-ambiguous archive path: {path}")
                member_by_key[key] = member
                if member.isfile():
                    regular_names[key] = path
                raw_entries.append((path, member.isdir(), member.size))
                if member.offset_data < 0 or member.offset_data + member.size > archive_size:
                    raise SourcePackError(f"archive member extent is invalid: {path}")
            inventory = _check_archive_inventory(raw_entries, limits)
            for path in selected_paths:
                if path.casefold() in inventory and inventory[path.casefold()][0]:
                    raise SourcePackError(f"selected path is a directory, not a file: {path}")

            def read_member(name: str) -> bytes:
                member = member_by_key.get(name.casefold())
                if member is None:
                    raise SourcePackError(f"selected archive member not found: {name}")
                try:
                    handle = archive.extractfile(member)
                    if handle is None:
                        raise SourcePackError(f"archive member has no file body: {name}")
                    with handle:
                        data = handle.read(limits.max_file_bytes + 1)
                except (OSError, tarfile.TarError) as exc:
                    raise SourcePackError(f"archive member could not be read safely: {name}") from exc
                if len(data) != member.size:
                    raise SourcePackError(f"archive member size does not match its header: {name}")
                return data

            selected, excluded, unselected = _selected_archive_payloads(
                selected_paths, regular_names, read_member, limits
            )
            return "tar", selected, excluded, unselected
    except SourcePackError:
        raise
    except (OSError, tarfile.TarError, EOFError) as exc:
        raise SourcePackError("malformed or unsupported uncompressed TAR archive") from exc


def _reject_link_components(path: Path) -> None:
    for candidate in (path, *path.parents):
        if candidate.is_symlink() or getattr(candidate, "is_junction", lambda: False)():
            raise SourcePackError(f"symlink or junction path rejected: {candidate.name}")


def _pack_directory(
    source: Path, selected_paths: list[str], limits: SourcePackLimits
) -> tuple[str, dict[str, bytes], list[dict[str, str]], int]:
    if not source.is_dir() or source.is_symlink() or getattr(source, "is_junction", lambda: False)():
        raise SourcePackError("directory source must be a non-symlink directory")
    root = source.resolve(strict=True)
    total_bytes = 0
    selected: dict[str, bytes] = {}
    excluded: list[dict[str, str]] = []
    for relative in selected_paths:
        candidate = root
        for component in relative.split("/"):
            candidate = candidate / component
            if candidate.is_symlink() or getattr(candidate, "is_junction", lambda: False)():
                raise SourcePackError(f"selected source path crosses a symlink or junction: {relative}")
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise SourcePackError(f"selected source path escapes source root: {relative}") from exc
        info = _check_regular_file(candidate)
        if info.st_size > limits.max_file_bytes:
            raise SourcePackError(f"selected file exceeds max_file_bytes: {relative}")
        total_bytes += info.st_size
        if total_bytes > limits.max_total_bytes:
            raise SourcePackError("selected files exceed max_total_bytes")
        reason = _path_exclusion(relative)
        if reason:
            excluded.append({"path": relative, "reason": reason})
            continue
        data = _bounded_file_read(
            candidate,
            info.st_size,
            limits.max_file_bytes,
            expected_info=info,
        )
        reason = _binary_or_secret_reason(relative, data)
        if reason:
            excluded.append({"path": relative, "reason": reason})
            continue
        selected[relative] = data
    return "directory", selected, sorted(excluded, key=lambda item: (item["path"].casefold(), item["reason"])), 0


def _canonical_json(value: Any) -> bytes:
    try:
        return (
            json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SourcePackError("source-pack manifest is not finite JSON") from exc


def _open_regular_archive(path: Path, max_archive_bytes: int):
    before = _check_regular_file(path)
    if before.st_size > max_archive_bytes:
        raise SourcePackError("archive exceeds max_archive_bytes")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        handle = os.fdopen(fd, "rb")
        opened = os.fstat(handle.fileno())
        if (
            not stat.S_ISREG(opened.st_mode)
            or (opened.st_dev, opened.st_ino, opened.st_size)
            != (before.st_dev, before.st_ino, before.st_size)
        ):
            handle.close()
            raise SourcePackError("archive changed or became unsafe while opening")
        return handle, opened.st_size
    except SourcePackError:
        raise
    except OSError as exc:
        raise SourcePackError("source archive could not be opened safely") from exc


def _zip_output_size(files: dict[str, bytes], manifest_bytes: bytes) -> int:
    entries = [(PACK_MANIFEST_PATH, manifest_bytes), *sorted(files.items(), key=lambda item: (item[0].casefold(), item[0]))]
    total = 22  # EOCD; classic ZIP limits are enforced by SourcePackLimits.
    for name, data in entries:
        name_size = len(name.encode("utf-8"))
        total += 30 + name_size + len(data)  # local header + stored data
        total += 46 + name_size  # central-directory entry
    return total


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.extra = b""
    info.comment = b""
    return info


def _assert_output_location(source: Path, output: Path, is_directory: bool) -> Path:
    if output.name in {"", ".", ".."}:
        raise SourcePackError("output must name a new pack file")
    if output.exists() or output.is_symlink() or getattr(output, "is_junction", lambda: False)():
        raise SourcePackError("output path already exists or is a link")
    parent = output.parent
    _reject_link_components(parent)
    resolved_source = source.resolve(strict=True)
    resolved_parent = parent.resolve(strict=False)
    resolved_output = resolved_parent / output.name
    if is_directory:
        try:
            resolved_output.relative_to(resolved_source)
        except ValueError:
            pass
        else:
            raise SourcePackError("output pack may not be placed inside its source tree")
    elif resolved_output == resolved_source:
        raise SourcePackError("output pack may not overwrite its source archive")
    parent.mkdir(parents=True, exist_ok=True)
    _reject_link_components(parent)
    if parent.resolve(strict=True) != resolved_parent:
        raise SourcePackError("output parent changed during source-pack setup")
    return resolved_output


def pack_static_source(
    source: str | Path,
    manifest: str | Path | dict[str, Any],
    output: str | Path,
    *,
    limits: SourcePackLimits | None = None,
) -> dict[str, Any]:
    """Build an atomic, deterministic ZIP containing only selected safe text files.

    `manifest` is either a small JSON path or an already-loaded mapping. Its
    provenance fields are caller assertions and are not verified against GitHub.
    """
    if limits is None:
        limits = SourcePackLimits()
    elif not isinstance(limits, SourcePackLimits):
        raise SourcePackError("limits must be a SourcePackLimits value")
    raw_manifest = load_source_manifest(manifest) if isinstance(manifest, (str, Path)) else manifest
    metadata = validate_source_manifest(raw_manifest, max_files=limits.max_files, max_depth=limits.max_depth)
    source_path = Path(source).expanduser()
    if source_path.is_symlink() or getattr(source_path, "is_junction", lambda: False)():
        raise SourcePackError("source path may not be a symlink or junction")
    if not source_path.exists():
        raise SourcePackError("source path does not exist")
    output_path = Path(output).expanduser()
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    resolved_output = _assert_output_location(source_path, output_path, source_path.is_dir())

    if source_path.is_dir():
        source_kind, files, exclusions, unselected_count = _pack_directory(
            source_path, metadata["selected_paths"], limits
        )
        unselected_scope_not_enumerated = True
    else:
        try:
            _reject_link_components(source_path)
        except SourcePackError:
            raise
        archive_file, archive_size = _open_regular_archive(source_path, limits.max_archive_bytes)
        try:
            is_zip = zipfile.is_zipfile(archive_file)
            archive_file.seek(0)
            if is_zip:
                source_kind, files, exclusions, unselected_count = _pack_zip(
                    archive_file, archive_size, metadata["selected_paths"], limits
                )
            else:
                source_kind, files, exclusions, unselected_count = _pack_tar(
                    archive_file, archive_size, metadata["selected_paths"], limits
                )
        except OSError as exc:
            raise SourcePackError("source archive could not be inspected safely") from exc
        finally:
            archive_file.close()
        unselected_scope_not_enumerated = False

    file_records = [
        {"path": path, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for path, data in sorted(files.items(), key=lambda item: (item[0].casefold(), item[0]))
    ]
    license_record = metadata["license_record"]
    content_excluded = bool(exclusions) or bool(unselected_count) or unselected_scope_not_enumerated
    pack_manifest = {
        "schema_version": "PublicRepoSourcePack.v1",
        "packer_version": PACKER_VERSION,
        "provenance": {
            "canonical_source_url": metadata["source_url"],
            "source_commit": metadata["source_commit"],
            "access_date": metadata["access_date"],
            "assertion_status": "caller_supplied_not_verified_offline",
        },
        "source_kind": source_kind,
        "selected_paths": [record["path"] for record in file_records],
        "files": file_records,
        "content_excluded": content_excluded,
        "exclusions": exclusions,
        "unselected_archive_file_count": unselected_count if not unselected_scope_not_enumerated else None,
        "unselected_directory_paths_enumerated": not unselected_scope_not_enumerated,
        "license_evaluation": license_record,
        "reuse_status": license_record["reuse_status"],
        "limits": asdict(limits),
    }
    manifest_bytes = _canonical_json(pack_manifest)
    if len(files) + 1 > MAX_CLASSIC_ZIP_ENTRIES:
        raise SourcePackError("source pack exceeds classic ZIP entry count")
    estimated_size = _zip_output_size(files, manifest_bytes)
    if estimated_size > limits.max_output_bytes:
        raise SourcePackError("deterministic source pack exceeds max_output_bytes")

    temp_name: str | None = None
    try:
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{resolved_output.name}.", suffix=".tmp", dir=resolved_output.parent
        )
        os.close(fd)
        with zipfile.ZipFile(temp_name, mode="w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
            archive.writestr(_zip_info(PACK_MANIFEST_PATH), manifest_bytes)
            for path, data in sorted(files.items(), key=lambda item: (item[0].casefold(), item[0])):
                archive.writestr(_zip_info(path), data)
        with open(temp_name, "rb+") as handle:
            os.fsync(handle.fileno())
        actual_size = os.path.getsize(temp_name)
        if actual_size != estimated_size or actual_size > limits.max_output_bytes:
            raise SourcePackError("source pack output size failed its deterministic bound check")
        os.link(temp_name, resolved_output)
        os.unlink(temp_name)
        temp_name = None
    except SourcePackError:
        raise
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise SourcePackError("source pack could not be written atomically") from exc
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
    return pack_manifest


def main(argv: list[str] | None = None) -> int:
    defaults = SourcePackLimits()
    parser = argparse.ArgumentParser(description="Create a deterministic, bounded static source pack (no execution).")
    parser.add_argument("--source", required=True, help="local source directory or ZIP/uncompressed TAR archive")
    parser.add_argument("--source-manifest", required=True, help="strict provenance and selected-path JSON")
    parser.add_argument("--out", required=True, help="new ZIP output path; existing files are not overwritten")
    parser.add_argument("--max-files", type=int, default=defaults.max_files)
    parser.add_argument("--max-file-bytes", type=int, default=defaults.max_file_bytes)
    parser.add_argument("--max-total-bytes", type=int, default=defaults.max_total_bytes)
    parser.add_argument("--max-depth", type=int, default=defaults.max_depth)
    parser.add_argument("--max-output-bytes", type=int, default=defaults.max_output_bytes)
    parser.add_argument("--max-archive-bytes", type=int, default=defaults.max_archive_bytes)
    parser.add_argument("--max-archive-entries", type=int, default=defaults.max_archive_entries)
    parser.add_argument("--max-compression-ratio", type=int, default=defaults.max_compression_ratio)
    args = parser.parse_args(argv)
    try:
        limits = SourcePackLimits(
            max_files=args.max_files,
            max_file_bytes=args.max_file_bytes,
            max_total_bytes=args.max_total_bytes,
            max_depth=args.max_depth,
            max_output_bytes=args.max_output_bytes,
            max_archive_bytes=args.max_archive_bytes,
            max_archive_entries=args.max_archive_entries,
            max_compression_ratio=args.max_compression_ratio,
        )
        result = pack_static_source(args.source, args.source_manifest, args.out, limits=limits)
    except SourcePackError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(f"PACKED: {args.out} files={len(result['selected_paths'])} content_excluded={result['content_excluded']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
