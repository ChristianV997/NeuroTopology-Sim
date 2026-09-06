"""Local-only BIDS and empirical cohort manifest builder with provenance tracking.

This module discovers local electrophysiology files (FIF, EDF/BDF, BrainVision,
and fixture inputs), extracts provenance-tracked metadata, strictly preserves exact
condition labels without unconfigured inference, pairs recordings according to
configurable pairing keys, segregates synthetic fixtures, and evaluates downstream
readiness gates (NO_DATA, INSUFFICIENT_PAIRS, VALID_PAIRED_COHORT, MALFORMED_COHORT).
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import struct
from typing import Any, Sequence


class CohortStatus(str, Enum):
    """Downstream falsification cohort readiness status."""
    NO_DATA = "no_data"
    INSUFFICIENT_PAIRS = "insufficient_pairs"
    VALID_PAIRED_COHORT = "valid_paired_cohort"
    MALFORMED_COHORT = "malformed_cohort"


class DatasetType(str, Enum):
    """Origin nature of dataset recording."""
    EMPIRICAL = "empirical"
    SYNTHETIC_FIXTURE = "synthetic_fixture"


class FileFormat(str, Enum):
    """Recognized electrophysiology recording format."""
    FIF = "fif"
    EDF = "edf"
    BDF = "bdf"
    BRAINVISION = "brainvision"
    NPY = "npy"
    CSV = "csv"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ProvenanceRecord:
    """Provenance tracking indicating the origin of each extracted metadata attribute."""
    subject_source: str = "null"
    session_source: str = "null"
    task_source: str = "null"
    condition_source: str = "null"
    run_source: str = "null"
    datatype_source: str = "null"
    sample_rate_source: str = "null"
    channel_count_source: str = "null"
    montage_state_source: str = "null"


@dataclass
class RecordingRecord:
    """Metadata and provenance record for an individual discovered recording."""
    file_path: str
    format: str
    checksum: str
    subject: str | None = None
    session: str | None = None
    task: str | None = None
    condition: str | None = None
    run: str | None = None
    datatype: str | None = None
    sample_rate: float | None = None
    channel_count: int | None = None
    montage_state: str | None = None
    companion_files: list[str] = field(default_factory=list)
    is_synthetic: bool = False
    provenance: ProvenanceRecord = field(default_factory=ProvenanceRecord)
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return _safe_finite_dict(data)


@dataclass
class PairedSubjectRecord:
    """Pairing of condition A and condition B recordings matching a pairing key."""
    pairing_key: dict[str, str]
    condition_a_record: RecordingRecord
    condition_b_record: RecordingRecord

    def to_dict(self) -> dict[str, Any]:
        return {
            "pairing_key": self.pairing_key,
            "condition_a_record": self.condition_a_record.to_dict(),
            "condition_b_record": self.condition_b_record.to_dict(),
        }


@dataclass
class CohortManifest:
    """Full structured empirical cohort manifest and validation report."""
    schema: str = "NeuroTopologySim.PairedCohortManifest.v1"
    input_dir: str = ""
    condition_a: str = ""
    condition_b: str = ""
    pairing_keys: list[str] = field(default_factory=lambda: ["subject"])
    min_pairs: int = 2
    status: CohortStatus = CohortStatus.NO_DATA
    status_reason: str = ""
    allow_synthetic: bool = False
    total_recordings: int = 0
    empirical_paired_count: int = 0
    synthetic_paired_count: int = 0
    paired_records: list[PairedSubjectRecord] = field(default_factory=list)
    unpaired_records: list[dict[str, Any]] = field(default_factory=list)
    duplicate_candidates: list[dict[str, Any]] = field(default_factory=list)
    ambiguous_matches: list[dict[str, Any]] = field(default_factory=list)
    missing_files: list[dict[str, Any]] = field(default_factory=list)
    invalid_files: list[dict[str, Any]] = field(default_factory=list)
    all_recordings: list[RecordingRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _safe_finite_dict({
            "schema": self.schema,
            "input_dir": self.input_dir,
            "condition_a": self.condition_a,
            "condition_b": self.condition_b,
            "pairing_keys": self.pairing_keys,
            "min_pairs": self.min_pairs,
            "status": self.status.value,
            "status_reason": self.status_reason,
            "allow_synthetic": self.allow_synthetic,
            "total_recordings": self.total_recordings,
            "empirical_paired_count": self.empirical_paired_count,
            "synthetic_paired_count": self.synthetic_paired_count,
            "paired_records": [p.to_dict() for p in self.paired_records],
            "unpaired_records": self.unpaired_records,
            "duplicate_candidates": self.duplicate_candidates,
            "ambiguous_matches": self.ambiguous_matches,
            "missing_files": self.missing_files,
            "invalid_files": self.invalid_files,
            "all_recordings": [r.to_dict() for r in self.all_recordings],
        })

    def to_json(self, path: str | Path | None = None) -> str:
        payload = self.to_dict()
        text = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if path is not None:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        return text

    def to_csv(self, path: str | Path | None = None) -> str:
        headers = [
            "file_path",
            "format",
            "checksum",
            "subject",
            "session",
            "task",
            "condition",
            "run",
            "datatype",
            "sample_rate",
            "channel_count",
            "montage_state",
            "is_synthetic",
        ]
        rows: list[dict[str, Any]] = []
        for r in sorted(self.all_recordings, key=lambda x: (x.subject or "", x.session or "", x.condition or "", x.file_path)):
            rows.append({
                "file_path": r.file_path,
                "format": r.format,
                "checksum": r.checksum,
                "subject": r.subject or "",
                "session": r.session or "",
                "task": r.task or "",
                "condition": r.condition or "",
                "run": r.run or "",
                "datatype": r.datatype or "",
                "sample_rate": "" if r.sample_rate is None else f"{r.sample_rate:g}",
                "channel_count": "" if r.channel_count is None else str(r.channel_count),
                "montage_state": r.montage_state or "",
                "is_synthetic": "true" if r.is_synthetic else "false",
            })
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        csv_text = buf.getvalue()
        if path is not None:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(csv_text, encoding="utf-8")
        return csv_text


def _safe_finite_dict(val: Any) -> Any:
    """Recursively converts non-finite numbers to None for strict JSON compliance."""
    if isinstance(val, float):
        return val if math.isfinite(val) else None
    if isinstance(val, (int, str, bool)) or val is None:
        return val
    if isinstance(val, dict):
        return {str(k): _safe_finite_dict(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_safe_finite_dict(v) for v in val]
    return str(val)


def _compute_sha256(path: Path) -> str:
    """Computes deterministic SHA-256 block hash without network calls."""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def _is_synthetic_path(path: Path) -> bool:
    """Identifies if a file belongs to synthetic fixtures rather than empirical data."""
    parts = [p.lower() for p in path.parts]
    synthetic_tokens = {"synthetic", "fixture", "fixtures", "mock", "simulated", "surrogate"}
    for part in parts:
        for token in synthetic_tokens:
            if token in part:
                return True
    return False


def _parse_bids_entities(path: Path, root: Path | None = None) -> dict[str, tuple[str, str]]:
    """Extracts BIDS entities from filename and directory hierarchy with provenance.

    Returns dict mapping entity name -> (value, provenance_source).
    """
    entities: dict[str, tuple[str, str]] = {}
    stem = path.stem
    if stem.endswith(".fif"):
        stem = stem[:-4]

    # Standard BIDS pattern key-value
    for part in stem.split("_"):
        if "-" in part:
            key, val = part.split("-", 1)
            if key in ("sub", "ses", "task", "acq", "run", "cond", "condition", "split", "rec"):
                if key == "sub":
                    standard_key = "sub"
                    entity_val = val if val.startswith("sub-") else f"sub-{val}"
                elif key == "ses":
                    standard_key = "ses"
                    entity_val = val if val.startswith("ses-") else f"ses-{val}"
                elif key in ("cond", "condition"):
                    standard_key = "condition"
                    entity_val = val
                else:
                    standard_key = key
                    entity_val = val
                entities[standard_key] = (entity_val, "bids_filename")

    # Suffix for datatype
    last_token = stem.split("_")[-1]
    if last_token in ("eeg", "meg", "ieeg"):
        entities["datatype"] = (last_token, "bids_suffix")

    # Parent directory hierarchy fallback
    if root is not None:
        try:
            rel = path.relative_to(root)
            for parent_part in rel.parent.parts:
                if parent_part.startswith("sub-") and "sub" not in entities:
                    entities["sub"] = (parent_part, "directory_hierarchy")
                elif parent_part.startswith("ses-") and "ses" not in entities:
                    entities["ses"] = (parent_part, "directory_hierarchy")
                elif parent_part in ("eeg", "meg", "ieeg") and "datatype" not in entities:
                    entities["datatype"] = (parent_part, "directory_hierarchy")
        except ValueError:
            pass

    return entities


def _parse_brainvision_header(path: Path) -> tuple[float | None, int | None, str | None, list[str], list[str]]:
    """Parses BrainVision .vhdr file using pure Python standard library.

    Returns (sample_rate, channel_count, montage_state, companion_files, issues).
    """
    sample_rate: float | None = None
    channel_count: int | None = None
    montage_state: str | None = None
    companion_files: list[str] = []
    issues: list[str] = []

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return None, None, None, [], [f"vhdr_read_error: {exc}"]

    current_section = ""
    has_coordinates = False
    data_file: str | None = None
    marker_file: str | None = None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_section = line[1:-1].strip().lower()
            if current_section == "coordinates":
                has_coordinates = True
            continue

        if "=" in line:
            k, v = line.split("=", 1)
            k = k.strip().lower()
            v = v.split(";")[0].strip()
            if current_section == "common infos":
                if k == "datafile":
                    data_file = v
                elif k == "markerfile":
                    marker_file = v
                elif k == "numberofchannels":
                    try:
                        channel_count = int(v)
                    except ValueError:
                        pass
                elif k == "samplinginterval":
                    try:
                        microsec = float(v)
                        if microsec > 0:
                            sample_rate = 1_000_000.0 / microsec
                    except ValueError:
                        pass

    parent_dir = path.parent
    if data_file:
        data_path = parent_dir / data_file
        companion_files.append(str(data_path))
        if not data_path.is_file():
            issues.append(f"missing_companion_data_file: {data_file}")
    if marker_file:
        marker_path = parent_dir / marker_file
        companion_files.append(str(marker_path))
        if not marker_path.is_file():
            issues.append(f"missing_companion_marker_file: {marker_file}")

    if has_coordinates:
        montage_state = "custom_coordinates"
    elif channel_count is not None:
        montage_state = "unspecified"

    return sample_rate, channel_count, montage_state, companion_files, issues


def _parse_edf_bdf_header(path: Path) -> tuple[float | None, int | None, str | None, list[str]]:
    """Parses standard EDF / BDF binary header in pure Python standard library.

    Returns (sample_rate, channel_count, montage_state, issues).
    """
    issues: list[str] = []
    try:
        with path.open("rb") as f:
            header_fixed = f.read(256)
            if len(header_fixed) < 256:
                return None, None, None, ["truncated_edf_bdf_header"]

            # Bytes 0-8: identification
            version = header_fixed[:8].decode("ascii", errors="replace").strip()
            # Bytes 244-252: duration of a data record in seconds
            duration_str = header_fixed[244:252].decode("ascii", errors="replace").strip()
            # Bytes 252-256: number of signals
            ns_str = header_fixed[252:256].decode("ascii", errors="replace").strip()

            try:
                channel_count = int(ns_str)
            except ValueError:
                return None, None, None, [f"invalid_channel_count_field: {ns_str}"]

            try:
                record_duration = float(duration_str)
            except ValueError:
                record_duration = 1.0

            if channel_count <= 0:
                return None, 0, None, ["zero_channels_in_header"]

            # Per-signal fields: each field is (channel_count * field_len)
            # labels: 16 * ns
            # transducer: 80 * ns
            # physical dimension: 8 * ns
            # physical min: 8 * ns
            # physical max: 8 * ns
            # digital min: 8 * ns
            # digital max: 8 * ns
            # prefiltering: 80 * ns
            # number of samples in each data record: 8 * ns
            samples_per_record_offset = 256 + (16 + 80 + 8 + 8 + 8 + 8 + 8 + 80) * channel_count
            f.seek(samples_per_record_offset)
            samples_raw = f.read(8 * channel_count)
            if len(samples_raw) < 8:
                return None, channel_count, "unspecified", ["truncated_edf_signal_header"]

            sample_rate: float | None = None
            first_ch_samples_str = samples_raw[:8].decode("ascii", errors="replace").strip()
            try:
                nr_samples = int(first_ch_samples_str)
                if record_duration > 0 and nr_samples > 0:
                    sample_rate = float(nr_samples) / record_duration
            except ValueError:
                pass

            return sample_rate, channel_count, "unspecified", issues
    except Exception as exc:
        return None, None, None, [f"edf_bdf_read_error: {exc}"]


def _parse_fif_header(path: Path) -> tuple[float | None, int | None, str | None, list[str]]:
    """Parses FIF header via MNE if available, with offline fallback."""
    issues: list[str] = []
    try:
        import mne
        raw = mne.io.read_raw_fif(str(path), preload=False, verbose="ERROR")
        sfreq = float(raw.info["sfreq"])
        nchan = int(raw.info["nchan"])
        montage = "fif_dig_montage" if raw.info.get("dig") else "unspecified"
        return sfreq, nchan, montage, issues
    except ImportError:
        # Graceful fallback: MNE is not installed
        if path.stat().st_size == 0:
            return None, None, None, ["zero_byte_fif_file"]
        return None, None, None, issues
    except Exception as exc:
        issues.append(f"fif_parse_error: {exc}")
        return None, None, None, issues


def _parse_fixture_npy(path: Path) -> tuple[float | None, int | None, str | None, list[str]]:
    """Parses .npy fixture header for dimensionality."""
    issues: list[str] = []
    try:
        with path.open("rb") as f:
            magic = f.read(6)
            if magic != b"\x93NUMPY":
                return None, None, None, ["invalid_npy_magic"]
            version = f.read(2)
            if version[0] == 1:
                header_len = struct.unpack("<H", f.read(2))[0]
            else:
                header_len = struct.unpack("<I", f.read(4))[0]
            header_str = f.read(header_len).decode("ascii", errors="replace")
            # header_str is a dict repr: {'descr': '<f8', 'fortran_order': False, 'shape': (64, 1000)}
            shape_match = re.search(r"'shape':\s*\(([^)]+)\)", header_str)
            if shape_match:
                dims = [int(d.strip()) for d in shape_match.group(1).split(",") if d.strip()]
                if len(dims) >= 2:
                    # heuristic: min dimension is channel count if <= 512
                    ch_candidate = min(dims[0], dims[1]) if min(dims[0], dims[1]) <= 512 else dims[0]
                    return None, ch_candidate, "synthetic_fixture", issues
        return None, None, "synthetic_fixture", issues
    except Exception as exc:
        return None, None, "synthetic_fixture", [f"npy_parse_error: {exc}"]


def _parse_fixture_csv(path: Path) -> tuple[float | None, int | None, str | None, list[str]]:
    """Parses .csv fixture header for column count."""
    issues: list[str] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            first_line = f.readline().strip()
            if not first_line:
                return None, 0, "synthetic_fixture", ["empty_csv_fixture"]
            cols = [c.strip() for c in first_line.split(",") if c.strip()]
            return None, len(cols), "synthetic_fixture", issues
    except Exception as exc:
        return None, None, "synthetic_fixture", [f"csv_parse_error: {exc}"]


def _inspect_bids_sidecars(path: Path) -> dict[str, Any]:
    """Inspects potential BIDS sidecars (_eeg.json, _channels.tsv, _electrodes.tsv)."""
    meta: dict[str, Any] = {}
    parent = path.parent
    stem = path.stem
    if stem.endswith(".fif"):
        stem = stem[:-4]

    # Find JSON sidecars matching prefix
    prefix_tokens = stem.split("_")
    for i in range(len(prefix_tokens), 0, -1):
        candidate_prefix = "_".join(prefix_tokens[:i])
        candidate_json = parent / f"{candidate_prefix}_eeg.json"
        if candidate_json.is_file():
            try:
                data = json.loads(candidate_json.read_text(encoding="utf-8"))
                if "SamplingFrequency" in data:
                    meta["sample_rate"] = float(data["SamplingFrequency"])
                    meta["sample_rate_source"] = "sidecar_json"
                if "EEGChannelCount" in data:
                    meta["channel_count"] = int(data["EEGChannelCount"])
                    meta["channel_count_source"] = "sidecar_json"
                if "TaskName" in data:
                    meta["task"] = str(data["TaskName"])
                    meta["task_source"] = "sidecar_json"
                break
            except Exception:
                pass

    # Check channels.tsv
    candidate_channels = parent / f"{stem}_channels.tsv"
    if not candidate_channels.is_file():
        # Try generic channels.tsv
        for p in parent.glob("*_channels.tsv"):
            candidate_channels = p
            break
    if candidate_channels.is_file():
        try:
            lines = [l for l in candidate_channels.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
            if len(lines) > 1:
                meta["channel_count"] = len(lines) - 1
                meta["channel_count_source"] = "channels_tsv"
        except Exception:
            pass

    # Check electrodes.tsv
    for el in parent.glob("*_electrodes.tsv"):
        meta["montage_state"] = "bids_electrodes_tsv"
        meta["montage_state_source"] = "electrodes_tsv"
        break

    return meta


def inspect_file(path: Path, root: Path | None = None) -> RecordingRecord:
    """Inspects a single electrophysiology recording file and constructs its record with provenance."""
    norm_path = path.resolve()
    rel_path = str(norm_path.relative_to(root.resolve())) if root else str(norm_path)
    rel_path_posix = rel_path.replace("\\", "/")

    # Determine format
    suffix = path.suffix.lower()
    full_name = path.name.lower()
    if full_name.endswith(".fif.gz") or suffix == ".fif":
        fmt = FileFormat.FIF
    elif suffix == ".edf":
        fmt = FileFormat.EDF
    elif suffix == ".bdf":
        fmt = FileFormat.BDF
    elif suffix == ".vhdr":
        fmt = FileFormat.BRAINVISION
    elif suffix == ".npy":
        fmt = FileFormat.NPY
    elif suffix == ".csv":
        fmt = FileFormat.CSV
    else:
        fmt = FileFormat.UNKNOWN

    checksum = _compute_sha256(norm_path)
    is_synthetic = _is_synthetic_path(norm_path) or fmt in (FileFormat.NPY, FileFormat.CSV)

    # Extract BIDS entities
    bids = _parse_bids_entities(norm_path, root)
    subject = bids.get("sub", (None, "null"))[0]
    subject_source = bids.get("sub", (None, "null"))[1]
    session = bids.get("ses", (None, "null"))[0]
    session_source = bids.get("ses", (None, "null"))[1]
    task = bids.get("task", (None, "null"))[0]
    task_source = bids.get("task", (None, "null"))[1]
    run = bids.get("run", (None, "null"))[0]
    run_source = bids.get("run", (None, "null"))[1]
    datatype = bids.get("datatype", (None, "null"))[0]
    datatype_source = bids.get("datatype", (None, "null"))[1]

    # Explicit condition extraction: preserve exact condition label!
    if "condition" in bids:
        condition = bids["condition"][0]
        condition_source = bids["condition"][1]
    elif task is not None:
        condition = task
        condition_source = "bids_task"
    else:
        condition = None
        condition_source = "null"

    # Header parsing
    sample_rate: float | None = None
    channel_count: int | None = None
    montage_state: str | None = None
    companion_files: list[str] = []
    issues: list[str] = []

    if fmt == FileFormat.BRAINVISION:
        sample_rate, channel_count, montage_state, companion_files, issues = _parse_brainvision_header(norm_path)
        sr_source = "file_header" if sample_rate is not None else "null"
        cc_source = "file_header" if channel_count is not None else "null"
        ms_source = "file_header" if montage_state is not None else "null"
    elif fmt in (FileFormat.EDF, FileFormat.BDF):
        sample_rate, channel_count, montage_state, issues = _parse_edf_bdf_header(norm_path)
        sr_source = "file_header" if sample_rate is not None else "null"
        cc_source = "file_header" if channel_count is not None else "null"
        ms_source = "file_header" if montage_state is not None else "null"
    elif fmt == FileFormat.FIF:
        sample_rate, channel_count, montage_state, issues = _parse_fif_header(norm_path)
        sr_source = "file_header" if sample_rate is not None else "null"
        cc_source = "file_header" if channel_count is not None else "null"
        ms_source = "file_header" if montage_state is not None else "null"
    elif fmt == FileFormat.NPY:
        sample_rate, channel_count, montage_state, issues = _parse_fixture_npy(norm_path)
        sr_source = "null"
        cc_source = "file_header" if channel_count is not None else "null"
        ms_source = "synthetic_fixture"
    elif fmt == FileFormat.CSV:
        sample_rate, channel_count, montage_state, issues = _parse_fixture_csv(norm_path)
        sr_source = "null"
        cc_source = "file_header" if channel_count is not None else "null"
        ms_source = "synthetic_fixture"
    else:
        sr_source = "null"
        cc_source = "null"
        ms_source = "null"

    # Augment with sidecars if available
    sidecars = _inspect_bids_sidecars(norm_path)
    if sample_rate is None and "sample_rate" in sidecars:
        sample_rate = sidecars["sample_rate"]
        sr_source = sidecars["sample_rate_source"]
    if channel_count is None and "channel_count" in sidecars:
        channel_count = sidecars["channel_count"]
        cc_source = sidecars["channel_count_source"]
    if (montage_state is None or montage_state == "unspecified") and "montage_state" in sidecars:
        montage_state = sidecars["montage_state"]
        ms_source = sidecars["montage_state_source"]
    if task is None and "task" in sidecars:
        task = sidecars["task"]
        task_source = sidecars["task_source"]
        if condition is None:
            condition = task
            condition_source = "sidecar_task"

    provenance = ProvenanceRecord(
        subject_source=subject_source,
        session_source=session_source,
        task_source=task_source,
        condition_source=condition_source,
        run_source=run_source,
        datatype_source=datatype_source,
        sample_rate_source=sr_source,
        channel_count_source=cc_source,
        montage_state_source=ms_source,
    )

    return RecordingRecord(
        file_path=rel_path_posix,
        format=fmt.value,
        checksum=checksum,
        subject=subject,
        session=session,
        task=task,
        condition=condition,
        run=run,
        datatype=datatype,
        sample_rate=sample_rate,
        channel_count=channel_count,
        montage_state=montage_state,
        companion_files=[c.replace("\\", "/") for c in companion_files],
        is_synthetic=is_synthetic,
        provenance=provenance,
        issues=issues,
    )


def discover_recordings(
    input_dir: str | Path,
    *,
    recognized_formats: Sequence[str] | None = None,
) -> list[RecordingRecord]:
    """Recursively discovers local electrophysiology files without network access."""
    root = Path(input_dir).resolve()
    if not root.is_dir():
        return []

    target_extensions = {
        ".vhdr",
        ".edf",
        ".bdf",
        ".fif",
        ".npy",
        ".csv",
    }
    if recognized_formats is not None:
        target_extensions = {f".{fmt.lstrip('.').lower()}" for fmt in recognized_formats}

    discovered_paths: list[Path] = []
    # Offline recursive scan
    for dirpath, _, filenames in os.walk(root):
        dpath = Path(dirpath)
        for fname in sorted(filenames):
            fpath = dpath / fname
            # Handle .fif.gz
            if fname.lower().endswith(".fif.gz") and (".fif" in target_extensions or ".fif.gz" in target_extensions):
                discovered_paths.append(fpath)
                continue
            suffix = fpath.suffix.lower()
            if suffix in target_extensions:
                discovered_paths.append(fpath)

    # Sort deterministically
    discovered_paths.sort(key=lambda p: str(p.relative_to(root)))

    records: list[RecordingRecord] = []
    for p in discovered_paths:
        try:
            rec = inspect_file(p, root=root)
            records.append(rec)
        except Exception as exc:
            # Create a minimal invalid record
            records.append(RecordingRecord(
                file_path=str(p.relative_to(root)).replace("\\", "/"),
                format=p.suffix.lstrip(".").lower() or "unknown",
                checksum="0" * 64,
                issues=[f"unhandled_discovery_error: {exc}"],
            ))

    return records


def build_paired_cohort_manifest(
    input_dir: str | Path,
    *,
    condition_a: str,
    condition_b: str,
    pairing_keys: Sequence[str] = ("subject",),
    min_pairs: int = 2,
    condition_alias: dict[str, str] | None = None,
    allow_synthetic: bool = False,
    recognized_formats: Sequence[str] | None = None,
) -> CohortManifest:
    """Builds and validates paired cohort manifest matching condition A and condition B.

    Preserves exact condition labels unless aliased. Distinguishes:
    - NO_DATA
    - INSUFFICIENT_PAIRS
    - VALID_PAIRED_COHORT
    - MALFORMED_COHORT
    """
    root = Path(input_dir)
    pkeys = list(pairing_keys)
    alias_map = {k.strip(): v.strip() for k, v in (condition_alias or {}).items()}

    all_recordings = discover_recordings(root, recognized_formats=recognized_formats)

    if not all_recordings:
        return CohortManifest(
            input_dir=str(root),
            condition_a=condition_a,
            condition_b=condition_b,
            pairing_keys=pkeys,
            min_pairs=min_pairs,
            status=CohortStatus.NO_DATA,
            status_reason="No matching recording files discovered in input directory.",
            allow_synthetic=allow_synthetic,
            total_recordings=0,
        )

    # Check for invalid files and companion issues
    invalid_files: list[dict[str, Any]] = []
    missing_files: list[dict[str, Any]] = []

    for r in all_recordings:
        for issue in r.issues:
            if "missing_companion" in issue:
                missing_files.append({"file_path": r.file_path, "issue": issue})
            else:
                invalid_files.append({"file_path": r.file_path, "issue": issue})

    # Group recordings by pairing key
    # Pairing key dict: e.g. {"subject": "sub-01"}
    grouped: dict[tuple[tuple[str, str], ...], list[RecordingRecord]] = {}
    ambiguous_matches: list[dict[str, Any]] = []

    for r in all_recordings:
        # Check synthetic gate
        if r.is_synthetic and not allow_synthetic:
            continue

        # Extract pairing key tuple
        key_items: list[tuple[str, str]] = []
        missing_key = False
        for k in pkeys:
            val = getattr(r, k, None)
            if not val:
                missing_key = True
                break
            key_items.append((k, str(val)))

        if missing_key:
            ambiguous_matches.append({
                "file_path": r.file_path,
                "reason": f"missing_required_pairing_key_field: {pkeys}",
            })
            continue

        ktup = tuple(key_items)
        grouped.setdefault(ktup, []).append(r)

    paired_records: list[PairedSubjectRecord] = []
    unpaired_records: list[dict[str, Any]] = []
    duplicate_candidates: list[dict[str, Any]] = []

    for ktup, group in sorted(grouped.items(), key=lambda item: item[0]):
        key_dict = dict(ktup)

        # Match condition A and condition B
        cand_a: list[RecordingRecord] = []
        cand_b: list[RecordingRecord] = []

        for r in group:
            effective_cond = alias_map.get(r.condition, r.condition) if r.condition else None
            matched_a = (effective_cond == condition_a)
            matched_b = (effective_cond == condition_b)

            if matched_a and matched_b:
                ambiguous_matches.append({
                    "pairing_key": key_dict,
                    "file_path": r.file_path,
                    "condition": r.condition,
                    "reason": "condition_matches_both_a_and_b",
                })
            elif matched_a:
                cand_a.append(r)
            elif matched_b:
                cand_b.append(r)

        # Check duplicates
        if len(cand_a) > 1:
            duplicate_candidates.append({
                "pairing_key": key_dict,
                "condition": condition_a,
                "count": len(cand_a),
                "file_paths": [r.file_path for r in cand_a],
            })
        if len(cand_b) > 1:
            duplicate_candidates.append({
                "pairing_key": key_dict,
                "condition": condition_b,
                "count": len(cand_b),
                "file_paths": [r.file_path for r in cand_b],
            })

        if len(cand_a) == 1 and len(cand_b) == 1:
            rec_a = cand_a[0]
            rec_b = cand_b[0]
            paired_records.append(PairedSubjectRecord(
                pairing_key=key_dict,
                condition_a_record=rec_a,
                condition_b_record=rec_b,
            ))
        elif len(cand_a) > 0 and len(cand_b) == 0:
            unpaired_records.append({
                "pairing_key": key_dict,
                "present_condition": condition_a,
                "missing_condition": condition_b,
                "file_paths": [r.file_path for r in cand_a],
            })
        elif len(cand_a) == 0 and len(cand_b) > 0:
            unpaired_records.append({
                "pairing_key": key_dict,
                "present_condition": condition_b,
                "missing_condition": condition_a,
                "file_paths": [r.file_path for r in cand_b],
            })
        elif len(cand_a) == 0 and len(cand_b) == 0:
            unpaired_records.append({
                "pairing_key": key_dict,
                "present_condition": None,
                "missing_condition": f"{condition_a}_and_{condition_b}",
                "file_paths": [r.file_path for r in group],
            })

    empirical_pairs = [p for p in paired_records if not (p.condition_a_record.is_synthetic or p.condition_b_record.is_synthetic)]
    synthetic_pairs = [p for p in paired_records if (p.condition_a_record.is_synthetic or p.condition_b_record.is_synthetic)]

    empirical_count = len(empirical_pairs)
    synthetic_count = len(synthetic_pairs)

    # Evaluate readiness status
    # Check if cohort is malformed
    if not paired_records and (invalid_files or (all_recordings and not grouped and ambiguous_matches)):
        status = CohortStatus.MALFORMED_COHORT
        status_reason = f"Cohort malformed: {len(invalid_files)} invalid files and {len(ambiguous_matches)} ambiguous matches prevented pairing."
    elif empirical_count < min_pairs:
        status = CohortStatus.INSUFFICIENT_PAIRS
        status_reason = f"Insufficient paired subjects: found {empirical_count} empirical pairs, but minimum required is {min_pairs}."
    else:
        status = CohortStatus.VALID_PAIRED_COHORT
        status_reason = f"Valid paired cohort: {empirical_count} paired subjects satisfy minimum requirement of {min_pairs}."

    return CohortManifest(
        input_dir=str(root),
        condition_a=condition_a,
        condition_b=condition_b,
        pairing_keys=pkeys,
        min_pairs=min_pairs,
        status=status,
        status_reason=status_reason,
        allow_synthetic=allow_synthetic,
        total_recordings=len(all_recordings),
        empirical_paired_count=empirical_count,
        synthetic_paired_count=synthetic_count,
        paired_records=paired_records,
        unpaired_records=unpaired_records,
        duplicate_candidates=duplicate_candidates,
        ambiguous_matches=ambiguous_matches,
        missing_files=missing_files,
        invalid_files=invalid_files,
        all_recordings=all_recordings,
    )
