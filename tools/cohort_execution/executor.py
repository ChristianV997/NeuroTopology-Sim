"""Streaming paired-cohort topology orchestrator and descriptive aggregator."""
from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path
import tempfile
import time
import tracemalloc
from typing import Any

import numpy as np
from scipy import stats

from .manifest_validator import validate_manifest_readiness
from .models import (
    CohortTopologyExecutionSummary,
    ConditionStreamSummary,
    ExecutionStatus,
    PairExecutionSummary,
    WindowMetrics,
    _safe_dict,
)
from .streamer import RecordingStreamer
from .topology import compute_window_topology


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Safely writes a JSON payload using atomic rename and NaN-disallowing serializer."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=path.stem + "_", suffix=".tmp", dir=path.parent)
    os.close(fd)
    try:
        clean_data = _safe_dict(payload)
        Path(temp).write_text(
            json.dumps(clean_data, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temp, path)
    finally:
        if Path(temp).exists():
            try:
                Path(temp).unlink()
            except OSError:
                pass


def _calc_stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "std": None, "min": None, "max": None}
    arr = np.asarray(values, dtype=float)
    finite_arr = arr[np.isfinite(arr)]
    if finite_arr.size == 0:
        return {"mean": None, "std": None, "min": None, "max": None}
    return {
        "mean": float(np.mean(finite_arr)),
        "std": float(np.std(finite_arr, ddof=1)) if len(finite_arr) > 1 else 0.0,
        "min": float(np.min(finite_arr)),
        "max": float(np.max(finite_arr)),
    }


