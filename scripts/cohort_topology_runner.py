#!/usr/bin/env python3
"""Local streaming paired-cohort topology execution runner for NeuroTopology-Sim.

Consumes a validated PairedCohortManifest, streams electrophysiology recordings
pair-by-pair without loading the entire cohort into memory, computes descriptive
graph persistence (beta-1) and spatial phase topology metrics while strictly
keeping them separate, preserves subject-level provenance and checksums, and enforces
repository guardrails (no Bayes factor claims, no PASS on synthetic inputs, no clinical claims).
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Iterator, Sequence

import numpy as np
from scipy.signal import hilbert
from scipy.stats import wilcoxon

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.data_loaders.cohort_manifest import (
    CohortManifest,
    CohortStatus,
    PairedSubjectRecord,
    RecordingRecord,
)
from topo_monitor.graph_persistence import analyze_adjacency
from topo_monitor.spatial_phase import sensor_spatial_charge, spatial_winding_charge

BANNED_PHRASES = (
    "proves consciousness", "consciousness proven", "soul proven", "afterlife proven",
    "liberation detected", "ontology solved", "ultimate reality", "q equals self",
    "q equals soul", "q_abs equals suffering", "f_dress equals karma",
    "sedated implies no_experience", "unresponsive implies unconscious",
    "topology proves liberation", "eeg proves consciousness", "bayes factor confirms",
    "consciousness solved", "toe validated", "final theory validated",
)

SAFE_SCIENTIFIC_NOTE = (
    "Descriptive cohort topology metrics only. Graph beta-1 (cycle persistence) and "
    "spatial phase charge (sensor winding) are mathematically distinct and never conflated. "
    "Synthetic inputs are never empirical evidence. No formal Bayes factor, clinical inference, "
    "or consciousness claims are made or implied."
)


def validate_safe_text(text: str) -> None:
    """Rejects prohibited claims per repository guardrails."""
    lower = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lower:
            raise ValueError(f"Banned claim phrase detected: '{phrase}'")


def safe_finite_value(val: Any) -> Any:
    """Recursively converts non-finite floats to None for strict JSON compliance (allow_nan=False)."""
    if isinstance(val, (float, np.floating)):
        return float(val) if math.isfinite(float(val)) else None
    if isinstance(val, (int, np.integer)):
        return int(val)
    if isinstance(val, (str, bool)) or val is None:
        return val
    if isinstance(val, dict):
        return {str(k): safe_finite_value(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [safe_finite_value(v) for v in val]
    return str(val)


def write_null_safe_json(path: Path, payload: dict[str, Any]) -> None:
    """Writes JSON atomically with allow_nan=False ensuring strict null-safe output."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = safe_finite_value(payload)
    text = json.dumps(cleaned, indent=2, sort_keys=True, allow_nan=False) + "\n"
    validate_safe_text(text)
    
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.stem + "_", suffix=".tmp")
    os.close(fd)
    try:
        Path(tmp).write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def load_and_validate_manifest(
    manifest_path: str | Path,
    *,
    diagnostic_only: bool = False,
    allow_insufficient: bool = False,
) -> tuple[dict[str, Any], list[str], bool]:
    """Loads and validates a PairedCohortManifest.
    
    Returns (manifest_dict, refusal_reasons, is_executable).
    """
    p = Path(manifest_path)
    if not p.is_file():
        return {}, [f"Manifest file not found: {p}"], False

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {}, [f"Malformed JSON in manifest: {e}"], False

    if not isinstance(data, dict):
        return {}, ["Manifest root must be a JSON object"], False

    refusal_reasons = []
    status = data.get("status")
    status_reason = data.get("status_reason", "")
    ambiguous = data.get("ambiguous_matches", [])

    if status == CohortStatus.NO_DATA.value:
        refusal_reasons.append(f"Manifest status is 'no_data': {status_reason}")
    elif status == CohortStatus.MALFORMED_COHORT.value:
        refusal_reasons.append(f"Manifest status is 'malformed_cohort': {status_reason}")
    elif status == CohortStatus.INSUFFICIENT_PAIRS.value and not allow_insufficient:
        refusal_reasons.append(f"Manifest status is 'insufficient_pairs': {status_reason}")

    if ambiguous:
        refusal_reasons.append(
            f"Manifest reports {len(ambiguous)} ambiguous matches with unresolvable condition labels"
        )

    is_executable = (len(refusal_reasons) == 0) or diagnostic_only
    return data, refusal_reasons, is_executable


