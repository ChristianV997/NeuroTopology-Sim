"""DS005620 EEG signal-block adapter contract.

Turns fixture EEG-like files (CSV/TSV/TXT) into windowed numeric signal blocks.

Does NOT:
- download data
- add dependencies (stdlib-only)
- extract Level M features
- perform Level T topology
- train models
- make consciousness/soul/liberation/afterlife/ontology claims
"""
from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional
import hashlib


_BANNED_PHRASES = [
    "consciousness",
    "soul",
    "liberation",
    "afterlife",
    "sentient",
    "enlightenment",
    "awakening",
    "nirvana",
    "transcendence",
]

_SAFE_CLAIM = (
    "Local EEG-like signal files were parsed into operational signal-window metadata "
    "for future Level M feature extraction."
)

_TIME_COLUMN_NAMES = {"time", "t", "timestamp", "seconds", "sec"}


def _validate_safe_text(text: str) -> None:
    """Raise ValueError if text contains any banned phrase.

    Args:
        text: Text to validate.

    Raises:
        ValueError: If any banned phrase is found.
    """
    lower = text.lower()
    for phrase in _BANNED_PHRASES:
        if phrase in lower:
            raise ValueError(f"Banned phrase detected in output text: {phrase!r}")


@dataclass
class EEGSignalFile:
    """Parsed numeric signal from a single EEG fixture file."""
    path: str
    readable: bool
    adapter: Optional[str] = None
    n_channels: Optional[int] = None
    n_samples: Optional[int] = None
    sample_rate_hz: Optional[float] = None
    duration_s: Optional[float] = None
    channel_names: list[str] = field(default_factory=list)
    samples: list[list[float]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # "header" | "caller_explicit" | None when missing (fail-closed).
    sample_rate_source: Optional[str] = None
    # False when sample rate was caller-supplied without a file header, or missing.
    scientific_eligible: bool = False
    # True when sample_rate_hz was caller-imputed (blocks scientific eligibility).
    imputed: bool = False


@dataclass
class EEGSignalWindow:
    """Metadata-only descriptor for a single windowed signal block."""
    file_path: str
    row_id: str
    window_id: str
    window_start_s: float
    window_end_s: float
    sample_start: int
    sample_end: int
    n_channels: int
    n_samples: int
    sample_rate_hz: float
    channel_names: list[str] = field(default_factory=list)
    status: str = "ok"
    warnings: list[str] = field(default_factory=list)


_PROBE_EVIDENCE_CLASS = "fixture_signal_block_scaffold"
_PROBE_RUN_MODE = "offline_fixture"


@dataclass
class EEGSignalProbeResult:
    """Aggregate result from probing a set of EEG fixture files."""
    n_files: int
    n_readable_files: int
    n_skipped_files: int
    n_windows: int
    signal_files: list = field(default_factory=list)
    windows: list = field(default_factory=list)
    skipped_files: list[dict] = field(default_factory=list)
    reader_alignment_report: dict = field(default_factory=dict)
    safe_claim: str = ""
    forbidden_claims: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evidence_class: str = _PROBE_EVIDENCE_CLASS
    run_mode: str = _PROBE_RUN_MODE
    scientific_pass: bool = False


def parse_fixture_signal_file(
    path: str,
    sample_rate_hz: Optional[float] = None,
) -> EEGSignalFile:
    """Parse a fixture text file (CSV/TSV/TXT) into a numeric signal.

    Reads header comments of the form:
        # channels: 8
        # sample_rate: 250.0
        # channel_names: ch1,ch2,...

    Then reads numeric data rows. A header row with column names is detected
    and used for channel_names if not already set via comment header.
    Time columns (time/t/timestamp/seconds/sec) are stripped automatically.

    Sample rate policy (fail-closed / no silent 100 Hz default):
    - Prefer ``# sample_rate:`` from the file header (``sample_rate_source=header``,
      ``scientific_eligible=True`` for the rate field).
    - Else an explicit ``sample_rate_hz`` caller argument
      (``sample_rate_source=caller_explicit``, ``scientific_eligible=False``).
    - Else the file is not scientifically usable: ``readable=False`` with
      ``missing_sample_rate_hz`` error (no silent default).

    Args:
        path: Path to the fixture file.
        sample_rate_hz: Explicit caller sample rate when the file has no header.

    Returns:
        EEGSignalFile with parsed data.
    """
    p = Path(path)
    result = EEGSignalFile(
        path=str(p),
        readable=False,
        adapter="fixture_text",
    )

    if not p.exists():
        result.errors.append(f"File not found: {path}")
        result.errors.append("missing_file")
        return result

    ext = p.suffix.lower()
    if ext not in {".csv", ".tsv", ".txt"}:
        result.errors.append(f"unsupported_or_dependency_missing: extension {ext}")
        return result

    try:
        with open(p, "r", newline="", encoding="utf-8") as f:
            raw = f.read()
    except Exception as e:
        result.errors.append(f"Could not read file: {e}")
        return result

    lines = raw.splitlines()

    n_channels_header: Optional[int] = None
    sr_header: Optional[float] = None
    channel_names_header: Optional[list[str]] = None
    data_rows: list[list[float]] = []
    detected_header_row: Optional[list[str]] = None
    errors: list[str] = []
    warnings: list[str] = []

    # Determine delimiter
    delimiter = ","
    if ext == ".tsv":
        delimiter = "\t"
    elif ext == ".txt":
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "\t" in stripped:
                delimiter = "\t"
            elif "," in stripped:
                delimiter = ","
            else:
                delimiter = None  # whitespace-split
            break

    def _split(line: str) -> list[str]:
        if delimiter is None:
            return line.split()
        return [x.strip() for x in line.split(delimiter)]

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("#"):
            content = stripped[1:].strip()
            if content.lower().startswith("channels"):
                try:
                    n_channels_header = int(content.split(":", 1)[1].strip())
                except (ValueError, IndexError):
                    warnings.append(f"Line {i+1}: malformed channel count comment")
            elif content.lower().startswith("sample_rate"):
                try:
                    sr_header = float(content.split(":", 1)[1].strip())
                except (ValueError, IndexError):
                    warnings.append(f"Line {i+1}: malformed sample_rate comment")
            elif content.lower().startswith("channel_names"):
                try:
                    names_str = content.split(":", 1)[1].strip()
                    channel_names_header = [n.strip() for n in names_str.split(",")]
                except (ValueError, IndexError):
                    warnings.append(f"Line {i+1}: malformed channel_names comment")
            continue

        parts = _split(stripped)
        if not parts:
            continue

        try:
            nums = [float(x) for x in parts]
            data_rows.append(nums)
        except ValueError:
            if detected_header_row is None and all(not _is_numeric(x) for x in parts):
                detected_header_row = parts

    # Determine channel names
    channel_names: list[str] = []
    strip_first_col = False

    if channel_names_header:
        channel_names = channel_names_header
    elif detected_header_row:
        if detected_header_row[0].lower() in _TIME_COLUMN_NAMES:
            strip_first_col = True
            channel_names = detected_header_row[1:]
        else:
            channel_names = detected_header_row

    # Strip leading time column from data rows if detected
    if strip_first_col and data_rows:
        data_rows = [row[1:] if len(row) > 1 else row for row in data_rows]

    # Validate rectangular rows
    if data_rows:
        first_row_width = len(data_rows[0])
        inconsistent = [j for j, row in enumerate(data_rows) if len(row) != first_row_width]
        if inconsistent:
            warnings.append(
                f"{len(inconsistent)} rows have inconsistent column count (expected {first_row_width})"
            )
            data_rows = [r for r in data_rows if len(r) == first_row_width]

    # Determine final metadata
    n_ch_final: Optional[int] = None
    if n_channels_header is not None:
        n_ch_final = n_channels_header
    elif data_rows:
        n_ch_final = len(data_rows[0])

    imputed = False
    if sr_header is not None:
        sr_final: Optional[float] = float(sr_header)
        sr_source: Optional[str] = "header"
        scientific_eligible = True
    elif sample_rate_hz is not None:
        sr_final = float(sample_rate_hz)
        sr_source = "caller_explicit"
        scientific_eligible = False
        imputed = True
        warnings.append(
            "sample_rate_hz supplied by caller without file header; "
            "imputed=True blocks scientific_eligible (no silent default)"
        )
    else:
        sr_final = None
        sr_source = None
        scientific_eligible = False
        errors.append("missing_sample_rate_hz")

    if n_ch_final and not channel_names:
        channel_names = [f"ch_{j}" for j in range(n_ch_final)]

    n_samples = len(data_rows)
    duration_s = n_samples / sr_final if sr_final and n_samples else None

    result.readable = n_samples > 0 and sr_final is not None and sr_final > 0
    result.n_channels = n_ch_final
    result.n_samples = n_samples
    result.sample_rate_hz = sr_final
    result.duration_s = duration_s
    result.channel_names = channel_names[:n_ch_final] if n_ch_final and channel_names else channel_names
    result.samples = data_rows
    result.warnings = warnings
    result.errors = errors
    result.sample_rate_source = sr_source
    result.imputed = bool(imputed)
    # imputed=True always blocks scientific eligibility even if otherwise readable.
    result.scientific_eligible = bool(
        scientific_eligible and result.readable and not result.imputed
    )

    if n_samples <= 0:
        result.errors.append("no_numeric_signal_rows")
    elif sr_final is None:
        # Keep missing_sample_rate_hz as the primary blocker reason.
        pass

    return result


def _is_numeric(s: str) -> bool:
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def segment_signal_file(
    signal_file: EEGSignalFile,
    window_seconds: float = 10.0,
    max_windows: Optional[int] = None,
) -> list[EEGSignalWindow]:
    """Segment a parsed signal file into fixed-length windows.

    Args:
        signal_file: Parsed EEGSignalFile.
        window_seconds: Duration of each window in seconds.
        max_windows: Maximum number of windows to produce. None = no limit.

    Returns:
        List of EEGSignalWindow descriptors (metadata only, no raw samples).
    """
    windows: list[EEGSignalWindow] = []

    if not signal_file.readable or not signal_file.n_samples or not signal_file.sample_rate_hz:
        return windows

    stem = Path(signal_file.path).stem
    sr = signal_file.sample_rate_hz
    n_total = signal_file.n_samples
    n_ch = signal_file.n_channels or 0
    ch_names = signal_file.channel_names

    window_samples = int(math.floor(window_seconds * sr))
    if window_samples <= 0:
        window_samples = 1

    n_full_windows = n_total // window_samples

    # Short file: no full windows but has samples → emit one short window
    if n_full_windows == 0 and n_total > 0:
        row_id = f"{stem}__win_0"
        w = EEGSignalWindow(
            file_path=signal_file.path,
            row_id=row_id,
            window_id="win-000",
            window_start_s=0.0,
            window_end_s=n_total / sr,
            sample_start=0,
            sample_end=n_total,
            n_channels=n_ch,
            n_samples=n_total,
            sample_rate_hz=sr,
            channel_names=ch_names,
            status="short_window",
            warnings=[f"Window shorter than requested ({n_total} samples < {window_samples})"],
        )
        windows.append(w)
        return windows

    limit = n_full_windows
    if max_windows is not None:
        limit = min(limit, max_windows)

    for idx in range(limit):
        sample_start = idx * window_samples
        sample_end = sample_start + window_samples
        start_s = sample_start / sr
        end_s = sample_end / sr
        row_id = f"{stem}__win_{idx}"
        window_id = f"win-{idx:03d}"
        w = EEGSignalWindow(
            file_path=signal_file.path,
            row_id=row_id,
            window_id=window_id,
            window_start_s=start_s,
            window_end_s=end_s,
            sample_start=sample_start,
            sample_end=sample_end,
            n_channels=n_ch,
            n_samples=window_samples,
            sample_rate_hz=sr,
            channel_names=ch_names,
            status="full_window",
        )
        windows.append(w)

    return windows


def probe_signal_paths(
    paths: list[str],
    sample_rate_hz: Optional[float] = None,
    window_seconds: float = 10.0,
    max_windows_per_file: Optional[int] = 3,
) -> EEGSignalProbeResult:
    """Probe a list of file paths for signal block extraction.

    Args:
        paths: List of file paths to probe.
        sample_rate_hz: Explicit sample rate only when a file lacks a header.
            No silent 100 Hz default; omitted rates fail closed.
        window_seconds: Window duration in seconds.
        max_windows_per_file: Max windows per file. None = no limit.

    Returns:
        EEGSignalProbeResult with all signal files, windows, and metadata.
    """
    signal_files: list[EEGSignalFile] = []
    all_windows: list[EEGSignalWindow] = []
    skipped: list[dict] = []
    warnings: list[str] = []

    _FIXTURE_EXTENSIONS = {".csv", ".tsv", ".txt"}
    _BINARY_EXTENSIONS = {".edf", ".bdf", ".set", ".vhdr", ".fif", ".eeg"}

    for p in paths:
        path_obj = Path(p)
        ext = path_obj.suffix.lower()

        if ext in _BINARY_EXTENSIONS:
            skipped.append({
                "path": str(p),
                "reason": "unsupported_or_dependency_missing",
                "extension": ext,
            })
            warnings.append(f"Skipped {path_obj.name}: unsupported binary EEG extension {ext!r}")
            continue

        if ext not in _FIXTURE_EXTENSIONS:
            skipped.append({
                "path": str(p),
                "reason": f"unsupported_extension:{ext}",
            })
            warnings.append(f"Skipped {path_obj.name}: unsupported extension {ext!r}")
            continue

        if not path_obj.exists():
            skipped.append({
                "path": str(p),
                "reason": "missing_file",
            })
            warnings.append(f"Skipped {path_obj.name}: file not found")
            continue

        sig = parse_fixture_signal_file(str(p), sample_rate_hz=sample_rate_hz)
        signal_files.append(sig)
        warnings.extend(sig.warnings)

        if not sig.readable:
            reason = "no_numeric_signal_rows"
            if sig.errors and any("missing_sample_rate_hz" in e for e in sig.errors):
                reason = "missing_sample_rate_hz"
            elif sig.errors and any("no_numeric_signal_rows" in e for e in sig.errors):
                reason = "no_numeric_signal_rows"
            skipped.append({
                "path": str(p),
                "reason": reason,
                "errors": sig.errors,
            })
            continue

        wins = segment_signal_file(sig, window_seconds=window_seconds, max_windows=max_windows_per_file)
        all_windows.extend(wins)

    n_readable = sum(1 for sf in signal_files if sf.readable)
    n_skipped = len(skipped)

    _validate_safe_text(_SAFE_CLAIM)

    reader_alignment = _build_reader_alignment_report(signal_files, skipped, paths)
    # Any caller-explicit sample rate makes the probe non-scientific for rate provenance.
    any_caller_rate = any(sf.sample_rate_source == "caller_explicit" for sf in signal_files)
    scientific_pass = False  # fixture probe is never a scientific pass

    result = EEGSignalProbeResult(
        n_files=len(paths),
        n_readable_files=n_readable,
        n_skipped_files=n_skipped,
        n_windows=len(all_windows),
        signal_files=signal_files,
        windows=all_windows,
        skipped_files=skipped,
        reader_alignment_report=reader_alignment,
        safe_claim=_SAFE_CLAIM,
        forbidden_claims=[],
        warnings=warnings,
        evidence_class=_PROBE_EVIDENCE_CLASS,
        run_mode="offline_fixture_caller_rate" if any_caller_rate else _PROBE_RUN_MODE,
        scientific_pass=scientific_pass,
    )
    return result


def _build_reader_alignment_report(
    signal_files: list[EEGSignalFile],
    skipped: list[dict],
    all_paths: list[str],
) -> dict:
    """Build reader alignment report.

    Args:
        signal_files: List of parsed signal files.
        skipped: List of skipped-file dicts.
        all_paths: All input paths.

    Returns:
        Dict with alignment statistics including ready_for_p9_signal_extraction.
    """
    adapters_used: dict[str, int] = {}
    extensions_seen: dict[str, int] = {}
    readable_fixture_files = 0
    unsupported_binary_files = 0
    missing_files = 0
    no_numeric_signal_rows = 0

    for sf in signal_files:
        ext = Path(sf.path).suffix.lower()
        extensions_seen[ext] = extensions_seen.get(ext, 0) + 1
        if sf.adapter:
            adapters_used[sf.adapter] = adapters_used.get(sf.adapter, 0) + 1
        if sf.readable:
            readable_fixture_files += 1

    for item in skipped:
        ext = Path(item["path"]).suffix.lower()
        extensions_seen[ext] = extensions_seen.get(ext, 0) + 1
        reason = item.get("reason", "")
        if reason == "unsupported_or_dependency_missing":
            unsupported_binary_files += 1
        elif reason == "missing_file":
            missing_files += 1
        elif reason == "no_numeric_signal_rows":
            no_numeric_signal_rows += 1

    return {
        "used_reader_inspection": True,
        "readable_fixture_files": readable_fixture_files,
        "unsupported_binary_files": unsupported_binary_files,
        "missing_files": missing_files,
        "no_numeric_signal_rows": no_numeric_signal_rows,
        "ready_for_p9_signal_extraction": readable_fixture_files > 0,
        "note": (
            "Only fixture text extensions (.csv, .tsv, .txt) are processed. "
            "Binary EEG formats require the optional_mne adapter."
        ),
        "adapters_used": adapters_used,
        "extensions_seen": extensions_seen,
    }


def build_signal_block_inventory(result: EEGSignalProbeResult) -> dict:
    """Build a JSON-serialisable inventory of signal blocks.

    Args:
        result: Aggregate probe result.

    Returns:
        Dict with aggregate counts, extensions_seen, adapter_counts, sample_rate_values.
    """
    per_file = []
    extensions_seen: dict[str, int] = {}
    adapter_counts: dict[str, int] = {}
    sample_rate_values: list[float] = []

    for sf in result.signal_files:
        ext = Path(sf.path).suffix.lower()
        extensions_seen[ext] = extensions_seen.get(ext, 0) + 1
        if sf.adapter:
            adapter_counts[sf.adapter] = adapter_counts.get(sf.adapter, 0) + 1
        if sf.sample_rate_hz is not None:
            if sf.sample_rate_hz not in sample_rate_values:
                sample_rate_values.append(sf.sample_rate_hz)

        per_file.append({
            "path": sf.path,
            "readable": sf.readable,
            "adapter": sf.adapter,
            "n_channels": sf.n_channels,
            "n_samples": sf.n_samples,
            "sample_rate_hz": sf.sample_rate_hz,
            "sample_rate_source": sf.sample_rate_source,
            "scientific_eligible": sf.scientific_eligible,
            "imputed": sf.imputed,
            "duration_s": sf.duration_s,
            "channel_names": sf.channel_names,
            "n_warnings": len(sf.warnings),
            "n_errors": len(sf.errors),
        })

    for item in result.skipped_files:
        ext = Path(item["path"]).suffix.lower()
        extensions_seen[ext] = extensions_seen.get(ext, 0) + 1

    return {
        "n_files": result.n_files,
        "n_readable_files": result.n_readable_files,
        "n_skipped_files": result.n_skipped_files,
        "n_windows": result.n_windows,
        "extensions_seen": extensions_seen,
        "adapter_counts": adapter_counts,
        "sample_rate_values": sorted(sample_rate_values),
        "files": per_file,
        "safe_claim": result.safe_claim,
        "evidence_class": result.evidence_class,
        "run_mode": result.run_mode,
        "scientific_pass": result.scientific_pass,
    }


def build_reader_alignment_report(result: EEGSignalProbeResult) -> dict:
    """Build reader alignment report from a probe result.

    Args:
        result: Aggregate probe result.

    Returns:
        Dict with alignment statistics.
    """
    return result.reader_alignment_report


def _build_omega_event(result: EEGSignalProbeResult) -> dict:
    """Build a minimal omega event record for the probe run."""
    payload = f"probe:{result.n_files}:{result.n_windows}:{result.safe_claim}"
    event_id = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return {
        "event_id": event_id,
        "event_type": "signal_block_probe",
        "n_files": result.n_files,
        "n_readable_files": result.n_readable_files,
        "n_windows": result.n_windows,
        "safe_claim": result.safe_claim,
        "forbidden_claims": result.forbidden_claims,
        "warnings": result.warnings[:20],
        "evidence_class": result.evidence_class,
        "run_mode": result.run_mode,
        "scientific_pass": result.scientific_pass,
    }


def _build_markdown_report(result: EEGSignalProbeResult) -> str:
    """Build a Markdown summary report for the probe run."""
    _validate_safe_text(result.safe_claim)

    md = "# EEG Signal Block Probe\n\n"

    md += "## Stage\n\n"
    md += "P8.2 — Signal-block adapter contract. Parses fixture EEG-like files into "
    md += "operational signal-window metadata. Does NOT extract Level M features or "
    md += "perform Level T topology.\n\n"

    md += "## Evidence watermark\n\n"
    md += f"- evidence_class: {result.evidence_class}\n"
    md += f"- run_mode: {result.run_mode}\n"
    md += f"- scientific_pass: {result.scientific_pass}\n\n"

    md += "## Files Inspected\n\n"
    md += f"- Total files: {result.n_files}\n"
    md += f"- Readable files: {result.n_readable_files}\n"
    md += f"- Skipped files: {result.n_skipped_files}\n\n"

    md += "## Signal Files\n\n"
    if result.signal_files:
        for sf in result.signal_files[:20]:
            icon = "✓" if sf.readable else "✗"
            md += f"- {icon} {Path(sf.path).name}"
            if sf.n_channels:
                md += f" | {sf.n_channels} ch"
            if sf.sample_rate_hz:
                md += f" | {sf.sample_rate_hz} Hz"
            if sf.duration_s is not None:
                md += f" | {sf.duration_s:.2f} s"
            md += "\n"
    else:
        md += "_No signal files parsed._\n"
    md += "\n"

    md += "## Windows\n\n"
    md += f"Total signal block windows: {result.n_windows}\n\n"
    if result.windows:
        md += "| row_id | window_id | start_s | end_s | n_samples | status |\n"
        md += "|--------|-----------|---------|-------|-----------|--------|\n"
        for w in result.windows[:30]:
            md += (
                f"| {w.row_id} | {w.window_id} | {w.window_start_s:.2f} | "
                f"{w.window_end_s:.2f} | {w.n_samples} | {w.status} |\n"
            )
    md += "\n"

    md += "## Skipped Files\n\n"
    if result.skipped_files:
        for item in result.skipped_files[:10]:
            md += f"- {Path(item['path']).name}: {item['reason']}\n"
    else:
        md += "_No files skipped._\n"
    md += "\n"

    md += "## Reader Alignment\n\n"
    ra = result.reader_alignment_report
    md += f"- Used reader inspection: {ra.get('used_reader_inspection', False)}\n"
    md += f"- Readable fixture files: {ra.get('readable_fixture_files', 0)}\n"
    md += f"- Unsupported binary files: {ra.get('unsupported_binary_files', 0)}\n"
    md += f"- Missing files: {ra.get('missing_files', 0)}\n"
    md += f"- No numeric signal rows: {ra.get('no_numeric_signal_rows', 0)}\n"
    md += f"- Ready for P9 signal extraction: {ra.get('ready_for_p9_signal_extraction', False)}\n\n"

    md += "## Safe Claim\n\n"
    md += f"{result.safe_claim}\n\n"

    md += "## Forbidden Claims\n\n"
    if result.forbidden_claims:
        for claim in result.forbidden_claims:
            md += f"- {claim}\n"
    else:
        md += "_None. No consciousness, soul, liberation, afterlife, or ontology proof claims._\n"
    md += "\n"

    if result.warnings:
        md += f"## Warnings ({len(result.warnings)})\n\n"
        for warn in result.warnings[:10]:
            md += f"- {warn}\n"
        md += "\n"

    md += "## Next Required Step\n\n"
    md += "Use signal-window metadata for P9 real Level M signal feature extraction.\n\n"

    md += "---\n"
    md += "**Guardrail:** This signal block probe does not validate cognition, affect, physiology, "
    md += "or any metaphysical property.\n"
    return md


def write_signal_probe_outputs(
    result: EEGSignalProbeResult,
    out_dir: str,
) -> dict[str, str]:
    """Write signal probe outputs to files.

    Artifacts written:
        signal_block_inventory.json
        window_inventory.csv
        reader_alignment_report.json
        skipped_files.json
        omega_event.json
        report.md

    Args:
        result: Aggregate probe result.
        out_dir: Output directory path.

    Returns:
        Dict mapping artifact names to file paths written.
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}

    # 1. signal_block_inventory.json
    inventory = build_signal_block_inventory(result)
    inv_file = out_path / "signal_block_inventory.json"
    with open(inv_file, "w", encoding="utf-8") as f:
        json.dump(inventory, f, indent=2)
    outputs["signal_block_inventory"] = str(inv_file)

    # 2. window_inventory.csv
    win_file = out_path / "window_inventory.csv"
    with open(win_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "file_path", "row_id", "window_id",
            "window_start_s", "window_end_s",
            "sample_start", "sample_end",
            "n_channels", "n_samples", "sample_rate_hz",
            "channel_names", "status", "warnings",
        ])
        for w in result.windows:
            writer.writerow([
                w.file_path, w.row_id, w.window_id,
                w.window_start_s, w.window_end_s,
                w.sample_start, w.sample_end,
                w.n_channels, w.n_samples, w.sample_rate_hz,
                "|".join(w.channel_names),
                w.status,
                "|".join(w.warnings),
            ])
    outputs["window_inventory"] = str(win_file)

    # 3. reader_alignment_report.json
    align_file = out_path / "reader_alignment_report.json"
    with open(align_file, "w", encoding="utf-8") as f:
        json.dump(result.reader_alignment_report, f, indent=2)
    outputs["reader_alignment_report"] = str(align_file)

    # 4. skipped_files.json
    skip_file = out_path / "skipped_files.json"
    with open(skip_file, "w", encoding="utf-8") as f:
        json.dump({"skipped": result.skipped_files}, f, indent=2)
    outputs["skipped_files"] = str(skip_file)

    # 5. omega_event.json
    omega = _build_omega_event(result)
    omega_file = out_path / "omega_event.json"
    with open(omega_file, "w", encoding="utf-8") as f:
        json.dump(omega, f, indent=2)
    outputs["omega_event"] = str(omega_file)

    # 6. report.md
    md = _build_markdown_report(result)
    md_file = out_path / "report.md"
    with open(md_file, "w", encoding="utf-8") as f:
        f.write(md)
    outputs["report"] = str(md_file)

    return outputs