def execute_cohort_topology(
    manifest_path: str | Path,
    output_dir: str | Path,
    *,
    window_samples: int = 1024,
    chunk_size: int = 4096,
    max_windows: int | None = None,
    diagnostic_only: bool = False,
    allow_insufficient: bool = False,
    seed: int = 42,
) -> CohortTopologyExecutionSummary:
    """Executes bounded streaming topology monitoring over a paired-cohort manifest."""
    np.random.seed(seed)
    start_time = time.perf_counter()
    tracemalloc.start()

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    manifest_dict, refusal_reasons, is_executable = validate_manifest_readiness(
        manifest_path,
        diagnostic_only=diagnostic_only,
        allow_insufficient=allow_insufficient,
    )

    manifest_p_str = str(Path(manifest_path).resolve()) if Path(manifest_path).exists() else str(manifest_path)
    manifest_status = manifest_dict.get("status")

    # Diagnostic-only execution or early refusal
    if diagnostic_only or not is_executable:
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        runtime = time.perf_counter() - start_time

        exec_status = (
            ExecutionStatus.REFUSED.value
            if refusal_reasons
            else ExecutionStatus.VALID_COHORT_PROCESSED.value
        )
        summary = CohortTopologyExecutionSummary(
            execution_status=exec_status,
            manifest_path=manifest_p_str,
            manifest_status=manifest_status,
            min_pairs_required=manifest_dict.get("min_pairs", 2),
            total_pairs_in_manifest=len(manifest_dict.get("paired_records", [])),
            pairs_processed=0,
            pairs_skipped=0,
            empirical_pairs_count=0,
            synthetic_pairs_count=0,
            refusal_reasons=refusal_reasons,
            runtime_seconds=runtime,
            peak_memory_mb=peak / (1024 * 1024),
            scientific_note=(
                "Diagnostic-only execution mode. Readiness validated without streaming recording files."
                if diagnostic_only
                else "Normal execution refused due to manifest readiness criteria failure."
            ),
        )
        _atomic_write_json(out_path / "cohort_topology_execution_summary.json", summary.to_dict())
        return summary

    paired_records = manifest_dict.get("paired_records", [])
    processed_pairs: list[dict[str, Any]] = []
    skipped_pairs: list[dict[str, Any]] = []
    all_window_rows: list[dict[str, Any]] = []
    all_pair_rows: list[dict[str, Any]] = []

    empirical_deltas: list[float] = []
    synthetic_deltas: list[float] = []

    empirical_a_areas: list[float] = []
    empirical_b_areas: list[float] = []

    for idx, pair in enumerate(paired_records):
        pair_start = time.perf_counter()
        pairing_key = pair.get("pairing_key", {})
        rec_a = pair.get("condition_a_record", {})
        rec_b = pair.get("condition_b_record", {})

        is_pair_synthetic = bool(
            pair.get("is_synthetic", False)
            or rec_a.get("is_synthetic", False)
            or rec_b.get("is_synthetic", False)
        )

        file_a = rec_a.get("file_path")
        file_b = rec_b.get("file_path")

        if not file_a or not file_b:
            skipped_pairs.append({
                "pair_index": idx,
                "pairing_key": pairing_key,
                "reason": "Missing recording file_path in paired record",
            })
            continue

        try:
            streamer_a = RecordingStreamer(
                file_a,
                format_hint=rec_a.get("format"),
                default_sfreq=rec_a.get("sample_rate") or 1000.0,
                is_synthetic=is_pair_synthetic,
            )
            streamer_b = RecordingStreamer(
                file_b,
                format_hint=rec_b.get("format"),
                default_sfreq=rec_b.get("sample_rate") or 1000.0,
                is_synthetic=is_pair_synthetic,
            )

            meta_a = streamer_a.get_metadata()
            meta_b = streamer_b.get_metadata()

            # Process condition A
            windows_a_metrics: list[WindowMetrics] = []
            for w_idx, chunk, is_fin in streamer_a.iter_windows(
                window_samples=window_samples, max_windows=max_windows
            ):
                metrics = compute_window_topology(chunk, montage_coordinates=meta_a.montage_coordinates)
                windows_a_metrics.append(metrics)
                all_window_rows.append({
                    "pair_index": idx,
                    "condition": "condition_a",
                    "window_index": w_idx,
                    "channels": metrics.channels,
                    "samples": metrics.samples,
                    "beta1_max": metrics.beta1_max,
                    "filtration_beta1_max": metrics.filtration_beta1_max,
                    "mean_beta1": metrics.mean_beta1,
                    "integrated_landscape_area": metrics.integrated_landscape_area,
                    "spatial_charge": metrics.spatial_charge,
                    "spatial_charge_available": metrics.spatial_charge_available,
                    "is_finite": metrics.is_finite,
                })

            # Process condition B
            windows_b_metrics: list[WindowMetrics] = []
            for w_idx, chunk, is_fin in streamer_b.iter_windows(
                window_samples=window_samples, max_windows=max_windows
            ):
                metrics = compute_window_topology(chunk, montage_coordinates=meta_b.montage_coordinates)
                windows_b_metrics.append(metrics)
                all_window_rows.append({
                    "pair_index": idx,
                    "condition": "condition_b",
                    "window_index": w_idx,
                    "channels": metrics.channels,
                    "samples": metrics.samples,
                    "beta1_max": metrics.beta1_max,
                    "filtration_beta1_max": metrics.filtration_beta1_max,
                    "mean_beta1": metrics.mean_beta1,
                    "integrated_landscape_area": metrics.integrated_landscape_area,
                    "spatial_charge": metrics.spatial_charge,
                    "spatial_charge_available": metrics.spatial_charge_available,
                    "is_finite": metrics.is_finite,
                })

            if not windows_a_metrics or not windows_b_metrics:
                skipped_pairs.append({
                    "pair_index": idx,
                    "pairing_key": pairing_key,
                    "reason": f"Insufficient samples for window size {window_samples} in one or both recordings",
                })
                continue

            # Summaries
            a_areas = [m.integrated_landscape_area for m in windows_a_metrics]
            b_areas = [m.integrated_landscape_area for m in windows_b_metrics]
            a_beta1 = [float(m.filtration_beta1_max) for m in windows_a_metrics]
            b_beta1 = [float(m.filtration_beta1_max) for m in windows_b_metrics]
            a_q = [m.spatial_charge for m in windows_a_metrics if m.spatial_charge is not None]
            b_q = [m.spatial_charge for m in windows_b_metrics if m.spatial_charge is not None]

            summary_a = ConditionStreamSummary(
                file_path=meta_a.file_path,
                format=meta_a.format,
                checksum=meta_a.checksum,
                subject=rec_a.get("subject"),
                session=rec_a.get("session"),
                condition=rec_a.get("condition"),
                is_synthetic=is_pair_synthetic,
                provenance=rec_a.get("provenance", {}),
                sample_count=meta_a.sample_count,
                channel_count=meta_a.channel_count,
                sampling_rate_hz=meta_a.sampling_rate_hz,
                windows_processed=len(windows_a_metrics),
                finite_value_status=all(m.is_finite for m in windows_a_metrics),
                beta1_summary=_calc_stats(a_beta1),
                landscape_area_summary=_calc_stats(a_areas),
                spatial_charge_summary={
                    "available": any(m.spatial_charge_available for m in windows_a_metrics),
                    "mean": float(np.mean(a_q)) if a_q else None,
                    "count": len(a_q),
                },
            )

            summary_b = ConditionStreamSummary(
                file_path=meta_b.file_path,
                format=meta_b.format,
                checksum=meta_b.checksum,
                subject=rec_b.get("subject"),
                session=rec_b.get("session"),
                condition=rec_b.get("condition"),
                is_synthetic=is_pair_synthetic,
                provenance=rec_b.get("provenance", {}),
                sample_count=meta_b.sample_count,
                channel_count=meta_b.channel_count,
                sampling_rate_hz=meta_b.sampling_rate_hz,
                windows_processed=len(windows_b_metrics),
                finite_value_status=all(m.is_finite for m in windows_b_metrics),
                beta1_summary=_calc_stats(b_beta1),
                landscape_area_summary=_calc_stats(b_areas),
                spatial_charge_summary={
                    "available": any(m.spatial_charge_available for m in windows_b_metrics),
                    "mean": float(np.mean(b_q)) if b_q else None,
                    "count": len(b_q),
                },
            )

            delta_area = float(np.mean(b_areas) - np.mean(a_areas))
            pair_runtime = time.perf_counter() - pair_start

            pair_summary = PairExecutionSummary(
                pair_index=idx,
                pairing_key=pairing_key,
                is_synthetic=is_pair_synthetic,
                status="processed",
                finite_value_status=(summary_a.finite_value_status and summary_b.finite_value_status),
                condition_a=summary_a,
                condition_b=summary_b,
                delta_landscape_area=delta_area,
                runtime_seconds=pair_runtime,
            )
            processed_pairs.append(pair_summary.to_dict())

            all_pair_rows.append({
                "pair_index": idx,
                "pairing_key": str(pairing_key),
                "is_synthetic": is_pair_synthetic,
                "status": "processed",
                "delta_landscape_area": delta_area,
                "a_mean_landscape_area": float(np.mean(a_areas)),
                "b_mean_landscape_area": float(np.mean(b_areas)),
                "a_mean_beta1": float(np.mean(a_beta1)),
                "b_mean_beta1": float(np.mean(b_beta1)),
                "runtime_seconds": pair_runtime,
            })

            if is_pair_synthetic:
                synthetic_deltas.append(delta_area)
            else:
                empirical_deltas.append(delta_area)
                empirical_a_areas.append(float(np.mean(a_areas)))
                empirical_b_areas.append(float(np.mean(b_areas)))

        except Exception as exc:
            skipped_pairs.append({
                "pair_index": idx,
                "pairing_key": pairing_key,
                "reason": f"Execution error: {exc}",
            })
            all_pair_rows.append({
                "pair_index": idx,
                "pairing_key": str(pairing_key),
                "is_synthetic": is_pair_synthetic,
                "status": "skipped",
                "delta_landscape_area": None,
                "a_mean_landscape_area": None,
                "b_mean_landscape_area": None,
                "a_mean_beta1": None,
                "b_mean_beta1": None,
                "runtime_seconds": time.perf_counter() - pair_start,
            })

    # Descriptive aggregate calculations
    empirical_pairs_count = len(empirical_deltas)
    synthetic_pairs_count = len(synthetic_deltas)

    descriptive_aggregate = {
        "empirical": {
            "pairs_count": empirical_pairs_count,
            "delta_landscape_area": _calc_stats(empirical_deltas),
            "condition_a_landscape_area": _calc_stats(empirical_a_areas),
            "condition_b_landscape_area": _calc_stats(empirical_b_areas),
        },
        "synthetic": {
            "pairs_count": synthetic_pairs_count,
            "delta_landscape_area": _calc_stats(synthetic_deltas),
        },
    }

    # Descriptive non-parametric Wilcoxon test on empirical pairs (if N >= 2)
    descriptive_wilcoxon: dict[str, Any] = {}
    if empirical_pairs_count >= 2:
        diffs = np.asarray(empirical_deltas, dtype=float)
        # Check if all differences are zero
        if np.all(diffs == 0.0):
            descriptive_wilcoxon = {
                "status": "zero_difference",
                "statistic": 0.0,
                "p_value": 1.0,
                "n_pairs": empirical_pairs_count,
                "note": "Descriptive non-parametric test only; does NOT constitute a formal Bayes factor or proof.",
            }
        else:
            try:
                res = stats.wilcoxon(diffs, alternative="two-sided")
                descriptive_wilcoxon = {
                    "status": "computed",
                    "statistic": float(res.statistic) if math.isfinite(res.statistic) else None,
                    "p_value": float(res.pvalue) if math.isfinite(res.pvalue) else None,
                    "n_pairs": empirical_pairs_count,
                    "note": "Descriptive non-parametric test only; does NOT constitute a formal Bayes factor or proof.",
                }
            except Exception as exc:
                descriptive_wilcoxon = {
                    "status": "failed",
                    "error": str(exc),
                    "n_pairs": empirical_pairs_count,
                }
    else:
        descriptive_wilcoxon = {
            "status": "insufficient_empirical_pairs",
            "n_pairs": empirical_pairs_count,
            "note": "Descriptive Wilcoxon signed-rank test requires at least 2 empirical pairs.",
        }

    # Determine execution status
    if empirical_pairs_count >= manifest_dict.get("min_pairs", 2):
        execution_status = ExecutionStatus.VALID_COHORT_PROCESSED.value
    elif empirical_pairs_count > 0:
        execution_status = ExecutionStatus.INSUFFICIENT_PAIRS_PROCESSED.value
    elif synthetic_pairs_count > 0:
        execution_status = ExecutionStatus.SYNTHETIC_EVALUATION.value
    else:
        execution_status = ExecutionStatus.NO_PAIRS_PROCESSED.value

    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    total_runtime = time.perf_counter() - start_time

    cohort_summary = CohortTopologyExecutionSummary(
        execution_status=execution_status,
        manifest_path=manifest_p_str,
        manifest_status=manifest_status,
        condition_a=manifest_dict.get("condition_a", "condition_a"),
        condition_b=manifest_dict.get("condition_b", "condition_b"),
        min_pairs_required=manifest_dict.get("min_pairs", 2),
        total_pairs_in_manifest=len(paired_records),
        pairs_processed=len(processed_pairs),
        pairs_skipped=len(skipped_pairs),
        empirical_pairs_count=empirical_pairs_count,
        synthetic_pairs_count=synthetic_pairs_count,
        refusal_reasons=[],
        processed_pairs=processed_pairs,
        skipped_pairs=skipped_pairs,
        descriptive_aggregate=descriptive_aggregate,
        descriptive_wilcoxon=descriptive_wilcoxon,
        runtime_seconds=total_runtime,
        peak_memory_mb=peak / (1024 * 1024),
        scientific_note=(
            "Descriptive streaming cohort topology summary. Strictly bounded memory execution. "
            "Graph persistent homology (beta_1, landscape area) and geometric spatial charge (Q_spatial) "
            "are computed via separate mathematical pathways. Results represent exploratory descriptive "
            "metrics only and do NOT constitute a formal Bayes factor, clinical inference, hypothesis "
            "confirmation, or theoretical validation."
        ),
    )

    # Write output JSON atomically
    _atomic_write_json(out_path / "cohort_topology_execution_summary.json", cohort_summary.to_dict())

    # Write output CSVs
    if all_pair_rows:
        pair_csv = out_path / "cohort_topology_pairs.csv"
        with pair_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(all_pair_rows[0].keys()))
            writer.writeheader()
            writer.writerows(_safe_dict(all_pair_rows))

    if all_window_rows:
        win_csv = out_path / "cohort_topology_windows.csv"
        with win_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(all_window_rows[0].keys()))
            writer.writeheader()
            writer.writerows(_safe_dict(all_window_rows))

    return cohort_summary
