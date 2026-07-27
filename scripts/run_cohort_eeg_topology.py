"""Cohort-level, bounded streaming EEG topology comparison.

The output is descriptive unless paired recordings permit a valid Wilcoxon
test.  It deliberately does not make a clinical or consciousness inference.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import wilcoxon

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts.run_eeg_topology_analysis import parser as eeg_parser, run_comparative


def _safe(value: Any) -> Any:
    if isinstance(value, (float, np.floating)): return float(value) if np.isfinite(value) else None
    if isinstance(value, np.integer): return int(value)
    if isinstance(value, dict): return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [_safe(v) for v in value]
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.stem, suffix=".tmp"); os.close(fd)
    try:
        Path(temporary).write_text(json.dumps(_safe(value), indent=2, allow_nan=False) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally: Path(temporary).unlink(missing_ok=True)


def _subject_key(path: Path) -> str | None:
    for item in path.stem.split("_"):
        if item.startswith("sub-"): return item
    return None


def _summary(condition: dict[str, Any]) -> dict[str, float | None]:
    return {key: condition.get(key) for key in ("mean_beta1", "mean_landscape_area", "mean_q_spatial")}


def _aggregate(rows: list[dict[str, Any]], metric: str) -> dict[str, float | int | None]:
    values = np.asarray([row[metric] for row in rows if row.get(metric) is not None], dtype=float)
    return {"n": int(values.size), "mean": float(values.mean()) if values.size else None,
            "median": float(np.median(values)) if values.size else None,
            "variance": float(values.var(ddof=1)) if values.size > 1 else None}


def _wilcoxon(rows: list[dict[str, Any]], metric: str) -> dict[str, Any]:
    pairs = [(r["awake"][metric], r["sedated"][metric]) for r in rows
             if r["awake"].get(metric) is not None and r["sedated"].get(metric) is not None]
    if len(pairs) < 2:
        return {"n_pairs": len(pairs), "statistic": None, "p_value": None, "status": "insufficient_paired_subjects"}
    awake, sedated = np.asarray(pairs, float).T
    if np.allclose(awake, sedated): return {"n_pairs": len(pairs), "statistic": 0.0, "p_value": 1.0, "status": "all_paired_differences_zero"}
    test = wilcoxon(awake, sedated, zero_method="wilcox", alternative="two-sided", method="auto")
    return {"n_pairs": len(pairs), "statistic": float(test.statistic), "p_value": float(test.pvalue), "status": "computed"}


def run(args: argparse.Namespace) -> dict[str, Any]:
    """Process only subjects having both local awake and sedated BrainVision headers."""
    data_dir, out = Path(args.data_dir), Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    awake = {_subject_key(p): p for p in data_dir.rglob("*task-awake*.vhdr") if _subject_key(p)}
    sedated = {_subject_key(p): p for p in data_dir.rglob("*task-sed2*.vhdr") if _subject_key(p)}
    subjects = sorted(set(awake) & set(sedated)); rows: list[dict[str, Any]] = []
    template = eeg_parser().parse_args([])
    for subject in subjects:
        run_args = argparse.Namespace(**vars(template)); run_args.awake_file = awake[subject]; run_args.sedated_file = sedated[subject]
        run_args.output_dir = out / "subjects" / subject; run_args.chunk_samples = args.chunk_samples; run_args.max_windows = args.max_windows
        result = run_comparative(run_args)
        rows.append({"subject": subject, "awake": _summary(result["awake"]), "sedated": _summary(result["sedated"]),
                     "persistence_distance_proxy": result["persistence_distance_proxy"]})
    flat = [{"subject": row["subject"], "condition": condition, **row[condition]}
            for row in rows for condition in ("awake", "sedated")]
    aggregation = {condition: {metric: _aggregate([r[condition] for r in rows], metric)
                                for metric in ("mean_beta1", "mean_landscape_area", "mean_q_spatial")}
                   for condition in ("awake", "sedated")}
    tests = {metric: _wilcoxon(rows, metric) for metric in ("mean_beta1", "mean_landscape_area", "mean_q_spatial")}
    power_status = "powered" if len(rows) >= args.min_paired_subjects else "insufficient_paired_subjects"
    payload = {"schema": "NeuroTopologySim.CohortSedationTopology.v1", "source": "local_empirical_eeg",
               "discovered_subjects": len(subjects), "paired_subjects": [r["subject"] for r in rows], "per_subject": rows,
               "aggregate": aggregation, "wilcoxon_signed_rank": tests, "power_status": power_status,
               "scientific_note": "A cohort result is descriptive when local paired subject count is inadequate. beta1 is graph persistence, whereas Q_spatial uses montage geometry."}
    _write_json(out / "cohort_topology_summary.json", payload)
    fields = ["subject", "condition", "mean_beta1", "mean_landscape_area", "mean_q_spatial"]
    with (out / "cohort_topology_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(_safe(flat))
    figure, axis = plt.subplots(figsize=(7, 4)); labels = ["awake", "sedated"]
    values = [aggregation[label]["mean_landscape_area"]["mean"] for label in labels]
    axis.bar(labels, [v if v is not None else 0 for v in values]); axis.set(ylabel="Mean persistence landscape area", title="Cohort topology summary")
    figure.tight_layout(); figure.savefig(out / "cohort_topology_summary.png", dpi=200); plt.close(figure)
    return payload


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", type=Path, default=ROOT / "data" / "ds005620")
    p.add_argument("--output-dir", type=Path, default=ROOT / "artifacts" / "topology_monitoring" / "cohort_sedation")
    p.add_argument("--chunk-samples", type=int, default=500); p.add_argument("--max-windows", type=int, default=12)
    p.add_argument("--min-paired-subjects", type=int, default=16, help="Report power only at this local paired-subject count; does not alter inferential tests.")
    return p


if __name__ == "__main__": print(json.dumps({"schema": run(parser().parse_args())["schema"]}))