def stream_file_chunks(
    file_path: str | Path,
    chunk_samples: int = 500,
    max_windows: int = 12,
    default_sfreq: float = 250.0,
) -> tuple[Iterator[np.ndarray], float, np.ndarray | None]:
    """Streams 2D chunks of shape (channels, samples) bounded without loading whole dataset.
    
    Returns (chunk_iterator, sample_rate_hz, montage_coordinates).
    """
    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"Recording file not found on disk: {p}")

    suffix = p.suffix.lower()

    if suffix == ".npy":
        # Memory-mapped array reader (bounded memory)
        mmap_arr = np.load(p, mmap_mode="r")
        if mmap_arr.ndim != 2:
            raise ValueError(f"NumPy array must be 2D (channels, samples), got shape {mmap_arr.shape}")
        channels, n_times = mmap_arr.shape

        def npy_chunks() -> Iterator[np.ndarray]:
            for w in range(max_windows):
                start = w * chunk_samples
                if start >= n_times:
                    break
                stop = min(n_times, start + chunk_samples)
                chunk = np.asarray(mmap_arr[:, start:stop], dtype=float)
                yield chunk

        # Spatial coordinates for square grids
        coords = None
        side = int(math.isqrt(channels))
        if side * side == channels and side >= 2:
            coords = np.stack(np.mgrid[:side, :side], axis=-1).astype(float)

        return npy_chunks(), default_sfreq, coords

    elif suffix == ".csv":
        # Stream CSV rows
        with p.open("r", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader, None)
            if not headers:
                raise ValueError(f"Empty CSV file: {p}")
            
            # Identify time column if present
            time_idx = None
            col_indices = []
            for i, h in enumerate(headers):
                if h.strip().lower() in ("time", "time_s", "timestamp"):
                    time_idx = i
                else:
                    col_indices.append(i)

            if not col_indices:
                raise ValueError(f"No signal channels found in CSV headers: {headers}")

            all_rows = []
            for row in reader:
                if not row or all(not cell.strip() for cell in row):
                    continue
                vals = [float(row[i]) for i in col_indices]
                all_rows.append(vals)

            if not all_rows:
                raise ValueError(f"CSV contains no data rows: {p}")

            data_arr = np.asarray(all_rows, dtype=float).T  # Shape: (channels, samples)
            channels, n_times = data_arr.shape

        def csv_chunks() -> Iterator[np.ndarray]:
            for w in range(max_windows):
                start = w * chunk_samples
                if start >= n_times:
                    break
                stop = min(n_times, start + chunk_samples)
                yield data_arr[:, start:stop]

        return csv_chunks(), default_sfreq, None

    elif suffix in (".vhdr", ".edf", ".bdf", ".fif"):
        # Use existing signal loaders or MNE if installed
        try:
            from shared.data_loaders.eeg_bids_loader import read_local_raw
            stream = read_local_raw(p, preload=False)
            
            def raw_chunks() -> Iterator[np.ndarray]:
                for idx, chunk in enumerate(stream.iter_chunks(chunk_samples)):
                    if idx >= max_windows:
                        break
                    yield chunk

            return raw_chunks(), stream.metadata.sfreq_hz, stream.metadata.montage_coordinates
        except Exception as exc:
            raise RuntimeError(f"Failed to stream electrophysiology format {suffix}: {exc}") from exc

    else:
        raise ValueError(f"Unsupported recording format: {suffix}")


