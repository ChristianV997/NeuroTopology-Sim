"""
Export the ds005620 PITNN cohort's real per-subject AND grand-average topology data
for the /vortex-field 3D viewer.

Reads outputs/pitnn_cohort/ds005620/subjects/*.json (produced by
`tools/stream_pitnn_cohort_ds005620.py --export-spatial --export-persistence`) and
writes a compact JSON payload for embedding directly in
apps/awareness_studio/src/awareness_studio/web/static/vortex_field.html.

Real, unmodified per subject: electrode (x, y), triangle indices, per-triangle
winding number, per-channel phase, H1 birth/death pairs (last analysis window),
bottleneck distance, and per-window (all 3 real 10s windows) mean PLV / landscape
area / beta1 / max-filtration beta1.

Real aggregates computed here, not fabricated:
  - grand-average per-triangle winding: arithmetic mean of each triangle's real
    winding (-1/0/+1) across all 20 subjects
  - grand-average per-channel phase: real circular mean, with the resultant vector
    length (0..1) as a genuine cross-subject phase-agreement measure
  - pooled H1: every real (birth, death) pair from all 20 subjects' last-window
    diagrams, concatenated (not averaged)
  - per-window cohort-mean trajectories: the same real per-window scalars,
    averaged across subjects at each of the 3 real window indices

Before aggregating, this script verifies electrode coordinates and the Delaunay
triangulation are byte-identical across every subject and both conditions (all
subjects use the same standard_1020 template positions) -- if that ever stops
being true for a re-run of the streaming tool, this script raises rather than
silently cross-subject-averaging misaligned electrodes.

Usage:
  python tools/export_cohort_vortex_field_data.py \\
      --cohort-dir outputs/pitnn_cohort/ds005620 --out /tmp/cohort_defects.json
"""
from __future__ import annotations

import argparse
import glob
import json
import math
from pathlib import Path
from typing import Any


def _round(x: float, n: int = 5) -> float:
    return round(x, n)


def _load_subjects(cohort_dir: Path) -> list[dict[str, Any]]:
    files = sorted(glob.glob(str(cohort_dir / "subjects" / "sub-*.json")))
    if not files:
        raise FileNotFoundError(f"No subject files under {cohort_dir / 'subjects'}")
    return [json.loads(Path(f).read_text()) for f in files]


def _verify_shared_geometry(subjects_raw: list[dict[str, Any]]) -> tuple[list, list]:
    ref_coords = subjects_raw[0]["spatial"]["awake"]["channel_coordinates"]
    ref_tri = subjects_raw[0]["spatial"]["awake"]["defects"]["triangle_indices"]
    for s in subjects_raw:
        for cond in ("awake", "sedated"):
            if s["spatial"][cond]["channel_coordinates"] != ref_coords:
                raise ValueError(
                    f"{s['subject']} {cond}: channel_coordinates differ from the "
                    "reference subject -- cohort averaging requires identical "
                    "electrode positions across subjects; do not silently average."
                )
            if s["spatial"][cond]["defects"]["triangle_indices"] != ref_tri:
                raise ValueError(
                    f"{s['subject']} {cond}: triangulation differs from the "
                    "reference subject -- cohort averaging requires an identical "
                    "triangulation across subjects; do not silently average."
                )
    return ref_coords, ref_tri


def _per_window_scalars(window: dict[str, Any]) -> dict[str, Any]:
    return {
        "window": window["window"],
        "start_s": window["start_s"],
        "mean_plv": _round(window["mean_plv"]),
        "landscape_area": _round(window["integrated_landscape_area"], 8),
        "beta1": window["beta1"],
        "filtration_beta1_max": window["filtration_beta1_max"],
    }


