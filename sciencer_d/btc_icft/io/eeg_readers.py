"""DS005620 EEG reader adapter contracts and inspection utilities.

This module provides stdlib-only reader capability inspection without hard
dependencies on MNE or other EEG packages. It classifies local EEG files
by readability and emits reader capability artifacts.

Does NOT:
- download data
- add dependencies
- implement real EEG feature extraction
- implement Level T topology
- make consciousness/soul/liberation/afterlife/ontology claims
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional
import importlib.util

SUPPORTED_FIXTURE_EXTENSIONS = {".txt", ".csv", ".tsv"}
KNOWN_EEG_EXTENSIONS = {".edf", ".bdf", ".set", ".vhdr", ".fif", ".eeg"}


@dataclass
class EEGReaderCapability:
    """Reader adapter capability descriptor."""
    adapter_name: str
    supported_extensions: list[str]
    dependency_required: Optional[str] = None
    dependency_available: bool = False
    status: str = "available"
    notes: list[str] = field(default_factory=list)


@dataclass
class EEGFileReadability:
    """Result of inspecting a single EEG file."""
    path: str
    extension: str
    exists: bool
    readable: bool
    adapter: Optional[str] = None
    status: str = "unknown"
    n_channels: Optional[int] = None
    sample_rate_hz: Optional[float] = None
    duration_s: Optional[float] = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class EEGChannelInventory:
    """Aggregate statistics from multiple file readability inspections."""
    n_files: int
    n_readable_files: int
    adapters_used: dict[str, int] = field(default_factory=dict)
    extensions_seen: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def get_reader_capabilities() -> dict[str, EEGReaderCapability]:
    """Build registry of available reader adapters.

    Returns:
        Dict mapping adapter_name to EEGReaderCapability.
    """
    mne_available = importlib.util.find_spec("mne") is not None

    return {
        "fixture_text": EEGReaderCapability(
            adapter_name="fixture_text",
            supported_extensions=[".txt", ".csv", ".tsv"],
            dependency_required=None,
            dependency_available=True,
            status="available",
            notes=["stdlib-only fixture adapter for text-based signal data"],
        ),
        "optional_mne": EEGReaderCapability(
            adapter_name="optional_mne",
            supported_extensions=[".edf", ".bdf", ".set", ".vhdr", ".fif"],
            dependency_required="mne",
            dependency_available=mne_available,
            status="available" if mne_available else "dependency_not_installed",
            notes=[
                "optional MNE adapter for standard EEG formats",
                "only available if mne package is installed",
            ],
        ),
    }


def _try_read_fixture_text(path: Path) -> tuple[bool, Optional[int], Optional[float], list[str]]:
    """Attempt to read a fixture text file and extract basic metadata.

    Args:
        path: Path to text file.

    Returns:
        (readable, n_channels, sample_rate_hz, errors) tuple.
    """
    try:
        with open(path, "r") as f:
            lines = f.readlines()

        if not lines:
            return False, None, None, ["File is empty"]

        n_channels = None
        sample_rate_hz = None
        errors = []

        for i, line in enumerate(lines[:10]):
            line = line.strip()
            if line.startswith("# channels"):
                try:
                    n_channels = int(line.split(":")[-1].strip())
                except (ValueError, IndexError):
                    errors.append(f"Line {i+1}: malformed channel count")
            if line.startswith("# sample_rate"):
                try:
                    sample_rate_hz = float(line.split(":")[-1].strip())
                except (ValueError, IndexError):
                    errors.append(f"Line {i+1}: malformed sample rate")

        return True, n_channels, sample_rate_hz, errors
    except Exception as e:
        return False, None, None, [str(e)]


def _try_read_mne(path: Path) -> tuple[bool, Optional[int], Optional[float], list[str]]:
    """Attempt to read an EEG file using MNE.

    Args:
        path: Path to EEG file.

    Returns:
        (readable, n_channels, sample_rate_hz, errors) tuple.
    """
    try:
        import mne

        suffix = "".join(path.suffixes).lower()
        raw = None

        if suffix.endswith((".fif", ".fif.gz")):
            raw = mne.io.read_raw_fif(str(path), preload=False, verbose="ERROR")
        elif suffix.endswith(".edf"):
            raw = mne.io.read_raw_edf(str(path), preload=False, verbose="ERROR")
        elif suffix.endswith(".bdf"):
            raw = mne.io.read_raw_bdf(str(path), preload=False, verbose="ERROR")
        elif suffix.endswith(".set"):
            raw = mne.io.read_raw_eeglab(str(path), preload=False, verbose="ERROR")
        elif suffix.endswith(".vhdr"):
            raw = mne.io.read_raw_brainvision(str(path), preload=False, verbose="ERROR")

        if raw is None:
            return False, None, None, ["Unsupported format or unable to load"]

        n_channels = raw.info["nchan"]
        sample_rate_hz = float(raw.info["sfreq"])
        return True, n_channels, sample_rate_hz, []
    except ImportError:
        return False, None, None, ["mne not installed"]
    except Exception as e:
        return False, None, None, [str(e)]


def inspect_eeg_file(path: str) -> EEGFileReadability:
    """Inspect a single EEG file for readability and metadata.

    Args:
        path: File path.

    Returns:
        EEGFileReadability with inspection results.
    """
    p = Path(path)
    ext = p.suffix.lower()
    result = EEGFileReadability(
        path=str(p),
        extension=ext,
        exists=p.exists(),
        readable=False,
        status="not_found" if not p.exists() else "unknown",
    )

    if not result.exists:
        result.errors.append(f"File not found: {path}")
        return result

    if ext in SUPPORTED_FIXTURE_EXTENSIONS:
        result.adapter = "fixture_text"
        readable, n_ch, sr, errs = _try_read_fixture_text(p)
        result.readable = readable
        result.n_channels = n_ch
        result.sample_rate_hz = sr
        result.errors = errs
        result.status = "readable" if readable else "unreadable_fixture"
        if not readable and not errs:
            result.errors = ["Unable to parse fixture text format"]

    elif ext in KNOWN_EEG_EXTENSIONS:
        readable, n_ch, sr, errs = _try_read_mne(p)
        if readable:
            result.adapter = "optional_mne"
            result.readable = True
            result.n_channels = n_ch
            result.sample_rate_hz = sr
            result.status = "readable_mne"
        else:
            result.adapter = "optional_mne"
            result.readable = False
            result.errors = errs
            result.status = "unsupported_or_dependency_missing"

    else:
        result.errors.append(f"Unknown extension: {ext}")
        result.status = "unknown_extension"

    return result


def inspect_eeg_files(paths: list[str]) -> list[EEGFileReadability]:
    """Inspect multiple EEG files.

    Args:
        paths: List of file paths.

    Returns:
        List of EEGFileReadability results.
    """
    return [inspect_eeg_file(p) for p in paths]


def build_reader_capability_report() -> dict:
    """Build a report of all available reader adapters.

    Returns:
        Dict with adapter capabilities and availability status.
    """
    caps = get_reader_capabilities()
    return {
        "reader_adapters": {
            name: {
                "adapter_name": cap.adapter_name,
                "supported_extensions": cap.supported_extensions,
                "dependency_required": cap.dependency_required,
                "dependency_available": cap.dependency_available,
                "status": cap.status,
                "notes": cap.notes,
            }
            for name, cap in caps.items()
        },
        "summary": {
            "total_adapters": len(caps),
            "adapters_available": sum(1 for c in caps.values() if c.status == "available"),
        },
    }


def build_channel_inventory(readability_rows: list[EEGFileReadability]) -> EEGChannelInventory:
    """Aggregate statistics from file readability inspections.

    Args:
        readability_rows: List of EEGFileReadability results.

    Returns:
        EEGChannelInventory with aggregated statistics.
    """
    n_files = len(readability_rows)
    n_readable = sum(1 for r in readability_rows if r.readable)

    adapters_used = {}
    extensions_seen = {}
    warnings = []

    for row in readability_rows:
        if row.adapter:
            adapters_used[row.adapter] = adapters_used.get(row.adapter, 0) + 1

        ext = row.extension.lower()
        if ext:
            extensions_seen[ext] = extensions_seen.get(ext, 0) + 1

        if row.warnings:
            warnings.extend(row.warnings)

    return EEGChannelInventory(
        n_files=n_files,
        n_readable_files=n_readable,
        adapters_used=adapters_used,
        extensions_seen=extensions_seen,
        warnings=warnings,
    )


def write_eeg_reader_outputs(
    readability_rows: list[EEGFileReadability],
    out_dir: str,
) -> dict[str, str]:
    """Write reader inspection outputs to files.

    Args:
        readability_rows: List of EEGFileReadability results.
        out_dir: Output directory path.

    Returns:
        Dict mapping output artifact names to file paths written.
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    outputs = {}

    # Write reader capability report
    cap_report = build_reader_capability_report()
    cap_file = out_path / "reader_capability_report.json"
    with open(cap_file, "w") as f:
        json.dump(cap_report, f, indent=2)
    outputs["reader_capability_report"] = str(cap_file)

    # Write file readability report
    readability_report = {
        "inspection_results": [asdict(r) for r in readability_rows],
        "total_files": len(readability_rows),
        "readable_files": sum(1 for r in readability_rows if r.readable),
    }
    read_file = out_path / "file_readability_report.json"
    with open(read_file, "w") as f:
        json.dump(readability_report, f, indent=2)
    outputs["file_readability_report"] = str(read_file)

    # Write channel inventory
    inventory = build_channel_inventory(readability_rows)
    inventory_file = out_path / "channel_inventory.json"
    with open(inventory_file, "w") as f:
        json.dump(asdict(inventory), f, indent=2)
    outputs["channel_inventory"] = str(inventory_file)

    # Write markdown report
    md_report = _build_markdown_report(readability_rows, cap_report, inventory)
    md_file = out_path / "report.md"
    with open(md_file, "w") as f:
        f.write(md_report)
    outputs["report"] = str(md_file)

    return outputs