def compute_window_topology(
    chunk: np.ndarray,
    sfreq: float,
    montage_coordinates: np.ndarray | None = None,
    plv_threshold: float = 0.5,
    landscape_layers: int = 5,
) -> dict[str, Any]:
    """Computes descriptive topology metrics on a single bounded signal chunk."""
    channels, samples = chunk.shape
    if channels < 2 or samples < 8:
        return {
            "channels": channels,
            "samples": samples,
            "is_finite": bool(np.all(np.isfinite(chunk))),
            "beta1_max": 0,
            "filtration_beta1_max": 0,
            "mean_beta1": 0.0,
            "integrated_landscape_area": 0.0,
            "spatial_charge": None,
            "spatial_charge_available": False,
        }

    is_finite = bool(np.all(np.isfinite(chunk)))
    if not is_finite:
        raise ValueError("Chunk contains non-finite values (NaN or Inf)")

    # Hilbert analytic signal and phase
    analytic = hilbert(chunk, axis=1)
    phase = np.angle(analytic)

    # Phase-locking value (PLV) adjacency
    diff = phase[:, None, :] - phase[None, :, :]
    plv = np.abs(np.mean(np.exp(1j * diff), axis=2))
    np.fill_diagonal(plv, 0.0)

    # Graph persistent homology via filtration sweep
    pers_res = analyze_adjacency(plv, threshold=plv_threshold, n_layers=landscape_layers)
    
    sweep_b = pers_res.sweep_beta1
    sweep_max = int(np.max(sweep_b)) if sweep_b is not None and sweep_b.size > 0 else 0
    mean_beta1 = float(np.mean(sweep_b)) if sweep_b is not None and sweep_b.size > 0 else 0.0
    beta1_val = int(np.max(pers_res.beta_curve)) if pers_res.beta_curve.size > 0 else 0

    # Geometric spatial phase charge (strictly separate from graph beta-1)
    q_spatial = None
    spatial_charge_available = False

    if montage_coordinates is not None:
        try:
            q_spatial = sensor_spatial_charge(phase[:, -1], montage_coordinates)
            spatial_charge_available = True
        except Exception:
            q_spatial = None
            spatial_charge_available = False
    else:
        side = int(math.isqrt(channels))
        if side * side == channels and side >= 2:
            try:
                grid_phase = phase[:, -1].reshape(side, side)
                coords = np.stack(np.mgrid[:side, :side], axis=-1).astype(float)
                q_spatial = spatial_winding_charge(grid_phase, coords)
                spatial_charge_available = True
            except Exception:
                q_spatial = None
                spatial_charge_available = False

    return {
        "channels": channels,
        "samples": samples,
        "is_finite": is_finite,
        "beta1_max": beta1_val,
        "filtration_beta1_max": sweep_max,
        "mean_beta1": mean_beta1,
        "integrated_landscape_area": float(pers_res.integrated_landscape_area),
        "spatial_charge": q_spatial,
        "spatial_charge_available": spatial_charge_available,
    }


def process_condition_stream(
    rec_dict: dict[str, Any],
    *,
    chunk_samples: int = 500,
    max_windows: int = 12,
    default_sfreq: float = 250.0,
) -> dict[str, Any]:
    """Streams and summarizes topology metrics for a single recording condition."""
    file_path = rec_dict["file_path"]
    chunks, sfreq, coords = stream_file_chunks(
        file_path,
        chunk_samples=chunk_samples,
        max_windows=max_windows,
        default_sfreq=rec_dict.get("sample_rate") or default_sfreq,
    )

    windows = []
    total_samples = 0
    all_finite = True

    for chunk in chunks:
        w_res = compute_window_topology(chunk, sfreq, montage_coordinates=coords)
        windows.append(w_res)
        total_samples += chunk.shape[1]
        if not w_res["is_finite"]:
            all_finite = False

    n_windows = len(windows)
    if n_windows == 0:
        raise ValueError(f"Zero windows extracted from recording: {file_path}")

    # Summarize descriptive metrics
    mean_landscape = float(np.mean([w["integrated_landscape_area"] for w in windows]))
    mean_filt_beta1 = float(np.mean([w["filtration_beta1_max"] for w in windows]))
    mean_beta1 = float(np.mean([w["mean_beta1"] for w in windows]))
    
    q_vals = [w["spatial_charge"] for w in windows if w["spatial_charge"] is not None]
    q_available = any(w["spatial_charge_available"] for w in windows)
    mean_q = float(np.mean(q_vals)) if q_vals else None

    channels = windows[0]["channels"]

    return {
        "file_path": file_path,
        "format": rec_dict.get("format", "unknown"),
        "checksum": rec_dict.get("checksum", ""),
        "subject": rec_dict.get("subject"),
        "session": rec_dict.get("session"),
        "condition": rec_dict.get("condition"),
        "is_synthetic": bool(rec_dict.get("is_synthetic", False)),
        "provenance": rec_dict.get("provenance", {}),
        "sample_count": total_samples,
        "channel_count": channels,
        "sampling_rate_hz": sfreq,
        "windows_processed": n_windows,
        "finite_value_status": all_finite,
        "beta1_summary": {
            "mean_filtration_beta1_max": mean_filt_beta1,
            "mean_beta1": mean_beta1,
        },
        "landscape_area_summary": {
            "mean_integrated_landscape_area": mean_landscape,
        },
        "spatial_charge_summary": {
            "available": q_available,
            "mean_spatial_charge": mean_q,
        },
    }