def build_payload(cohort_dir: Path) -> dict[str, Any]:
    subjects_raw = _load_subjects(cohort_dir)
    ref_coords, ref_tri = _verify_shared_geometry(subjects_raw)
    n_ch, n_tri, n_subj = len(ref_coords), len(ref_tri), len(subjects_raw)

    subjects_out = []
    wind_sum = {c: [0.0] * n_tri for c in ("awake", "sedated")}
    wind_abs_sum = {c: [0.0] * n_tri for c in ("awake", "sedated")}
    phase_cos_sum = {c: [0.0] * n_ch for c in ("awake", "sedated")}
    phase_sin_sum = {c: [0.0] * n_ch for c in ("awake", "sedated")}
    h1_pool: dict[str, list] = {c: [] for c in ("awake", "sedated")}
    window_sum = {
        c: [
            {"mean_plv": 0.0, "integrated_landscape_area": 0.0, "beta1": 0.0, "filtration_beta1_max": 0.0, "start_s": 0.0}
            for _ in range(3)
        ]
        for c in ("awake", "sedated")
    }

    for s in subjects_raw:
        conds_out = {}
        for cond in ("awake", "sedated"):
            sp = s["spatial"][cond]
            defects = sp["defects"]
            wind = [int(round(w)) if abs(w) > 0.5 else 0 for w in defects["signed_winding"]]
            phase = sp["phase"]
            qabs = sum(abs(w) for w in defects["signed_winding"])

            last_window = s["topology_windows"][cond][-1]
            h1_raw = last_window["cubical_persistence"]["diagrams"]["1"]
            h1_finite = [[_round(b), _round(d)] for b, d in h1_raw if d is not None and math.isfinite(d)]

            per_window = []
            for w in s["topology_windows"][cond]:
                pw = _per_window_scalars(w)
                per_window.append(pw)
                acc = window_sum[cond][w["window"]]
                acc["mean_plv"] += w["mean_plv"]
                acc["integrated_landscape_area"] += w["integrated_landscape_area"]
                acc["beta1"] += w["beta1"]
                acc["filtration_beta1_max"] += w["filtration_beta1_max"]
                acc["start_s"] = w["start_s"]

            conds_out[cond] = {
                "phase": [_round(p, 4) for p in phase],
                "wind": wind,
                "qabs": _round(qabs, 4),
                "h1": h1_finite,
                "per_window": per_window,
            }

            for i, w in enumerate(wind):
                wind_sum[cond][i] += w
                wind_abs_sum[cond][i] += abs(w)
            for i, p in enumerate(phase):
                phase_cos_sum[cond][i] += math.cos(p)
                phase_sin_sum[cond][i] += math.sin(p)
            h1_pool[cond].extend(h1_finite)

        subjects_out.append(
            {
                "id": s["subject"],
                "bottleneck": s["cubical_h1_bottleneck_distance_last_window"],
                "n_channels": s["n_channels"],
                "conditions": conds_out,
            }
        )

    cohort_average = {}
    for cond in ("awake", "sedated"):
        wind_mean = [_round(v / n_subj) for v in wind_sum[cond]]
        wind_abs_mean = [_round(v / n_subj) for v in wind_abs_sum[cond]]
        phase_mean, coherence = [], []
        for i in range(n_ch):
            cx, sx = phase_cos_sum[cond][i] / n_subj, phase_sin_sum[cond][i] / n_subj
            phase_mean.append(_round(math.atan2(sx, cx), 4))
            coherence.append(_round(math.hypot(cx, sx), 4))
        per_window_avg = []
        for i in range(3):
            acc = window_sum[cond][i]
            per_window_avg.append(
                {
                    "window": i,
                    "start_s": acc["start_s"],
                    "mean_plv": _round(acc["mean_plv"] / n_subj),
                    "landscape_area": _round(acc["integrated_landscape_area"] / n_subj, 8),
                    "beta1": _round(acc["beta1"] / n_subj, 3),
                    "filtration_beta1_max": _round(acc["filtration_beta1_max"] / n_subj, 3),
                }
            )
        cohort_average[cond] = {
            "wind_mean": wind_mean,
            "wind_abs_mean": wind_abs_mean,
            "phase_mean": phase_mean,
            "coherence": coherence,
            "qabs_grand_mean_map": _round(sum(abs(v) for v in wind_mean), 4),
            "h1_pooled": h1_pool[cond],
            "per_window": per_window_avg,
        }

    return {
        "coords": [[_round(c[0]), _round(c[1])] for c in ref_coords],
        "tri": ref_tri,
        "n_channels": n_ch,
        "n_subjects": n_subj,
        "cohort_average": cohort_average,
        "subjects": subjects_out,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort-dir", default="outputs/pitnn_cohort/ds005620")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    payload = build_payload(Path(args.cohort_dir))
    out_path = Path(args.out)
    out_path.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
