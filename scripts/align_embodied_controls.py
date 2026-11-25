#!/usr/bin/env python3
"""CLI utility for aligning EEG neural windows with autonomic physiology.

Scientific guardrails:
- Embodied variables are candidate explanatory features, moderators, covariates,
  or possible intervention targets; they are not proven causal mechanisms.
- Do not label parasympathetic activity as calmness, slow breathing as equanimity,
  reward sensitivity as detachment, or autonomic change as liberation.
- No claim of causal mediation.
- Synthetic data is never empirical evidence.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.embodied_controls.aligner import EmbodiedControlAligner
from tools.embodied_controls.types import (
    EmbodiedControlAlignmentReport,
    InterpolationMethod,
)


def generate_demo_synthetic_data(
    duration_s: float = 40.0,
    window_len_s: float = 8.0,
    common_fs: float = 100.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Generate synthetic neural windows and multi-rate physiology for demonstration and testing."""
    n_samples_physio = int(duration_s * common_fs)
    t = np.arange(n_samples_physio) / common_fs

    # 1. Respiration: 0.3 Hz (~18 BPM) sine wave
    resp_sig = 0.8 * np.sin(2.0 * np.pi * 0.3 * t) + 0.1 * np.sin(2.0 * np.pi * 0.6 * t)

    # 2. ECG: R-peak impulses every 0.8s (75 BPM)
    ecg_sig = np.zeros(n_samples_physio)
    rr_interval_s = 0.8
    r_times = np.arange(0.2, duration_s - 0.2, rr_interval_s)
    for rt in r_times:
        idx = int(round(rt * common_fs))
        if 0 <= idx < n_samples_physio:
            ecg_sig[idx] = 1.5
            if idx > 0:
                ecg_sig[idx - 1] = -0.2
            if idx < n_samples_physio - 1:
                ecg_sig[idx + 1] = -0.3

    # 3. EDA: Slow tonic drift with small phasic response
    eda_sig = 5.0 + 0.5 * np.sin(2.0 * np.pi * 0.02 * t) + 0.05 * np.random.randn(n_samples_physio)

    physio_stream = {
        "respiration": resp_sig.tolist(),
        "respiration_fs": common_fs,
        "ecg": ecg_sig.tolist(),
        "ecg_fs": common_fs,
        "eda": eda_sig.tolist(),
        "eda_fs": common_fs,
        "timestamps": t.tolist(),
        "start_time_s": 0.0,
    }

    # 4. Neural windows with alpha (10 Hz) modulation
    neural_windows: list[dict[str, Any]] = []
    n_windows = int(duration_s // window_len_s)
    for i in range(n_windows):
        w_start = i * window_len_s
        w_end = w_start + window_len_s
        w_samples = int(window_len_s * common_fs)
        w_t = np.arange(w_samples) / common_fs + w_start

        alpha_carrier = np.sin(2.0 * np.pi * 10.0 * w_t)
        modulation = 1.0 + 0.3 * np.sin(2.0 * np.pi * 0.3 * w_t)
        eeg_data = (alpha_carrier * modulation + 0.1 * np.random.randn(w_samples)) * 20.0

        neural_windows.append({
            "window_id": f"win_{i:03d}",
            "start_time_s": w_start,
            "end_time_s": w_end,
            "sample_rate_hz": common_fs,
            "n_channels": 1,
            "data": eeg_data.tolist(),
        })

    return neural_windows, physio_stream


def format_markdown_report(report: EmbodiedControlAlignmentReport) -> str:
    """Format EmbodiedControlAlignmentReport into clean, readable Markdown."""
    lines: list[str] = [
        "# Embodied-Control Alignment Report",
        "",
        "> **Scientific Guardrail:** Embodied physiological variables (respiration, cardiac, autonomic)",
        "> are candidate explanatory features, moderators, or covariates. They are **not** proven causal",
        "> mechanisms, and no claim of causal mediation is asserted.",
        "",
        f"- **Schema Version:** `{report.schema_version}`",
        f"- **Timestamp (UTC):** `{report.report_timestamp}`",
        f"- **Evidence Class:** `{report.evidence_class}`",
        f"- **Synthetic Status:** `{report.is_synthetic}`",
        f"- **Alignment Quality Score:** {report.alignment_quality_score:.3f}",
        f"- **Alignment Quality State:** `{report.alignment_quality_state}`",
        f"- **Report Checksum (SHA-256):** `{report.report_checksum_sha256}`",
        f"- **Windows Aligned:** {report.n_windows_aligned}",
        "",
        "## Variable Roles & Feature Units",
        "",
        "| Variable Name | Assigned Role | Physical Units |",
        "| :--- | :--- | :--- |",
    ]
    for var_name, role in sorted(report.variable_roles.items()):
        unit = report.feature_units.get(var_name, "arbitrary")
        lines.append(f"| `{var_name}` | `{role}` | `{unit}` |")

    lines.append("")
    lines.append("## Confound Controls Evaluation")
    lines.append("")
    lines.append("| Control Type | Parameters | Original Coupling | Perturbed Coupling | Attenuation | Surrogate Passed |")
    lines.append("| :--- | :--- | :---: | :---: | :---: | :---: |")
    for cc in report.confound_controls:
        passed_mark = "YES" if cc.surrogate_passed else "NO"
        lines.append(
            f"| `{cc.control_type}` | {cc.parameter_description} | {cc.original_coupling:.3f} | {cc.perturbed_coupling:.3f} | {cc.attenuation_ratio * 100.0:.1f}% | {passed_mark} |"
        )

    lines.append("")
    lines.append(f"## Aligned Windows Summary (First {min(5, len(report.windows))} of {len(report.windows)})")
    lines.append("")
    for w in report.windows[:5]:
        r_str = f"{w.respiration.respiratory_rate_bpm:.1f} BPM" if (w.respiration and w.respiration.respiratory_rate_bpm is not None) else "null"
        if w.cardiac and w.cardiac.heart_rate_bpm is not None:
            rmssd_part = f" (RMSSD={w.cardiac.rmssd_ms:.1f}ms)" if w.cardiac.rmssd_ms is not None else ""
            c_str = f"{w.cardiac.heart_rate_bpm:.1f} BPM{rmssd_part}"
        else:
            c_str = "null"
        lines.append(
            f"- Window `{w.window_id}` `[{w.start_time_s:.1f}s - {w.end_time_s:.1f}s]`: Overlap={w.alignment.overlap_ratio * 100:.0f}%, State=`{w.alignment.signal_quality_state}`, Resp={r_str}, Heart={c_str}"
        )

    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Align EEG neural windows with respiration and autonomic physiology."
    )
    parser.add_argument(
        "--eeg-windows",
        type=Path,
        default=None,
        help="Path to EEG windows JSON file.",
    )
    parser.add_argument(
        "--physio-stream",
        type=Path,
        default=None,
        help="Path to physiology stream JSON file.",
    )
    parser.add_argument(
        "--common-clock-hz",
        type=float,
        default=100.0,
        help="Target common clock frequency in Hz (default: 100.0).",
    )
    parser.add_argument(
        "--interpolation",
        choices=["causal_linear", "nearest"],
        default="causal_linear",
        help="Resampling interpolation mode (default: 'causal_linear').",
    )
    parser.add_argument(
        "--duration-s",
        type=float,
        default=40.0,
        help="Duration in seconds for synthetic generation (default: 40.0).",
    )
    parser.add_argument(
        "--window-duration-s",
        type=float,
        default=8.0,
        help="Window duration in seconds (default: 8.0).",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Run synthetic benchmark alignment (default if no inputs provided).",
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
        help="Write report to output file.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress terminal output.",
    )

    args = parser.parse_args(argv)

    is_synth = args.synthetic
    if args.eeg_windows and args.physio_stream:
        with args.eeg_windows.open("r", encoding="utf-8") as f:
            neural_windows = json.load(f)
        with args.physio_stream.open("r", encoding="utf-8") as f:
            physio_stream = json.load(f)
    else:
        # Default synthetic demo
        is_synth = True
        neural_windows, physio_stream = generate_demo_synthetic_data(
            duration_s=args.duration_s,
            window_len_s=args.window_duration_s,
            common_fs=args.common_clock_hz,
        )

    method = (
        InterpolationMethod.NEAREST
        if args.interpolation == "nearest"
        else InterpolationMethod.CAUSAL_LINEAR
    )

    aligner = EmbodiedControlAligner(
        common_clock_hz=args.common_clock_hz,
        interpolation_method=method,
        is_synthetic=is_synth,
    )

    report = aligner.align(neural_windows, physio_stream)

    if args.format == "markdown":
        output_str = format_markdown_report(report)
    else:
        output_str = report.to_json(indent=2)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_str, encoding="utf-8")

    if not args.quiet:
        print(output_str)

    return 0


if __name__ == "__main__":
    sys.exit(main())
