"""Lazy local EEG/MEG container readers for provenance inspection.

Header and sidecar metadata only. These readers do not load signal samples,
install packages, download files, or mutate DatasetProvenance.v1 / RunRecordV1.
A local checksum is not independent empirical validation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
import hashlib
import importlib
import importlib.util
import json
import math
import re

SCHEMA = "NeuroTopologySim.ContainerInspection.v1"
PROVENANCE_SCHEMA = "NeuroTopologySim.DatasetProvenance.v1"
SUPPORTED_FORMATS = frozenset({"fif", "edf", "bdf", "vhdr", "bids"})
ORIGIN_LABELS = frozenset({"synthetic_demo", "empirical_local", "external_solver", "unavailable"})
OPTIONAL_DEPENDENCIES = ("mne",)
_BIDS_ENTITY_RE = re.compile(r"(sub|ses|task|run|acq|desc)-([A-Za-z0-9]+)")


class ContainerReaderError(ValueError):
    """Invalid container metadata or non-finite numeric field."""


@dataclass
class ContainerInspection:
    format: str | None
    checksum_sha256: str | None
    subject_id: str | None
    session_id: str | None
    task: str | None
    run: str | None
    channel_count: int | None
    channel_names: list[str]
    sampling_rate_hz: float | None
    units: dict[str, str | None]
    duration_s: float | None
    montage_state: str | None
    coordinate_status: str | None
    source_path: str | None
    sidecar_present: bool | None
    warnings: list[str] = field(default_factory=list)
    unavailable_fields: list[str] = field(default_factory=list)
    capability: str = "ok"
    optional_dependency: str | None = None
    origin: str = "empirical_local"
    sample_count: int | None = None
    samples_loaded: bool = False
    reader_kind: str = "container"
    schema: str = SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return json_safe(
            {
                "schema": SCHEMA,
                "reader_kind": self.reader_kind,
                "format": self.format,
                "checksum_sha256": self.checksum_sha256,
                "subject_id": self.subject_id,
                "session_id": self.session_id,
                "task": self.task,
                "run": self.run,
                "channel_count": self.channel_count,
                "channel_names": list(self.channel_names),
                "sampling_rate_hz": self.sampling_rate_hz,
                "units": dict(self.units),
                "duration_s": self.duration_s,
                "montage_state": self.montage_state,
                "coordinate_status": self.coordinate_status,
                "source_path": self.source_path,
                "sidecar_present": self.sidecar_present,
                "warnings": list(self.warnings),
                "unavailable_fields": list(self.unavailable_fields),
                "capability": self.capability,
                "optional_dependency": self.optional_dependency,
                "origin": self.origin,
                "sample_count": self.sample_count,
                "samples_loaded": False,
                "scientific_support": "not_claimed",
                "checksum_is_empirical_validation": False,
            }
        )

    def as_provenance_declaration(self) -> dict[str, Any]:
        """DatasetProvenance.v1-compatible declaration. Does not validate evidence."""
        fmt = self.format or "unavailable"
        return json_safe(
            {
                "schema": PROVENANCE_SCHEMA,
                "dataset_identifier": None,
                "condition_label": self.task,
                "subject_id": self.subject_id,
                "session_id": self.session_id,
                "local_path": self.source_path,
                "file_checksum_sha256": self.checksum_sha256,
                "file_format": fmt,
                "channel_count": self.channel_count,
                "sample_count": self.sample_count,
                "sampling_rate_hz": self.sampling_rate_hz,
                "units": {key: value for key, value in self.units.items() if value is not None},
                "montage_source": self.montage_state,
                "montage_channels": list(self.channel_names),
                "acquisition_metadata": {
                    "task": self.task,
                    "run": self.run,
                    "duration_s": self.duration_s,
                    "coordinate_status": self.coordinate_status,
                    "sidecar_present": self.sidecar_present,
                    "reader_kind": "container",
                },
                "preprocessing_steps": [],
                "filtering_bands_hz": {},
                "tda_configuration": {},
                "source_url": None,
                "license": None,
                "access_metadata": {"offline_only": True},
                "origin": self.origin,
                "acquisition_timestamp": None,
                "warnings": list(self.warnings)
                + ["container inspection is not array validation and is not empirical validation"],
            }
        )


def json_safe(value: Any, path: str = "$") -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContainerReaderError(f"{path} is not a finite JSON number")
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [json_safe(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, tuple):
        return [json_safe(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, Mapping):
        return {
            str(key): json_safe(item, f"{path}.{key}")
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    raise ContainerReaderError(f"{path} is not JSON-serializable ({type(value).__name__})")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def optional_dependency_state(name: str = "mne") -> dict[str, Any]:
    spec = importlib.util.find_spec(name)
    return {
        "name": name,
        "available": spec is not None,
        "capability": "available" if spec is not None else "missing_optional_dependency",
    }


def _missing_capability(fmt: str, path: Path | None, origin: str, dependency: str, warnings: list[str]) -> ContainerInspection:
    return ContainerInspection(
        format=fmt,
        checksum_sha256=sha256_file(path) if path is not None and path.is_file() else None,
        subject_id=None,
        session_id=None,
        task=None,
        run=None,
        channel_count=None,
        channel_names=[],
        sampling_rate_hz=None,
        units={"time": "s", "sampling_frequency": "Hz", "amplitude": None},
        duration_s=None,
        montage_state=None,
        coordinate_status="unavailable",
        source_path=str(path) if path is not None else None,
        sidecar_present=False,
        warnings=warnings,
        unavailable_fields=[
            "channel_count",
            "channel_names",
            "sampling_rate_hz",
            "duration_s",
            "montage_state",
        ],
        capability="missing_optional_dependency",
        optional_dependency=dependency,
        origin=origin,
    )


def _finite(name: str, value: Any) -> float | None:
    if value is None or value == "":
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ContainerReaderError(f"{name} must be a finite number")
    return number


def _finite_int(name: str, value: Any) -> int | None:
    number = _finite(name, value)
    return None if number is None else int(number)


def _bids_entities(path: Path) -> dict[str, str]:
    found = {key: value for key, value in _BIDS_ENTITY_RE.findall(path.name)}
    for parent in path.parents:
        if parent.name.startswith("sub-") and "sub" not in found:
            found["sub"] = parent.name.split("-", 1)[1]
        if parent.name.startswith("ses-") and "ses" not in found:
            found["ses"] = parent.name.split("-", 1)[1]
    return found


def _origin(value: str | None) -> str:
    origin = value or "empirical_local"
    if origin not in ORIGIN_LABELS:
        raise ContainerReaderError(f"origin {origin!r} is not recognized")
    return origin


def inspect_edf(path: Path, *, origin: str = "empirical_local") -> ContainerInspection:
    """Parse EDF/BDF header bytes only."""
    raw = path.read_bytes()
    if len(raw) < 256:
        raise ContainerReaderError("EDF/BDF header is shorter than 256 bytes")
    version = raw[0:8].decode("ascii", errors="replace")
    fmt = "bdf" if raw[0:1] == b"\xff" or "BIOSEMI" in version.upper() or path.suffix.lower() == ".bdf" else "edf"
    n_records = _finite("n_data_records", raw[236:244].decode("ascii", errors="replace").strip() or "0")
    record_duration = _finite("record_duration_s", raw[244:252].decode("ascii", errors="replace").strip() or "0")
    n_channels = _finite_int("channel_count", raw[252:256].decode("ascii", errors="replace").strip() or "0")
    header_bytes = _finite_int("header_bytes", raw[184:192].decode("ascii", errors="replace").strip() or "256") or 256
    names: list[str] = []
    units_amp: str | None = None
    samples_per_record: int | None = None
    if n_channels and len(raw) >= header_bytes:
        base = 256
        names = [
            raw[base + 16 * index : base + 16 * (index + 1)].decode("ascii", errors="replace").strip()
            for index in range(n_channels)
        ]
        unit_base = 256 + (16 + 80) * n_channels
        if len(raw) >= unit_base + 8:
            units_amp = raw[unit_base : unit_base + 8].decode("ascii", errors="replace").strip() or None
        sample_base = 256 + (16 + 80 + 8 + 8 + 8 + 8 + 8 + 80) * n_channels
        if len(raw) >= sample_base + 8:
            samples_per_record = _finite_int(
                "samples_per_record",
                raw[sample_base : sample_base + 8].decode("ascii", errors="replace").strip() or "0",
            )
    rate = None
    duration = None
    sample_count = None
    if record_duration and record_duration > 0 and samples_per_record:
        rate = samples_per_record / record_duration
    if n_records and record_duration and n_records >= 0:
        duration = n_records * record_duration
    if n_records and samples_per_record:
        sample_count = int(n_records * samples_per_record)
    entities = _bids_entities(path)
    unavailable = []
    if rate is None:
        unavailable.append("sampling_rate_hz")
    if not names:
        unavailable.append("channel_names")
    return ContainerInspection(
        format=fmt,
        checksum_sha256=sha256_file(path),
        subject_id=entities.get("sub"),
        session_id=entities.get("ses"),
        task=entities.get("task"),
        run=entities.get("run"),
        channel_count=n_channels,
        channel_names=names,
        sampling_rate_hz=rate,
        units={"time": "s", "sampling_frequency": "Hz", "amplitude": units_amp},
        duration_s=duration,
        montage_state="header_labels_only",
        coordinate_status="inferred" if names else "unavailable",
        source_path=str(path),
        sidecar_present=False,
        warnings=["EDF/BDF header parsed without loading samples"],
        unavailable_fields=unavailable,
        origin=_origin(origin),
        sample_count=sample_count,
    )


def inspect_brainvision(path: Path, *, origin: str = "empirical_local") -> ContainerInspection:
    """Parse BrainVision VHDR text. Does not load .eeg samples."""
    text = path.read_text(encoding="utf-8", errors="replace")
    values: dict[str, str] = {}
    names: list[str] = []
    section = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].lower()
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if section == "channel infos" and key.lower().startswith("ch"):
            names.append(value.split(",", 1)[0].strip())
        else:
            values[key.lower()] = value
    n_channels = _finite_int("NumberOfChannels", values.get("numberofchannels"))
    interval_us = _finite("SamplingInterval", values.get("samplinginterval"))
    rate = None if interval_us in (None, 0) else 1e6 / interval_us
    data_file = values.get("datafile")
    marker_file = values.get("markerfile")
    sidecar_present = bool(
        (data_file and (path.parent / data_file).is_file())
        or (marker_file and (path.parent / marker_file).is_file())
    )
    entities = _bids_entities(path)
    if n_channels and names and len(names) != n_channels:
        raise ContainerReaderError("BrainVision channel list does not match NumberOfChannels")
    return ContainerInspection(
        format="vhdr",
        checksum_sha256=sha256_file(path),
        subject_id=entities.get("sub"),
        session_id=entities.get("ses"),
        task=entities.get("task"),
        run=entities.get("run"),
        channel_count=n_channels,
        channel_names=names,
        sampling_rate_hz=rate,
        units={"time": "s", "sampling_frequency": "Hz", "amplitude": values.get("orientation") or None},
        duration_s=None,
        montage_state="vhdr_channel_infos" if names else "incomplete",
        coordinate_status="inferred" if names else "unavailable",
        source_path=str(path),
        sidecar_present=sidecar_present,
        warnings=["BrainVision VHDR parsed without loading .eeg samples"],
        unavailable_fields=["duration_s"] + ([] if names else ["channel_names"]),
        origin=_origin(origin),
    )


def inspect_bids_sidecar(path: Path, *, origin: str = "empirical_local") -> ContainerInspection:
    """Read BIDS JSON sidecar metadata. Does not load EEG/MEG bytes."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ContainerReaderError("BIDS sidecar must be a JSON object")
    rate = _finite("SamplingFrequency", payload.get("SamplingFrequency"))
    eeg_channels = payload.get("EEGChannelCount")
    meg_channels = payload.get("MEGChannelCount")
    n_channels = _finite_int("channel_count", eeg_channels if eeg_channels is not None else meg_channels)
    names: list[str] = []
    channels_tsv = path.with_name(path.name.replace("_eeg.json", "_channels.tsv").replace("_meg.json", "_channels.tsv"))
    if channels_tsv.is_file():
        rows = channels_tsv.read_text(encoding="utf-8").splitlines()
        if rows:
            header = rows[0].split("\t")
            name_index = header.index("name") if "name" in header else 0
            names = [line.split("\t")[name_index] for line in rows[1:] if line.strip()]
    entities = _bids_entities(path)
    montage = payload.get("EEGPlacementScheme") or payload.get("CapManufacturer")
    coordsystem = path.with_name(path.name.replace("_eeg.json", "_coordsystem.json").replace("_meg.json", "_coordsystem.json"))
    if coordsystem.is_file():
        coordinate_status = "native"
    elif montage:
        coordinate_status = "inferred"
    else:
        coordinate_status = "unavailable"
    return ContainerInspection(
        format="bids",
        checksum_sha256=sha256_file(path),
        subject_id=entities.get("sub"),
        session_id=entities.get("ses"),
        task=entities.get("task") or payload.get("TaskName"),
        run=entities.get("run"),
        channel_count=n_channels if n_channels is not None else (len(names) or None),
        channel_names=names,
        sampling_rate_hz=rate,
        units={"time": "s", "sampling_frequency": "Hz", "amplitude": payload.get("Units") or None},
        duration_s=_finite("RecordingDuration", payload.get("RecordingDuration")),
        montage_state=str(montage) if montage else None,
        coordinate_status=coordinate_status,
        source_path=str(path),
        sidecar_present=True,
        warnings=["BIDS sidecar parsed without loading recording bytes"],
        unavailable_fields=[name for name, value in (("sampling_rate_hz", rate), ("channel_count", n_channels or names)) if not value],
        origin=_origin(origin),
    )


