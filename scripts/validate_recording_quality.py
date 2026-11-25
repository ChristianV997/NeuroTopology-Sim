#!/usr/bin/env python3
"""CLI utility for provenance-aware recording-quality gate.

Scientific guardrails:
- Header validation is not independent empirical validation.
- Synthetic data is never empirical evidence.
- No clinical claims.
- No label inference: never infer awake, sedated, meditation, or task states
  from filenames or directory structures.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

# Ensure repository root is in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shared.provenance.recording_quality import (
    RecordingQualityReport,
    RecordingQualityState,
    inspect_recording_quality,
)


def format_markdown_report(reports: Sequence[RecordingQualityReport]) -> str:
    """Format evaluation reports as Markdown."""
    lines: list[str] = [
        "# Recording Quality Gate Evaluation Report",
        "",
        "> **Scientific Guardrail:** Header validation is not independent empirical validation.",
        "> Synthetic fixtures are never empirical evidence.",
        "",
        "| Target Path | Quality State | Passed | Synthetic | Sfreq (Hz) | Channels | Checksum |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :--- |",
    ]

    for rep in reports:
        sfreq = f"{rep.metadata.sampling_rate_hz:.1f}" if (rep.metadata and rep.metadata.sampling_rate_hz) else "null"
        ch_count = str(rep.metadata.channel_count) if (rep.metadata and rep.metadata.channel_count) else "null"
        passed_mark = "PASS" if rep.passed_validation else "FAIL"
        synth_mark = "YES" if rep.is_synthetic else "NO"
        sha_short = rep.report_checksum_sha256[:8] if rep.report_checksum_sha256 else "null"
        target_name = Path(rep.target_path).name if rep.target_path else "unknown"
        lines.append(
            f"| `{target_name}` | `{rep.quality_state}` | {passed_mark} | {synth_mark} | {sfreq} | {ch_count} | `{sha_short}` |"
        )

    lines.append("")
    # Detail section
    for rep in reports:
        lines.append(f"## Target: `{rep.target_path}`")
        lines.append(f"- **State:** `{rep.quality_state}`")
        lines.append(f"- **Passed Validation:** `{rep.passed_validation}`")
        lines.append(f"- **Synthetic Flag:** `{rep.is_synthetic}`")
        if rep.issues:
            lines.append(f"- **Issues:**")
            for issue in rep.issues:
                lines.append(f"  - `{issue}`")
        if rep.warnings:
            lines.append(f"- **Warnings:**")
            for warn in rep.warnings:
                lines.append(f"  - {warn}")
        if rep.missing_dependencies:
            lines.append(f"- **Missing Dependencies:** {', '.join(rep.missing_dependencies)}")
        if rep.metadata and rep.metadata.montage:
            m = rep.metadata.montage
            cov = f"{m.coverage_ratio * 100:.1f}%" if m.coverage_ratio is not None else "null"
            lines.append(f"- **Montage Coverage:** {cov} ({m.channels_with_coordinates}/{m.total_channels})")
        lines.append(f"- **Report Checksum (SHA-256):** `{rep.report_checksum_sha256}`")
        lines.append("")

    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Provenance-aware recording-quality gate for local EEG/MEG containers."
    )
    parser.add_argument(
        "targets",
        nargs="*",
        help="One or more target file or BIDS directory paths.",
    )
    parser.add_argument(
        "--path",
        "-p",
        action="append",
        dest="paths",
        default=[],
        help="Explicit path to recording or container (can be repeated).",
    )
    parser.add_argument(
        "--bounded-samples",
        type=int,
        default=512,
        help="Max number of sample frames inspected for finiteness (default: 512).",
    )
    parser.add_argument(
        "--provenance-hint",
        choices=["auto", "empirical", "synthetic"],
        default="auto",
        help="Provenance assertion hint (default: 'auto').",
    )
    parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output serialization format (default: 'json').",
    )
    parser.add_argument(
        "--strict-empirical",
        action="store_true",
        help="Reject synthetic data; exit nonzero unless all targets are VALIDATED_EMPIRICAL_LOCAL.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Write report output to specified file path.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress terminal output.",
    )

    args = parser.parse_args(argv)

    all_targets = list(args.targets) + list(args.paths)
    if not all_targets:
        parser.error("At least one target recording path or container must be provided.")

    reports: list[RecordingQualityReport] = []
    for target in all_targets:
        rep = inspect_recording_quality(
            target_path=target,
            provenance_hint=args.provenance_hint,
            bounded_samples=args.bounded_samples,
        )
        # Ensure json/checksum generated
        rep.to_json()
        reports.append(rep)

    if args.format == "markdown":
        output_str = format_markdown_report(reports)
    else:
        if len(reports) == 1:
            output_str = reports[0].to_json(indent=2)
        else:
            report_dicts = [rep.to_dict() for rep in reports]
            output_str = json.dumps(report_dicts, indent=2, sort_keys=True, allow_nan=False)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_str, encoding="utf-8")

    if not args.quiet:
        print(output_str)

    # Determine exit code
    overall_pass = True
    for rep in reports:
        if not rep.passed_validation:
            overall_pass = False
            break
        if args.strict_empirical and rep.quality_state != RecordingQualityState.VALIDATED_EMPIRICAL_LOCAL.value:
            overall_pass = False
            break

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
