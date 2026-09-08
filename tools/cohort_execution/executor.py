"""Streaming paired-cohort topology orchestrator and descriptive aggregator."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time
import tracemalloc
from typing import Any, Sequence

import numpy as np

from .manifest_validator import validate_manifest_readiness
from .models import (
    CohortTopologyExecutionSummary,
    ConditionStreamSummary,
    ExecutionStatus,
    PairExecutionSummary,
    WindowMetrics,
    _safe_dict,
)
from .streamer import RecordingStreamer, compute_file_sha256
from .topology import compute_window_topology


def _strip_transient_telemetry(val: Any) -> Any:
    """Recursively removes non-deterministic telemetry (dynamic runtimes and memory) for stable hashing."""
    if isinstance(val, dict):
        return {
            k: _strip_transient_telemetry(v)
            for k, v in val.items()
            if k not in ("runtime_seconds", "peak_memory_mb", "memory_telemetry", "output_checksum")
        }
    if isinstance(val, (list, tuple)):
        return [_strip_transient_telemetry(x) for x in val]
    return val


def _canonicalize_and_checksum(payload: dict[str, Any]) -> tuple[str, str]:
    """Serializes canonical JSON without NaN and returns (json_string, sha256_checksum)."""
    clean_copy = dict(payload)
    clean_copy["output_checksum"] = ""
    safe_data = _safe_dict(clean_copy)
    hash_data = _strip_transient_telemetry(safe_data)
    canonical_str = json.dumps(hash_data, indent=2, sort_keys=True, allow_nan=False)
    checksum = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
    clean_copy["output_checksum"] = checksum
    final_str = json.dumps(_safe_dict(clean_copy), indent=2, sort_keys=True, allow_nan=False) + "\n"
    return final_str, checksum


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> str:
    """Safely writes a canonical JSON payload using atomic replace. Returns checksum."""
    path.parent.mkdir(parents=True, exist_ok=True)
    final_json, checksum = _canonicalize_and_checksum(payload)
    fd, temp = tempfile.mkstemp(prefix=path.stem + "_", suffix=".tmp", dir=path.parent)
    os.close(fd)
    try:
        Path(temp).write_text(final_json, encoding="utf-8")
        os.replace(temp, path)
    finally:
        if Path(temp).exists():
            try:
                Path(temp).unlink()
            except OSError:
                pass
    return checksum


def _calc_stats(values: Sequence[float]) -> dict[str, float | None]:
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
    window_duration_s: float | None = None,
    window_samples: int = 1024,
    step_duration_s: float | None = None,
    step_samples: int | None = None,
    channel_limit: int | None = None,
    sample_limit: int | None = None,
    filtration_thresholds: Sequence[float] | None = None,
    max_points_per_window: int | None = None,
    max_windows: int | None = None,
    memory_telemetry: bool = True,
    diagnostic_only: bool = False,
    allow_insufficient: bool = False,
    seed: int = 42,
) -> CohortTopologyExecutionSummary:
    """Executes bounded streaming topology monitoring over a paired-cohort manifest."""
    np.random.seed(seed)
    start_time = time.perf_counter()
    if memory_telemetry:
        tracemalloc.start()

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Compute provenance checksum over manifest file
    prov_checksum = compute_file_sha256(manifest_path)

    # Check optional dependency: ripser
    try:
        import ripser
    except ImportError:
        if memory_telemetry:
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        else:
            peak = 0
        runtime = time.perf_counter() - start_time
        summary = CohortTopologyExecutionSummary(
            execution_status=ExecutionStatus.MISSING_OPTIONAL_DEPENDENCY.value,
            formal_bayes_factor=None,
            scientific_pass=False,
            evidence_class="descriptive_topology_only",
            manifest_path=str(manifest_path),
            provenance_checksum=prov_checksum,
            refusal_reasons=["Optional dependency 'ripser' is not installed or importable."],
            runtime_seconds=runtime,
            peak_memory_mb=peak / (1024 * 1024) if memory_telemetry else None,
            memory_telemetry={"peak_mb": peak / (1024 * 1024)} if memory_telemetry else {},
            scientific_note="Execution halted: missing optional topological dependency.",
        )
        checksum = _atomic_write_json(out_path / "cohort_topology_execution_summary.json", summary.to_dict())
        summary.output_checksum = checksum
        return summary

    manifest_dict, refusal_reasons, suggested_status, is_executable = validate_manifest_readiness(
        manifest_path,
        diagnostic_only=diagnostic_only,
        allow_insufficient=allow_insufficient,
    )

    manifest_p_str = str(Path(manifest_path).resolve()) if Path(manifest_path).exists() else str(manifest_path)
    manifest_status = manifest_dict.get("status")

    # Diagnostic-only execution or early refusal
    if diagnostic_only or not is_executable:
        if memory_telemetry:
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        else:
            peak = 0
        runtime = time.perf_counter() - start_time

        exec_status = suggested_status if refusal_reasons else ExecutionStatus.DESCRIPTIVE_READY.value
        summary = CohortTopologyExecutionSummary(
            execution_status=exec_status,
            formal_bayes_factor=None,
            scientific_pass=False,
            evidence_class="descriptive_topology_only",
            manifest_path=manifest_p_str,
            manifest_status=manifest_status,
            provenance_checksum=prov_checksum,
            min_pairs_required=manifest_dict.get("min_pairs", 2),
            total_pairs_in_manifest=len(manifest_dict.get("paired_records", [])),
            pairs_processed=0,
            pairs_skipped=0,
            empirical_pairs_count=0,
            synthetic_pairs_count=0,
            refusal_reasons=refusal_reasons,
            runtime_seconds=runtime,
            peak_memory_mb=peak / (1024 * 1024) if memory_telemetry else None,
            memory_telemetry={"peak_mb": peak / (1024 * 1024)} if memory_telemetry else {},
            scientific_note=(
                "Diagnostic-only execution mode. Readiness validated without streaming recording files."
                if diagnostic_only
                else "Normal execution refused due to manifest readiness criteria failure."
            ),
        )
        checksum = _atomic_write_json(out_path / "cohort_topology_execution_summary.json", summary.to_dict())
        summary.output_checksum = checksum
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
                window_duration_s=window_duration_s,
                window_samples=window_samples,
                step_duration_s=step_duration_s,
                step_samples=step_samples,
                channel_limit=channel_limit,
                sample_limit=sample_limit,
                max_points_per_window=max_points_per_window,
                max_windows=max_windows,
            ):
                metrics = compute_window_topology(
                    chunk,
                    montage_coordinates=meta_a.montage_coordinates,
                    filtration_thresholds=filtration_thresholds,
                )
                windows_a_metrics.append(metrics)
                all_window_rows.append({
                    "pair_index": idx,
                    "condition": "condition_a",
                    "window_index": w_idx,
                    "channels": metrics.channels,
                    "samples": metrics.samples,
                    "h0_intervals_count": metrics.h0_intervals_count,
                    "h1_intervals_count": metrics.h1_intervals_count,
                    "beta0_max": metrics.beta0_max,
                    "beta0_mean": metrics.beta0_mean,
                    "beta1_max": metrics.beta1_max,
                    "filtration_beta1_max": metrics.filtration_beta1_max,
                    "mean_beta1": metrics.mean_beta1,
                    "integrated_beta1_landscape_area": metrics.integrated_beta1_landscape_area,
                    "spatial_phase_charge": metrics.spatial_phase_charge,
                    "spatial_charge_available": metrics.spatial_charge_available,
                    "is_finite": metrics.is_finite,
                })

            # Process condition B
            windows_b_metrics: list[WindowMetrics] = []
            for w_idx, chunk, is_fin in streamer_b.iter_windows(
                window_duration_s=window_duration_s,
                window_samples=window_samples,
                step_duration_s=step_duration_s,
                step_samples=step_samples,
                channel_limit=channel_limit,
                sample_limit=sample_limit,
                max_points_per_window=max_points_per_window,
                max_windows=max_windows,
            ):
                metrics = compute_window_topology(
                    chunk,
                    montage_coordinates=meta_b.montage_coordinates,
                    filtration_thresholds=filtration_thresholds,
                )
                windows_b_metrics.append(metrics)
                all_window_rows.append({
                    "pair_index": idx,
                    "condition": "condition_b",
                    "window_index": w_idx,
                    "channels": metrics.channels,
                    "samples": metrics.samples,
                    "h0_intervals_count": metrics.h0_intervals_count,
                    "h1_intervals_count": metrics.h1_intervals_count,
                    "beta0_max": metrics.beta0_max,
                    "beta0_mean": metrics.beta0_mean,
                    "beta1_max": metrics.beta1_max,
                    "filtration_beta1_max": metrics.filtration_beta1_max,
                    "mean_beta1": metrics.mean_beta1,
                    "integrated_beta1_landscape_area": metrics.integrated_beta1_landscape_area,
                    "spatial_phase_charge": metrics.spatial_phase_charge,
                    "spatial_charge_available": metrics.spatial_charge_available,
                    "is_finite": metrics.is_finite,
                })

            if not windows_a_metrics or not windows_b_metrics:
                skipped_pairs.append({
                    "pair_index": idx,
                    "pairing_key": pairing_key,
                    "reason": f"Insufficient samples for window size in one or both recordings",
                })
                continue

            # Summaries
            a_areas = [m.integrated_beta1_landscape_area for m in windows_a_metrics]
            b_areas = [m.integrated_beta1_landscape_area for m in windows_b_metrics]
            a_beta0 = [float(m.beta0_mean) for m in windows_a_metrics]
            b_beta0 = [float(m.beta0_mean) for m in windows_b_metrics]
            a_beta1 = [float(m.filtration_beta1_max) for m in windows_a_metrics]
            b_beta1 = [float(m.filtration_beta1_max) for m in windows_b_metrics]
            a_q = [m.spatial_phase_charge for m in windows_a_metrics if m.spatial_phase_charge is not None]
            b_q = [m.spatial_phase_charge for m in windows_b_metrics if m.spatial_phase_charge is not None]

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
                beta0_summary=_calc_stats(a_beta0),
                beta1_summary=_calc_stats(a_beta1),
                integrated_beta1_landscape_area_summary=_calc_stats(a_areas),
                persistence_interval_counts={
                    "h0": sum(m.h0_intervals_count for m in windows_a_metrics),
                    "h1": sum(m.h1_intervals_count for m in windows_a_metrics),
                },
                spatial_phase_charge_summary={
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
                beta0_summary=_calc_stats(b_beta0),
                beta1_summary=_calc_stats(b_beta1),
                integrated_beta1_landscape_area_summary=_calc_stats(b_areas),
                persistence_interval_counts={
                    "h0": sum(m.h0_intervals_count for m in windows_b_metrics),
                    "h1": sum(m.h1_intervals_count for m in windows_b_metrics),
                },
                spatial_phase_charge_summary={
                    "available": any(m.spatial_charge_available for m in windows_b_metrics),
                    "mean": float(np.mean(b_q)) if b_q else None,
                    "count": len(b_q),
                },
            )

            mean_a_area = float(np.mean(a_areas)) if a_areas else 0.0
            mean_b_area = float(np.mean(b_areas)) if b_areas else 0.0
            delta_area = float(mean_b_area - mean_a_area)
            persistence_distance = float(abs(delta_area))
            pair_runtime = time.perf_counter() - pair_start

            pair_summary = PairExecutionSummary(
                pair_index=idx,
                pairing_key=pairing_key,
                is_synthetic=is_pair_synthetic,
                status="processed",
                finite_value_status=(summary_a.finite_value_status and summary_b.finite_value_status),
                condition_a=summary_a,
                condition_b=summary_b,
                persistence_distance=persistence_distance,
                delta_landscape_area=delta_area,
                runtime_seconds=pair_runtime,
            )
            processed_pairs.append(pair_summary.to_dict())

            all_pair_rows.append({
                "pair_index": idx,
                "pairing_key": str(pairing_key),
                "is_synthetic": is_pair_synthetic,
                "status": "processed",
                "persistence_distance": persistence_distance,
                "delta_landscape_area": delta_area,
                "a_mean_landscape_area": mean_a_area,
                "b_mean_landscape_area": mean_b_area,
                "a_mean_beta1": float(np.mean(a_beta1)) if a_beta1 else None,
                "b_mean_beta1": float(np.mean(b_beta1)) if b_beta1 else None,
                "runtime_seconds": pair_runtime,
            })

            if is_pair_synthetic:
                synthetic_deltas.append(delta_area)
            else:
                empirical_deltas.append(delta_area)
                empirical_a_areas.append(mean_a_area)
                empirical_b_areas.append(mean_b_area)

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
                "persistence_distance": None,
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
            "persistence_distance": _calc_stats([abs(d) for d in empirical_deltas]),
            "condition_a_landscape_area": _calc_stats(empirical_a_areas),
            "condition_b_landscape_area": _calc_stats(empirical_b_areas),
        },
        "synthetic": {
            "pairs_count": synthetic_pairs_count,
            "delta_landscape_area": _calc_stats(synthetic_deltas),
            "persistence_distance": _calc_stats([abs(d) for d in synthetic_deltas]),
        },
    }

    # Determine execution status
    if empirical_pairs_count >= manifest_dict.get("min_pairs", 2):
        execution_status = ExecutionStatus.DESCRIPTIVE_READY.value
    elif empirical_pairs_count > 0:
        execution_status = ExecutionStatus.INSUFFICIENT_PAIRED_SUBJECTS.value
    elif synthetic_pairs_count > 0:
        execution_status = ExecutionStatus.SYNTHETIC_DEMO_ONLY.value
    else:
        execution_status = ExecutionStatus.NO_DATA.value

    if memory_telemetry:
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_mb = peak / (1024 * 1024)
        mem_data = {"peak_mb": peak_mb}
    else:
        peak_mb = None
        mem_data = {}

    total_runtime = time.perf_counter() - start_time

    cohort_summary = CohortTopologyExecutionSummary(
        execution_status=execution_status,
        formal_bayes_factor=None,
        scientific_pass=False,
        evidence_class="descriptive_topology_only",
        manifest_path=manifest_p_str,
        manifest_status=manifest_status,
        provenance_checksum=prov_checksum,
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
        runtime_seconds=total_runtime,
        peak_memory_mb=peak_mb,
        memory_telemetry=mem_data,
        scientific_note=(
            "Descriptive streaming cohort topology summary. Strictly bounded memory execution. "
            "Graph persistent homology (beta_0, beta_1, landscape area) and geometric spatial charge "
            "(Q_spatial) are computed via separate mathematical pathways. Results represent exploratory "
            "descriptive metrics only and do NOT constitute a formal Bayes factor, clinical inference, "
            "hypothesis confirmation, or theoretical validation."
        ),
    )

    # Write output JSON atomically and get SHA-256 checksum
    checksum = _atomic_write_json(out_path / "cohort_topology_execution_summary.json", cohort_summary.to_dict())
    cohort_summary.output_checksum = checksum

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