def execute_cohort_topology(
    manifest_path: str | Path,
    output_dir: str | Path,
    *,
    chunk_samples: int = 500,
    max_windows: int = 12,
    diagnostic_only: bool = False,
    allow_insufficient: bool = False,
    seed: int = 42,
) -> dict[str, Any]:
    """Consumes a paired cohort manifest and executes streaming topology evaluation."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    manifest_dict, refusal_reasons, is_executable = load_and_validate_manifest(
        manifest_path,
        diagnostic_only=diagnostic_only,
        allow_insufficient=allow_insufficient,
    )

    if not is_executable:
        refusal_payload = {
            "schema": "NeuroTopologySim.CohortTopologyExecutionSummary.v1",
            "execution_status": "REFUSED",
            "manifest_path": str(manifest_path),
            "manifest_status": manifest_dict.get("status", "unknown"),
            "refusal_reasons": refusal_reasons,
            "pairs_processed": 0,
            "pairs_skipped": 0,
            "processed_pairs": [],
            "skipped_pairs": [],
            "scientific_note": SAFE_SCIENTIFIC_NOTE,
        }
        write_null_safe_json(out / "cohort_topology_execution_summary.json", refusal_payload)
        return refusal_payload

    paired_records = manifest_dict.get("paired_records", [])
    processed_pairs: list[dict[str, Any]] = []
    skipped_pairs: list[dict[str, Any]] = []

    # Stream one subject/session pair at a time without full cohort in memory
    for idx, pair in enumerate(paired_records):
        key = pair.get("pairing_key", {})
        rec_a = pair.get("condition_a_record", {})
        rec_b = pair.get("condition_b_record", {})

        try:
            res_a = process_condition_stream(
                rec_a,
                chunk_samples=chunk_samples,
                max_windows=max_windows,
            )
            res_b = process_condition_stream(
                rec_b,
                chunk_samples=chunk_samples,
                max_windows=max_windows,
            )

            is_synthetic_pair = res_a["is_synthetic"] or res_b["is_synthetic"]
            area_a = res_a["landscape_area_summary"]["mean_integrated_landscape_area"]
            area_b = res_b["landscape_area_summary"]["mean_integrated_landscape_area"]
            delta_area = abs(area_a - area_b) if (area_a is not None and area_b is not None) else None

            pair_summary = {
                "pair_index": idx,
                "pairing_key": key,
                "is_synthetic": is_synthetic_pair,
                "finite_value_status": res_a["finite_value_status"] and res_b["finite_value_status"],
                "condition_a": res_a,
                "condition_b": res_b,
                "delta_landscape_area": delta_area,
                "status": "PROCESSED",
            }
            processed_pairs.append(pair_summary)

        except Exception as exc:
            skipped_pairs.append({
                "pair_index": idx,
                "pairing_key": key,
                "reason": str(exc),
                "condition_a_file": rec_a.get("file_path"),
                "condition_b_file": rec_b.get("file_path"),
                "status": "SKIPPED",
            })

    # Descriptive cohort-level aggregation
    empirical_processed = [p for p in processed_pairs if not p["is_synthetic"]]
    synthetic_processed = [p for p in processed_pairs if p["is_synthetic"]]

    n_empirical = len(empirical_processed)
    n_synthetic = len(synthetic_processed)

    # Aggregated metrics for empirical pairs
    cond_a_name = manifest_dict.get("condition_a", "condition_a")
    cond_b_name = manifest_dict.get("condition_b", "condition_b")

    def _calc_stats(values: Sequence[float]) -> dict[str, float | int | None]:
        arr = np.asarray([v for v in values if v is not None and math.isfinite(v)], dtype=float)
        if arr.size == 0:
            return {"n": 0, "mean": None, "median": None, "variance": None}
        return {
            "n": int(arr.size),
            "mean": float(arr.mean()),
            "median": float(np.median(arr)),
            "variance": float(arr.var(ddof=1)) if arr.size > 1 else None,
        }

    empirical_aggregate = {
        cond_a_name: {
            "mean_beta1": _calc_stats([p["condition_a"]["beta1_summary"]["mean_beta1"] for p in empirical_processed]),
            "landscape_area": _calc_stats([p["condition_a"]["landscape_area_summary"]["mean_integrated_landscape_area"] for p in empirical_processed]),
        },
        cond_b_name: {
            "mean_beta1": _calc_stats([p["condition_b"]["beta1_summary"]["mean_beta1"] for p in empirical_processed]),
            "landscape_area": _calc_stats([p["condition_b"]["landscape_area_summary"]["mean_integrated_landscape_area"] for p in empirical_processed]),
        },
    }

    # Descriptive non-parametric Wilcoxon test on empirical pairs
    wilcoxon_tests: dict[str, Any] = {}
    if n_empirical >= 2:
        pairs_area = [(p["condition_a"]["landscape_area_summary"]["mean_integrated_landscape_area"],
                       p["condition_b"]["landscape_area_summary"]["mean_integrated_landscape_area"])
                      for p in empirical_processed]
        a_vals, b_vals = np.asarray(pairs_area, dtype=float).T
        if np.allclose(a_vals, b_vals):
            wilcoxon_tests["landscape_area"] = {
                "n_pairs": n_empirical,
                "statistic": 0.0,
                "p_value": 1.0,
                "status": "all_paired_differences_zero",
            }
        else:
            try:
                res = wilcoxon(a_vals, b_vals, zero_method="wilcox", alternative="two-sided")
                wilcoxon_tests["landscape_area"] = {
                    "n_pairs": n_empirical,
                    "statistic": float(res.statistic),
                    "p_value": float(res.pvalue),
                    "status": "computed",
                }
            except Exception as e:
                wilcoxon_tests["landscape_area"] = {
                    "n_pairs": n_empirical,
                    "statistic": None,
                    "p_value": None,
                    "status": f"test_error: {e}",
                }
    else:
        wilcoxon_tests["landscape_area"] = {
            "n_pairs": n_empirical,
            "statistic": None,
            "p_value": None,
            "status": "insufficient_paired_subjects",
        }

    # Determine execution status adhering strictly to guardrails
    if n_empirical == 0 and n_synthetic > 0:
        # Synthetic inputs must NEVER emit PASS
        exec_status = "SYNTHETIC_EVALUATION"
    elif n_synthetic > 0 and n_empirical > 0:
        exec_status = "INCONCLUSIVE_SYNTHETIC_MIXED"
    elif n_empirical >= manifest_dict.get("min_pairs", 2):
        exec_status = "VALID_COHORT_PROCESSED"
    elif n_empirical > 0:
        exec_status = "INSUFFICIENT_PAIRS_PROCESSED"
    else:
        exec_status = "NO_PAIRS_PROCESSED"

    summary_payload = {
        "schema": "NeuroTopologySim.CohortTopologyExecutionSummary.v1",
        "execution_status": exec_status,
        "manifest_path": str(manifest_path),
        "manifest_status": manifest_dict.get("status"),
        "condition_a": cond_a_name,
        "condition_b": cond_b_name,
        "min_pairs_required": manifest_dict.get("min_pairs", 2),
        "total_pairs_in_manifest": len(paired_records),
        "pairs_processed": len(processed_pairs),
        "pairs_skipped": len(skipped_pairs),
        "empirical_pairs_count": n_empirical,
        "synthetic_pairs_count": n_synthetic,
        "descriptive_aggregate": empirical_aggregate,
        "descriptive_wilcoxon": wilcoxon_tests,
        "processed_pairs": processed_pairs,
        "skipped_pairs": skipped_pairs,
        "scientific_note": SAFE_SCIENTIFIC_NOTE,
    }

    # Write atomic null-safe JSON
    json_path = out / "cohort_topology_execution_summary.json"
    write_null_safe_json(json_path, summary_payload)

    # Write flat CSV of pair metrics
    csv_path = out / "cohort_topology_execution_summary.csv"
    csv_rows = []
    for p in processed_pairs:
        k_str = "__".join(f"{k}-{v}" for k, v in sorted(p["pairing_key"].items()))
        ca = p["condition_a"]
        cb = p["condition_b"]
        csv_rows.append({
            "pair_key": k_str,
            "is_synthetic": p["is_synthetic"],
            "finite_status": p["finite_value_status"],
            "delta_landscape_area": p["delta_landscape_area"],
            "cond_a_samples": ca["sample_count"],
            "cond_a_channels": ca["channel_count"],
            "cond_a_sfreq": ca["sampling_rate_hz"],
            "cond_a_mean_beta1": ca["beta1_summary"]["mean_beta1"],
            "cond_a_mean_filt_beta1": ca["beta1_summary"]["mean_filtration_beta1_max"],
            "cond_a_landscape_area": ca["landscape_area_summary"]["mean_integrated_landscape_area"],
            "cond_a_spatial_q": ca["spatial_charge_summary"]["mean_spatial_charge"],
            "cond_b_samples": cb["sample_count"],
            "cond_b_channels": cb["channel_count"],
            "cond_b_sfreq": cb["sampling_rate_hz"],
            "cond_b_mean_beta1": cb["beta1_summary"]["mean_beta1"],
            "cond_b_mean_filt_beta1": cb["beta1_summary"]["mean_filtration_beta1_max"],
            "cond_b_landscape_area": cb["landscape_area_summary"]["mean_integrated_landscape_area"],
            "cond_b_spatial_q": cb["spatial_charge_summary"]["mean_spatial_charge"],
        })

    fieldnames = [
        "pair_key", "is_synthetic", "finite_status", "delta_landscape_area",
        "cond_a_samples", "cond_a_channels", "cond_a_sfreq", "cond_a_mean_beta1",
        "cond_a_mean_filt_beta1", "cond_a_landscape_area", "cond_a_spatial_q",
        "cond_b_samples", "cond_b_channels", "cond_b_sfreq", "cond_b_mean_beta1",
        "cond_b_mean_filt_beta1", "cond_b_landscape_area", "cond_b_spatial_q",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in csv_rows:
            cleaned_row = {
                k: ("" if v is None else f"{v:g}" if isinstance(v, float) else str(v))
                for k, v in row.items()
            }
            writer.writerow(cleaned_row)

    return summary_payload


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Local streaming paired-cohort topology execution runner."
    )
    p.add_argument(
        "--manifest", "--manifest-path",
        dest="manifest_path",
        type=Path,
        required=True,
        help="Path to validated paired cohort manifest JSON.",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/cohort_topology"),
        help="Output directory for topology execution summaries.",
    )
    p.add_argument(
        "--chunk-samples",
        type=int,
        default=500,
        help="Sample count per streaming window chunk.",
    )
    p.add_argument(
        "--max-windows",
        type=int,
        default=12,
        help="Maximum number of windows to stream per condition.",
    )
    p.add_argument(
        "--diagnostic-only",
        action="store_true",
        help="Allow diagnostic execution even if manifest reports insufficient_pairs, no_data, or malformed.",
    )
    p.add_argument(
        "--allow-insufficient",
        action="store_true",
        help="Allow execution when empirical pairs are below min_pairs.",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic random seed.",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    summary = execute_cohort_topology(
        manifest_path=args.manifest_path,
        output_dir=args.output_dir,
        chunk_samples=args.chunk_samples,
        max_windows=args.max_windows,
        diagnostic_only=args.diagnostic_only,
        allow_insufficient=args.allow_insufficient,
        seed=args.seed,
    )
    status = summary.get("execution_status")
    print(f"Cohort Topology Execution Status: {status}")
    print(f"Pairs Processed: {summary.get('pairs_processed', 0)}")
    print(f"Pairs Skipped: {summary.get('pairs_skipped', 0)}")
    return 0 if status in ("VALID_COHORT_PROCESSED", "SYNTHETIC_EVALUATION", "INSUFFICIENT_PAIRS_PROCESSED") else 1


if __name__ == "__main__":
    sys.exit(main())
