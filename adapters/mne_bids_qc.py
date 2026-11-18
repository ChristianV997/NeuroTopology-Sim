"""Channel / unit / sampling-rate QC for the existing `adapters.mne_bids*` chain.

Closes the gaps recorded against the `adapters.mne_bids*` test baseline:
missing / expected-channel reporting, explicit unit validation and
normalisation, channel-type checks, and a sidecar-vs-header sampling-rate
check. It is a QC layer only:

- It does not read files itself. Every read is delegated to existing code:
  recording header -> `data.bids_ingest.get_sample_rate` /
  `data.bids_ingest._read_raw_cached` (the same MNE reader the ingest path
  uses); `*_eeg.json` -> `data.bids_ingest._read_json_object` (bounded JSON
  reader); `*_channels.tsv` -> `mne_bids.tsv_handler._from_tsv` (mne-bids,
  already in requirements-eeg.txt); file checksums ->
  `data.bids_ingest._file_checksum_or_unknown`.
- It adds no new schema or contract id. Its output is a plain dict meant for
  the existing `DerivedFeatureRecipeManifestV1.qc_summary` field
  (`adapters.mne_bids_feature_recipe_schema`), under the key `channel_qc`.
- No label inference, no clinical claims, no composite score or detector.

Unit policy (voltage channel types only): allowed units are ``V``, ``mV`` and
``µV`` (``uV`` accepted as an ASCII alias of ``µV``). ``n/a``, empty or missing
units produce an explicit ``UNITS_MISSING`` flag and are never assumed.
Anything else produces ``UNIT_NOT_ALLOWED``.

Sampling-rate policy: the ``SamplingFrequency`` in ``*_eeg.json`` must equal
the recording header rate; a mismatch raises
:class:`SamplingFrequencyMismatchError` by default (``on_sfreq_mismatch="flag"``
records it instead).
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

QC_SUMMARY_KEY = "channel_qc"

# Allowed unit strings -> scale to volts. "uV" is an ASCII alias of "µV" (U+00B5).
ALLOWED_VOLTAGE_UNITS: Mapping[str, float] = {"V": 1.0, "mV": 1e-3, "\u00b5V": 1e-6, "uV": 1e-6}
CANONICAL_UNIT: Mapping[str, str] = {"V": "V", "mV": "mV", "\u00b5V": "\u00b5V", "uV": "\u00b5V"}
MISSING_UNIT_TOKENS: frozenset[str] = frozenset({"", "n/a", "na", "none", "null"})

# BIDS EEG channels.tsv `type` vocabulary (upper-case in BIDS).
BIDS_EEG_CHANNEL_TYPES: frozenset[str] = frozenset({
    "AUDIO", "EEG", "EOG", "ECG", "EMG", "EYEGAZE", "GSR", "HEOG", "MISC", "PPG", "PUPIL",
    "REF", "RESP", "SYSCLOCK", "TEMP", "TRIG", "VEOG",
})
VOLTAGE_CHANNEL_TYPES: frozenset[str] = frozenset({"EEG", "EOG", "ECG", "EMG", "HEOG", "VEOG", "REF"})

SFREQ_TOLERANCE_HZ = 1e-6


class ChannelQCError(ValueError):
    """Raised for structurally unusable QC inputs."""


class SamplingFrequencyMismatchError(ChannelQCError):
    """Raised when the sidecar SamplingFrequency disagrees with the recording header."""


@dataclass(frozen=True)
class QCFlag:
    code: str
    channel: Optional[str] = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "channel": self.channel, "detail": self.detail}


@dataclass
class ChannelQCReport:
    channel_names: list[str]
    channel_types: dict[str, str]
    units_declared: dict[str, Optional[str]]
    units_canonical: dict[str, Optional[str]]
    scale_to_volts: dict[str, Optional[float]]
    unit_qc_flags: dict[str, str]  # channel -> OK | UNITS_MISSING | UNIT_NOT_ALLOWED | NOT_VOLTAGE_TYPE
    expected_channels: list[str]
    missing_channel_mask: dict[str, bool]  # expected channel -> True if absent
    missing_channels: list[str]
    bad_channels: list[str]  # channels.tsv status == bad (as declared; not inferred)
    sampling_frequency_sidecar_hz: Optional[float]
    sampling_frequency_header_hz: Optional[float]
    sampling_frequency_mismatch: bool
    flags: list[QCFlag] = field(default_factory=list)
    input_files: list[dict[str, Any]] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "flagged" if self.flags else "pass"

    def to_qc_summary(self) -> dict[str, Any]:
        body = {
            "status": self.status,
            "channel_names": list(self.channel_names),
            "channel_types": dict(self.channel_types),
            "units_declared": dict(self.units_declared),
            "units_canonical": dict(self.units_canonical),
            "scale_to_volts": dict(self.scale_to_volts),
            "unit_qc_flags": dict(self.unit_qc_flags),
            "expected_channels": list(self.expected_channels),
            "missing_channel_mask": dict(self.missing_channel_mask),
            "missing_channels": list(self.missing_channels),
            "bad_channels": list(self.bad_channels),
            "sampling_frequency_sidecar_hz": self.sampling_frequency_sidecar_hz,
            "sampling_frequency_header_hz": self.sampling_frequency_header_hz,
            "sampling_frequency_mismatch": self.sampling_frequency_mismatch,
            "flags": [f.to_dict() for f in self.flags],
            "input_files": [dict(x) for x in self.input_files],
        }
        body["qc_hash"] = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        ).hexdigest()
        return {QC_SUMMARY_KEY: body}


# ── pure checks (no I/O) ─────────────────────────────────────────────────


def check_unit(unit: Any, channel_type: str) -> tuple[str, Optional[str], Optional[float]]:
    """Return (unit_qc_flag, canonical_unit, scale_to_volts) for one channel."""
    if channel_type not in VOLTAGE_CHANNEL_TYPES:
        return "NOT_VOLTAGE_TYPE", None, None
    text = "" if unit is None or (isinstance(unit, float) and math.isnan(unit)) else str(unit).strip()
    if text.lower() in MISSING_UNIT_TOKENS:
        return "UNITS_MISSING", None, None
    if text not in ALLOWED_VOLTAGE_UNITS:
        return "UNIT_NOT_ALLOWED", None, None
    return "OK", CANONICAL_UNIT[text], ALLOWED_VOLTAGE_UNITS[text]


def check_sampling_frequency(sidecar_hz: Any, header_hz: Optional[float]) -> tuple[Optional[float], bool, list[QCFlag]]:
    flags: list[QCFlag] = []
    try:
        side = None if sidecar_hz is None else float(sidecar_hz)
    except (TypeError, ValueError):
        side = None
    if side is None or not math.isfinite(side) or side <= 0:
        flags.append(QCFlag("SIDECAR_SFREQ_MISSING", None, f"SamplingFrequency={sidecar_hz!r}"))
        return None, False, flags
    if header_hz is None:
        flags.append(QCFlag("HEADER_SFREQ_MISSING"))
        return side, False, flags
    mismatch = abs(side - float(header_hz)) > SFREQ_TOLERANCE_HZ
    if mismatch:
        flags.append(QCFlag("SAMPLING_FREQUENCY_MISMATCH", None, f"sidecar={side} header={float(header_hz)}"))
    return side, mismatch, flags


def build_channel_qc(
    *,
    channel_rows: Sequence[Mapping[str, Any]],
    header_channel_names: Sequence[str],
    sidecar: Mapping[str, Any],
    header_sfreq_hz: Optional[float],
    expected_channels: Iterable[str] = (),
    on_sfreq_mismatch: str = "raise",
    input_files: Sequence[Mapping[str, Any]] = (),
) -> ChannelQCReport:
    """Pure QC over already-read metadata. ``channel_rows`` are channels.tsv rows."""
    if on_sfreq_mismatch not in {"raise", "flag"}:
        raise ChannelQCError("on_sfreq_mismatch must be 'raise' or 'flag'")
    if not channel_rows:
        raise ChannelQCError("channels.tsv has no rows")
    names = [str(r.get("name", "")).strip() for r in channel_rows]
    if any(not n for n in names):
        raise ChannelQCError("channels.tsv row without a name")
    if len(set(names)) != len(names):
        raise ChannelQCError("duplicate channel names in channels.tsv")

    flags: list[QCFlag] = []
    types: dict[str, str] = {}
    declared: dict[str, Optional[str]] = {}
    canonical: dict[str, Optional[str]] = {}
    scales: dict[str, Optional[float]] = {}
    unit_flags: dict[str, str] = {}
    bads: list[str] = []
    for name, row in zip(names, channel_rows):
        ctype = str(row.get("type", "") or "").strip().upper()
        if ctype not in BIDS_EEG_CHANNEL_TYPES:
            flags.append(QCFlag("UNKNOWN_CHANNEL_TYPE", name, f"type={row.get('type')!r}"))
        types[name] = ctype
        raw_unit = row.get("units")
        declared[name] = None if raw_unit is None else str(raw_unit)
        uflag, canon, scale = check_unit(raw_unit, ctype)
        unit_flags[name], canonical[name], scales[name] = uflag, canon, scale
        if uflag in {"UNITS_MISSING", "UNIT_NOT_ALLOWED"}:
            flags.append(QCFlag(uflag, name, f"units={raw_unit!r}"))
        if str(row.get("status", "") or "").strip().lower() == "bad":
            bads.append(name)

    used = sorted({canonical[n] for n in names if unit_flags[n] == "OK" and types[n] == "EEG"})
    if len(used) > 1:
        flags.append(QCFlag("MIXED_EEG_UNITS", None, ",".join(used)))

    header = [str(h) for h in header_channel_names]
    for n in names:
        if n not in header:
            flags.append(QCFlag("TSV_CHANNEL_NOT_IN_HEADER", n))
    for h in header:
        if h not in names:
            flags.append(QCFlag("HEADER_CHANNEL_NOT_IN_TSV", h))

    expected = list(dict.fromkeys(str(e) for e in expected_channels))
    present = set(names) & set(header) if header else set(names)
    mask = {e: e not in present for e in expected}
    missing = [e for e in expected if mask[e]]
    for e in missing:
        flags.append(QCFlag("MISSING_EXPECTED_CHANNEL", e))

    side, mismatch, sflags = check_sampling_frequency(sidecar.get("SamplingFrequency"), header_sfreq_hz)
    flags.extend(sflags)
    if mismatch and on_sfreq_mismatch == "raise":
        raise SamplingFrequencyMismatchError(sflags[-1].detail)

    return ChannelQCReport(
        channel_names=names,
        channel_types=types,
        units_declared=declared,
        units_canonical=canonical,
        scale_to_volts=scales,
        unit_qc_flags=unit_flags,
        expected_channels=expected,
        missing_channel_mask=mask,
        missing_channels=missing,
        bad_channels=bads,
        sampling_frequency_sidecar_hz=side,
        sampling_frequency_header_hz=None if header_sfreq_hz is None else float(header_sfreq_hz),
        sampling_frequency_mismatch=mismatch,
        flags=flags,
        input_files=[dict(x) for x in input_files],
    )


# ── orchestration through existing readers ───────────────────────────────


def qc_bids_recording(
    recording_path: str | Path,
    *,
    bids_root: str | Path,
    expected_channels: Iterable[str] = (),
    on_sfreq_mismatch: str = "raise",
) -> ChannelQCReport:
    """QC one BIDS EEG recording via the repository's existing readers.

    Requires the optional EEG profile (mne, mne-bids). Never downloads data.
    """
    from mne_bids import get_bids_path_from_fname
    from mne_bids.tsv_handler import _from_tsv

    from data.bids_ingest import _file_checksum_or_unknown, _read_json_object, _read_raw_cached, get_sample_rate

    recording_path = Path(recording_path)
    bids_root = Path(bids_root)
    bp = get_bids_path_from_fname(recording_path)
    channels_tsv = Path(bp.copy().update(suffix="channels", extension=".tsv").fpath)
    sidecar_json = Path(bp.copy().update(suffix="eeg", extension=".json").fpath)
    if not channels_tsv.is_file():
        raise ChannelQCError(f"missing channels.tsv for {recording_path.name}")
    if not sidecar_json.is_file():
        raise ChannelQCError(f"missing eeg.json for {recording_path.name}")

    tsv = _from_tsv(str(channels_tsv))
    n_rows = len(tsv.get("name", []))
    rows = [{k: v[i] for k, v in tsv.items()} for i in range(n_rows)]
    sidecar = _read_json_object(sidecar_json)
    raw = _read_raw_cached(str(recording_path))
    header_names = list(raw.ch_names)
    header_sfreq = get_sample_rate(str(recording_path))

    files = []
    for p in (recording_path, channels_tsv, sidecar_json):
        digest, status = _file_checksum_or_unknown(p)
        try:
            rel = p.resolve().relative_to(bids_root.resolve()).as_posix()
        except ValueError:
            rel = p.name
        files.append({"path": rel, "sha256": digest, "checksum_status": status})

    return build_channel_qc(
        channel_rows=rows,
        header_channel_names=header_names,
        sidecar=sidecar,
        header_sfreq_hz=header_sfreq,
        expected_channels=expected_channels,
        on_sfreq_mismatch=on_sfreq_mismatch,
        input_files=files,
    )