def inspect_fif(
    path: Path,
    *,
    origin: str = "empirical_local",
    import_module=None,
    find_spec=None,
) -> ContainerInspection:
    """Inspect FIF via optional MNE with preload=False."""
    finder = find_spec or (lambda name: importlib.util.find_spec(name) is not None)
    if not finder("mne"):
        return _missing_capability(
            "fif",
            path,
            _origin(origin),
            "mne",
            ["FIF header inspection requires optional mne; package was not imported"],
        )
    loader = import_module or importlib.import_module
    mne = loader("mne")
    raw = mne.io.read_raw_fif(path, preload=False, verbose="ERROR")
    info = raw.info
    sfreq = _finite("sfreq", info.get("sfreq"))
    names = [str(name) for name in info.get("ch_names", [])]
    n_times = getattr(raw, "n_times", None)
    duration = None
    sample_count = None
    if n_times is not None:
        sample_count = _finite_int("n_times", n_times)
        if sfreq:
            duration = sample_count / sfreq
    montage = info.get("dig")
    coordinate_status = "native" if montage else ("inferred" if names else "unavailable")
    return ContainerInspection(
        format="fif",
        checksum_sha256=sha256_file(path),
        subject_id=_bids_entities(path).get("sub"),
        session_id=_bids_entities(path).get("ses"),
        task=_bids_entities(path).get("task"),
        run=_bids_entities(path).get("run"),
        channel_count=len(names) or _finite_int("nchan", info.get("nchan")),
        channel_names=names,
        sampling_rate_hz=sfreq,
        units={"time": "s", "sampling_frequency": "Hz", "amplitude": "V"},
        duration_s=duration,
        montage_state="fif_info_dig" if montage else "fif_channel_names",
        coordinate_status=coordinate_status,
        source_path=str(path),
        sidecar_present=False,
        warnings=["FIF inspected with preload=False; samples were not loaded"],
        unavailable_fields=[],
        origin=_origin(origin),
        sample_count=sample_count,
        optional_dependency="mne",
    )


def detect_format(path: Path) -> str | None:
    name = path.name.lower()
    suffix = path.suffix.lower()
    if name.endswith("_eeg.json") or name.endswith("_meg.json"):
        return "bids"
    mapping = {".fif": "fif", ".edf": "edf", ".bdf": "bdf", ".vhdr": "vhdr"}
    if suffix == ".gz" and name.endswith(".fif.gz"):
        return "fif"
    return mapping.get(suffix)


def inspect_local_recording(
    path: str | Path,
    *,
    origin: str = "empirical_local",
    import_module=None,
    find_spec=None,
) -> ContainerInspection:
    source = Path(path)
    if not source.is_file():
        raise ContainerReaderError(f"local container is missing: {source}")
    fmt = detect_format(source)
    if fmt is None:
        raise ContainerReaderError(
            f"unsupported container {source.suffix}; array NPY/NPZ validation is a separate contract"
        )
    if fmt in {"edf", "bdf"}:
        return inspect_edf(source, origin=origin)
    if fmt == "vhdr":
        return inspect_brainvision(source, origin=origin)
    if fmt == "bids":
        return inspect_bids_sidecar(source, origin=origin)
    return inspect_fif(source, origin=origin, import_module=import_module, find_spec=find_spec)
