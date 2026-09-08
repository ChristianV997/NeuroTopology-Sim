#!/usr/bin/env python3
"""CLI utility for memory-bounded multimodal physiology stream inspection.

Scientific guardrails:
- Physiological coupling is a candidate mechanism, not proof of a mental-state transition.
- Do not describe respiration or parasympathetic activity as equivalent to calmness,
  detachment, equanimity, or liberation.
- Synthetic data is never empirical evidence.
- No label inference: never infer awake, sedated, meditation, jhāna, task, or arousal
  states from filenames or paths; preserve operator labels verbatim.
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

from shared.data_loaders.physiology_types import (
    AlignmentMode,
    PhysiologyCapabilityState,
    PhysiologySummary,
)
from shared.data_loaders.physiology_stream import PhysiologyStreamReader


def format_markdown_stream_report(
    summary: PhysiologySummary,
    chunks_meta: list[dict],
) -> str:
    """Format physiology inspection summary as Markdown."""
    lines: list[str] = [
        "# Multimodal Physiology Stream Inspection Report",
        "",
        "> **Scientific Guardrail:** Physiological coupling is a candidate mechanism,",
        "> not proof of a mental-state transition. Respiration and autonomic metrics",
        "> quantify peripheral dynamics; they are not equivalent to mental states.",
        "",
        f"- **Source File:** `{summary.source_file}`",
        f"- **Capability State:** `{summary.capability_state}`",
        f"- **Synthetic Status:** `{summary.is_synthetic}`",
        f"- **Total Samples:** {summary.total_samples}",
        f"- **Duration (s):** {summary.duration_s if summary.duration_s is not None else 'null'}",
        f"- **Report Checksum (SHA-256):** `{summary.report_checksum_sha256}`",
        "",
        "## Channel Modality Inventory",
        "",
        "| Channel Name | Modality Type | Original Sfreq (Hz) | Aligned Sfreq (Hz) | Units | Bad |",
        "| :--- | :--- | :---: | :---: | :---: | :---: |",
    ]

    for ch in summary.channels:
        bad_mark = "YES" if ch.is_bad else "NO"
        lines.append(
            f"| `{ch.name}` | `{ch.channel_type}` | {ch.original_sfreq_hz:.1f} | {ch.aligned_sfreq_hz:.1f} | `{ch.units}` | {bad_mark} |"
        )

    lines.append("")
    lines.append("## Feature-Ready Physiological Summary")
    lines.append("")
    if summary.respiration:
        r = summary.respiration
        r_bpm = f"{r.respiratory_rate_bpm:.1f} BPM" if r.respiratory_rate_bpm is not None else "null"
        ie = f"{r.ie_ratio:.2f}" if r.ie_ratio is not None else "null"
        phase = f"{r.respiratory_phase_rad:.2f} rad" if r.respiratory_phase_rad is not None else "null"
        lines.append(f"- **Respiration:** Rate={r_bpm}, I:E Ratio={ie}, Phase={phase}")
    else:
        lines.append("- **Respiration:** null (channel missing or insufficient cycles)")

    if summary.cardiac:
        c = summary.cardiac
        hr_bpm = f"{c.heart_rate_bpm:.1f} BPM" if c.heart_rate_bpm is not None else "null"
        rmssd = f"{c.rmssd_ms:.1f} ms" if c.rmssd_ms is not None else "null"
        sdnn = f"{c.sdnn_ms:.1f} ms" if c.sdnn_ms is not None else "null"
        lines.append(f"- **Cardiac/HRV:** Heart Rate={hr_bpm}, RMSSD={rmssd}, SDNN={sdnn}")
    else:
        lines.append("- **Cardiac/HRV:** null (ECG channel missing or insufficient peaks)")

    if summary.quality:
        q = summary.quality
        sqi = f"{q.signal_quality_index:.2f}" if q.signal_quality_index is not None else "null"
        lines.append(f"- **Quality Metrics:** SQI={sqi}, Missingness={q.missingness_ratio:.2f}, FiniteRatio={q.finite_ratio:.2f}")

    lines.append("")
    lines.append(f"## Streamed Chunks Inspected ({len(chunks_meta)})")
    lines.append("")
    for c in chunks_meta:
        lines.append(
            f"- Chunk `{c['chunk_index']}`: samples `[{c['start_sample']}:{c['end_sample']}]`, time `[{c['start_time_s']:.2f}s - {c['end_time_s']:.2f}s]`, finite=`{c['finite_status']}`"
        )

    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect multimodal physiology stream and extract bounded physiological features."
    )
    parser.add_argument("target", help="Path to physiology recording file (FIF, EDF, BDF, BrainVision).")
    parser.add_argument(
        "--chunk-duration-s",
        type=float,
        default=1.0,
        help="Chunk duration in seconds (default: 1.0).",
    )
    parser.add_argument(
        "--common-sfreq-hz",
        type=float,
        default=None,
        help="Optional common clock sampling rate in Hz for aligned resampling.",
    )
    parser.add_argument(
        "--alignment-mode",
        choices=["causal", "noncausal"],
        default="causal",
        help="Alignment interpolation mode (default: 'causal').",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=5,
        help="Maximum number of chunks to stream (default: 5).",
    )
    parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output serialization format (default: 'json').",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Write inspection report to output file.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress terminal output.",
    )

    args = parser.parse_args(argv)

    mode = AlignmentMode.CAUSAL if args.alignment_mode == "causal" else AlignmentMode.NONCAUSAL
    reader = PhysiologyStreamReader(
        source_path=args.target,
        common_sfreq_hz=args.common_sfreq_hz,
        alignment_mode=mode,
    )

    if reader.capability_state != PhysiologyCapabilityState.AVAILABLE.value:
        summary = reader.compute_summary()
        out_json = summary.to_json(indent=2)
        if not args.quiet:
            print(out_json, file=sys.stderr)
        return 1

    chunks_meta: list[dict] = []
    for chunk in reader.iter_chunks(chunk_duration_s=args.chunk_duration_s, max_chunks=args.max_chunks):
        chunks_meta.append(chunk.to_dict())

    summary = reader.compute_summary()

    if args.format == "markdown":
        output_str = format_markdown_stream_report(summary, chunks_meta)
    else:
        full_report = {
            "summary": summary.to_dict(),
            "inspected_chunks": chunks_meta,
        }
        output_str = json.dumps(full_report, indent=2, sort_keys=True, allow_nan=False)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_str, encoding="utf-8")

    if not args.quiet:
        print(output_str)

    return 0


if __name__ == "__main__":
    sys.exit(main())