def _build_markdown_report(
    readability_rows: list[EEGFileReadability],
    cap_report: dict,
    inventory: EEGChannelInventory,
) -> str:
    """Build markdown report of reader inspection.

    Args:
        readability_rows: File readability inspection results.
        cap_report: Reader capability report.
        inventory: Channel inventory statistics.

    Returns:
        Markdown report string.
    """
    md = "# DS005620 EEG Reader Adapter Inspection\n\n"

    md += "## Overview\n\n"
    md += "This is a **reader capability inspection**. It does NOT:\n"
    md += "- compute scientific evidence\n"
    md += "- train models\n"
    md += "- make consciousness, self, soul, liberation, afterlife, or ontology claims\n\n"

    md += "## Reader Capabilities\n\n"
    md += "| Adapter | Extensions | Status | Dependency |\n"
    md += "|---------|-----------|--------|------------|\n"

    for name, cap in cap_report["reader_adapters"].items():
        exts = ", ".join(cap["supported_extensions"][:3])
        dep = cap.get("dependency_required") or "None"
        status = cap["status"]
        md += f"| {cap['adapter_name']} | {exts} | {status} | {dep} |\n"

    md += f"\n## File Inspection Summary\n\n"
    md += f"- Total files: {inventory.n_files}\n"
    md += f"- Readable files: {inventory.n_readable_files}\n"
    md += f"- Adapters used: {dict(inventory.adapters_used)}\n"
    md += f"- Extensions seen: {dict(inventory.extensions_seen)}\n\n"

    if inventory.warnings:
        md += f"## Warnings ({len(inventory.warnings)})\n\n"
        for warn in inventory.warnings[:10]:
            md += f"- {warn}\n"

    md += f"\n## File Details\n\n"
    for row in readability_rows[:20]:
        status_icon = "✓" if row.readable else "✗"
        md += f"- {status_icon} {Path(row.path).name}: {row.status}\n"
        if row.n_channels:
            md += f"  - Channels: {row.n_channels}\n"
        if row.sample_rate_hz:
            md += f"  - Sample rate: {row.sample_rate_hz} Hz\n"

    md += "\n---\n"
    md += "**Guardrail:** This inspection does not validate consciousness.\n"

    return md
