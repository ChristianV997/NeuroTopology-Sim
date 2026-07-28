"""Read empirical BTC/ICFT result artifacts into a stable Command Center payload."""
from __future__ import annotations

import csv
import json
import math
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_ROOT = REPOSITORY_ROOT / "outputs/btc_icft/ds005620/full_21_optimized"
DEFAULT_PITNN_COHORT_ROOT = REPOSITORY_ROOT / "outputs/pitnn_cohort/ds005620"
SCHEMA_VERSION = "command-center-real-results/v1"
PROXY_METRICS = {
    "q_net": "channel-mean topology proxy; not a demonstrated conserved physical charge",
    "f_dress": "topology dressing proxy; not a validated thermodynamic friction or TUR estimator",
    "defect_density": "triangle-based proxy from the current Level T method",
}


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _result_root(root: str | Path | None = None) -> Path:
    return Path(root or os.getenv("NEUROTOPOLOGY_RESULTS_ROOT", DEFAULT_RESULTS_ROOT))


def _read_manifest(root: Path) -> dict[str, Any]:
    path = root / "manifest.json"
    if not path.exists():
        return {"processed_subjects": {}, "failed_subjects": {}, "source": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"processed_subjects": {}, "failed_subjects": {}, "source": str(path), "read_error": "manifest_unreadable"}
    if not isinstance(data, dict):
        return {"processed_subjects": {}, "failed_subjects": {}, "source": str(path), "read_error": "manifest_not_object"}
    data.setdefault("processed_subjects", {})
    data.setdefault("failed_subjects", {})
    data["source"] = str(path)
    return data


def _reports(root: Path) -> list[str]:
    names = sorted({*root.glob("REPORT_*.md"), *root.glob("*_REPORT.md")})
    return [str(path) for path in names]


def _window_rows(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*_features_t.csv")):
        try:
            handle = path.open(encoding="utf-8", newline="")
        except OSError:
            continue
        with handle:
            for raw in csv.DictReader(handle):
                task = (raw.get("task_label") or "unknown").strip() or "unknown"
                row = {
                    "row_id": raw.get("row_id", ""),
                    "subject_id": raw.get("subject_id", ""),
                    "task_label": task,
                    "window_id": raw.get("window_id", ""),
                    "window_start_s": _number(raw.get("window_start_s")),
                    "window_end_s": _number(raw.get("window_end_s")),
                    "q_net": _number(raw.get("q_net")),
                    "q_abs": _number(raw.get("q_abs")),
                    "f_dress": _number(raw.get("f_dress")),
                    "defect_density": _number(raw.get("defect_density")),
                    "topology_quality": _number(raw.get("topology_quality")),
                    "null_method": raw.get("null_method", ""),
                    "warnings": raw.get("warnings", ""),
                    "source_file": raw.get("source_file", ""),
                    "source_artifact": str(path),
                }
                if row["q_net"] is not None and row["f_dress"] is not None:
                    rows.append(row)
    return rows


def _summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[row["task_label"]].append(row)
    output = []
    for task, items in sorted(buckets.items()):
        subjects = {item["subject_id"] for item in items if item["subject_id"]}
        output.append({
            "task_label": task,
            "window_count": len(items),
            "subject_count": len(subjects),
            "q_net_mean": sum(item["q_net"] for item in items) / len(items),
            "f_dress_mean": sum(item["f_dress"] for item in items) / len(items),
            "defect_density_mean": sum(item["defect_density"] or 0.0 for item in items) / len(items),
            "topology_quality_mean": sum(item["topology_quality"] or 0.0 for item in items) / len(items),
        })
    return output


def _mean(items: list[dict[str, Any]], field: str) -> float | None:
    values = [item[field] for item in items if item.get(field) is not None]
    return sum(values) / len(values) if values else None


def _subject_summaries(rows: list[dict[str, Any]], state_order: list[str]) -> list[dict[str, Any]]:
    """Aggregate only existing window telemetry for an operator-facing table."""
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[row["subject_id"] or "unknown"].append(row)

    summaries = []
    for subject_id, items in sorted(buckets.items()):
        states = []
        for state in state_order:
            state_items = [item for item in items if item["task_label"] == state]
            if not state_items:
                continue
            states.append({
                "task_label": state,
                "window_count": len(state_items),
                "q_net_mean": _mean(state_items, "q_net"),
                "f_dress_mean": _mean(state_items, "f_dress"),
                "defect_density_mean": _mean(state_items, "defect_density"),
                "topology_quality_mean": _mean(state_items, "topology_quality"),
            })
        summaries.append({
            "subject_id": subject_id,
            "window_count": len(items),
            "warning_count": sum(bool(item["warnings"].strip()) for item in items),
            "q_net_mean": _mean(items, "q_net"),
            "f_dress_mean": _mean(items, "f_dress"),
            "defect_density_mean": _mean(items, "defect_density"),
            "topology_quality_mean": _mean(items, "topology_quality"),
            "states": states,
        })
    return summaries


def _failure_registry(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    failures = manifest.get("failed_subjects", {})
    if not isinstance(failures, dict):
        return []
    return [{
        "subject_id": subject_id,
        "reason": reason if isinstance(reason, str) else json.dumps(reason, sort_keys=True),
        "status": "needs_review",
    } for subject_id, reason in sorted(failures.items())]


def build_real_results(root: str | Path | None = None) -> dict[str, Any]:
    result_root = _result_root(root)
    manifest = _read_manifest(result_root)
    rows = _window_rows(result_root) if result_root.exists() else []
    state_order = [state for state in ("awake", "sed", "sed2") if any(r["task_label"] == state for r in rows)]
    state_order.extend(sorted({r["task_label"] for r in rows} - set(state_order)))
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "available" if rows else "not_available",
        "dataset": "ds005620" if "ds005620" in str(result_root) else result_root.name,
        "results_root": str(result_root),
        "manifest": manifest,
        "reports": _reports(result_root) if result_root.exists() else [],
        "metric_provenance": PROXY_METRICS,
        "evidence_state": "empirical_window_telemetry_with_proxy_labels",
        "claim_scope": "research_hypothesis_not_clinical_or_physical_proof",
        "state_order": state_order,
        "state_summaries": _summaries(rows),
        "subject_summaries": _subject_summaries(rows, state_order),
        "data_quality": {
            "window_count": len(rows),
            "subject_count": len({row["subject_id"] for row in rows if row["subject_id"]}),
            "warning_window_count": sum(bool(row["warnings"].strip()) for row in rows),
            "level_t_artifact_count": len({row["source_artifact"] for row in rows}),
        },
        "windows": rows,
        "spatial_artifact": {
            "status": "unavailable",
            "reason": "Current Level T CSVs do not contain channel phase, cortical coordinates, defect locations, wave vectors, or beta1.",
            "required_fields": ["channel_coordinates", "phase", "defects", "wave_vectors", "beta1", "coordinate_frame", "quality_control"],
        },
        "source_artifacts": sorted({manifest["source"], *[row["source_artifact"] for row in rows], *(_reports(result_root) if result_root.exists() else [])}),
        "failure_registry": _failure_registry(manifest),
    }


def _pitnn_cohort_root(root: str | Path | None = None) -> Path:
    return Path(root or os.getenv("NEUROTOPOLOGY_PITNN_COHORT_ROOT", DEFAULT_PITNN_COHORT_ROOT))


def build_pitnn_cohort_spatial_artifact(root: str | Path | None = None) -> dict[str, Any]:
    """Real channel-coordinate defect maps from `tools/stream_pitnn_cohort_ds005620.py`.

    This is a SEPARATE, additive source from `build_real_results`'s `spatial_artifact`
    (which stays tied to the Level-T channel-mean CSVs and correctly reports
    "unavailable" there -- those CSVs never carried coordinates or phase). The PITNN
    cohort pipeline's `--export-spatial` flag calls
    `validation.montage_topology.signed_defect_map` on each condition's real montage
    and last-window phase, which is exactly the set of fields the CSV path was always
    missing: `channel_coordinates`, `phase`, `defects`, `beta1`, `coordinate_frame`,
    `quality_control`. `wave_vectors` stays `None` -- no wave-vector estimator exists
    anywhere in this repo, so it is reported absent rather than fabricated.

    Absence (no cohort run yet, or run without `--export-spatial`) is reported as
    `"unavailable"` with the same required_fields contract as the CSV path, never as
    an empty-but-"available" bundle.
    """
    result_root = _pitnn_cohort_root(root)
    subjects_dir = result_root / "subjects"
    required_fields = ["channel_coordinates", "phase", "defects", "wave_vectors", "beta1", "coordinate_frame", "quality_control"]
    if not subjects_dir.exists():
        return {
            "status": "unavailable",
            "reason": f"No PITNN cohort subject records at {subjects_dir}. Run "
                      "tools/stream_pitnn_cohort_ds005620.py --export-spatial first.",
            "required_fields": required_fields,
        }

    subjects: list[dict[str, Any]] = []
    for path in sorted(subjects_dir.glob("sub-*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        spatial = record.get("spatial") or {}
        conditions = {label: snap for label, snap in spatial.items() if snap}
        if not conditions:
            continue
        subjects.append({
            "subject_id": record.get("subject", path.stem),
            "conditions": conditions,
            "bottleneck_distance_h1_last_window": record.get("cubical_h1_bottleneck_distance_last_window"),
        })

    if not subjects:
        return {
            "status": "unavailable",
            "reason": f"{subjects_dir} exists but no subject record includes a spatial "
                      "snapshot. Re-run with --export-spatial.",
            "required_fields": required_fields,
        }

    return {
        "status": "available",
        "source": "tools/stream_pitnn_cohort_ds005620.py --export-spatial",
        "results_root": str(result_root),
        "coordinate_frame": "sensor_2d_projection_of_standard_1020_montage",
        "subject_count": len(subjects),
        "subjects": subjects,
        "scientific_note": "Per-subject last-window signed defect maps and betti1; "
                            "descriptive spatial topology, not a validated physical or "
                            "clinical measurement.",
    }


def build_pitnn_cohort_persistence_artifact(root: str | Path | None = None) -> dict[str, Any]:
    """Real cubical-persistence H1 birth/death diagrams from the PITNN cohort run.

    Populated only when the streaming run used `--export-persistence`
    (`tools/stream_pitnn_cohort_ds005620.py`'s `window_topology` then calls
    `core.topology.export_persistence_json` on each window's PLV matrix). This
    reads the LAST window's H1 diagram per condition per subject -- the same
    window `cubical_h1_bottleneck_distance_last_window` was computed from, so a
    viewer plotting both is showing the same pair of diagrams the bottleneck
    number describes, not a different window.

    "Available" always means every subject record it returns actually carries a
    diagram; a subject whose windows lack `cubical_persistence` (streaming run
    without `--export-persistence`) is skipped, and a cohort where none carry it
    is reported "unavailable" -- never backfilled with an empty plot.
    """
    result_root = _pitnn_cohort_root(root)
    subjects_dir = result_root / "subjects"
    if not subjects_dir.exists():
        return {
            "status": "unavailable",
            "reason": f"No PITNN cohort subject records at {subjects_dir}. Run "
                      "tools/stream_pitnn_cohort_ds005620.py --export-persistence first.",
        }

    subjects: list[dict[str, Any]] = []
    for path in sorted(subjects_dir.glob("sub-*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        windows = record.get("topology_windows") or {}
        diagrams: dict[str, list[list[float | None]]] = {}
        for label, rows in windows.items():
            if not rows:
                continue
            cp = rows[-1].get("cubical_persistence")
            if not cp:
                continue
            h1 = cp.get("diagrams", {}).get("1")
            if h1 is None:
                continue
            diagrams[label] = h1
        if not diagrams:
            continue
        subjects.append({
            "subject_id": record.get("subject", path.stem),
            "diagrams_h1": diagrams,
            "bottleneck_distance_h1_last_window": record.get("cubical_h1_bottleneck_distance_last_window"),
        })

    if not subjects:
        return {
            "status": "unavailable",
            "reason": f"{subjects_dir} exists but no subject record includes a cubical "
                      "persistence diagram. Re-run with --export-persistence.",
        }

    return {
        "status": "available",
        "source": "tools/stream_pitnn_cohort_ds005620.py --export-persistence",
        "results_root": str(result_root),
        "subject_count": len(subjects),
        "subjects": subjects,
        "scientific_note": "GUDHI sub-level cubical persistence on each window's PLV "
                            "matrix, last window per condition; a descriptive spatial-"
                            "network summary, not a validated physical or clinical "
                            "measurement. Infinite-death H0 features are omitted from H1.",
    }


def build_visualization_payload(root: str | Path | None = None) -> dict[str, Any]:
    results = build_real_results(root)
    return {
        "schema_version": "cortex-viewer/v1",
        "dataset": results["dataset"],
        "metric_provenance": results["metric_provenance"],
        "state_order": results["state_order"],
        "frames": results["windows"],
        "phase_space": results["state_summaries"],
        "subject_summaries": results["subject_summaries"],
        "spatial_artifact": results["spatial_artifact"],
        "pitnn_cohort_spatial_artifact": build_pitnn_cohort_spatial_artifact(),
        "pitnn_cohort_persistence_artifact": build_pitnn_cohort_persistence_artifact(),
        "source_artifacts": results["source_artifacts"],
    }


def build_command_center_registry(root: str | Path | None = None) -> dict[str, Any]:
    """Return a UI-safe, read-only inventory of empirical run artifacts.

    The registry deliberately describes commands without executing them.  It is
    intended for an operations UI where discovery and review are separated from
    data acquisition or pipeline execution.
    """
    results = build_real_results(root)
    result_root = _result_root(root)
    processed = results["manifest"].get("processed_subjects", {})
    failed = results["manifest"].get("failed_subjects", {})
    report_files = [Path(path) for path in results["reports"]]
    pdf_reports = sorted(result_root.glob("*.pdf")) if result_root.exists() else []
    failed_subjects = results["manifest"].get("failed_subjects", {})
    pitnn_cohort_spatial = build_pitnn_cohort_spatial_artifact()

    artifacts = [{
        "id": "manifest",
        "name": "manifest.json",
        "kind": "run_manifest",
        "description": "Atomic completion checkpoint and per-subject row counts.",
        "downloadable": True,
        "path": str(result_root / "manifest.json"),
    }]
    for index, report in enumerate([*report_files, *pdf_reports]):
        artifacts.append({
            "id": f"report-{index}",
            "name": report.name,
            "kind": "compiled_report" if report.suffix.lower() == ".pdf" else "run_report",
            "description": "Compiled full-dataset report." if report.suffix.lower() == ".pdf" else "Source run report in Markdown.",
            "downloadable": True,
            "path": str(report),
        })
    artifacts.append({
        "id": "level-t-telemetry",
        "name": f"{len(set(row['source_artifact'] for row in results['windows']))} Level T CSV artifacts",
        "kind": "window_telemetry",
        "description": f"{len(results['windows'])} empirical window rows; exposed through the visualization API, not a browser bulk download.",
        "downloadable": False,
        "path": str(result_root),
    })

    return {
        "schema_version": "command-center-registry/v1",
        "data_mode": "real",
        "dataset_registry": [{
            "accession": results["dataset"],
            "label": "Propofol consciousness EEG",
            "status": results["status"],
            "participant_count": len(processed),
            "failed_subject_count": len(failed),
            "window_count": len(results["windows"]),
            "state_order": results["state_order"],
            "evidence_state": results["evidence_state"],
        }],
        "artifact_registry": artifacts,
        "metric_registry": [{"id": key, "label": key.replace("_", " "), "provenance": description, "available": any(row.get(key) is not None for row in results["windows"])} for key, description in results["metric_provenance"].items()],
        "failure_registry": results["failure_registry"],
        "run_history": [{
            "run_id": f"{results['dataset']}-full-21-optimized",
            "dataset": results["dataset"],
            "label": "Propofol consciousness EEG / full_21_optimized",
            "status": results["status"],
            "completed_subject_count": len(processed),
            "failed_subject_count": len(failed),
            "window_count": len(results["windows"]),
            "failure_summary": "No failed subjects recorded in manifest." if not failed_subjects else f"{len(failed_subjects)} subject failures recorded in manifest.",
            "source": str(result_root / "manifest.json"),
        }],
        "proposed_runs": [
            {
                "proposal_id": "rerun-failed-subjects-with-preflight",
                "label": "Targeted rerun: failed subjects + preflight",
                "dataset": results["dataset"],
                "status": "planned",
                "scope": "Only subjects listed in manifest.failed_subjects; preserve successful artifacts.",
                "acceptance": ["input contract passes", "per-subject checkpoint is atomic", "failure reason is retained", "output manifest validates"],
            },
            {
                "proposal_id": "spatial-topology-pilot",
                "label": "Spatial topology pilot",
                "dataset": results["dataset"],
                "status": "available" if pitnn_cohort_spatial["status"] == "available" else "blocked_pending_inputs",
                "scope": "Export channel coordinates, phase/wave-vector fields, defect locations, and registered coordinate frame.",
                "acceptance": ["coordinate frame declared", "QC mask emitted", "defect localization validated on synthetic control", "no anatomical claim without registration"],
                "note": (
                    f"{pitnn_cohort_spatial['subject_count']} subject(s) with real defect maps "
                    "via tools/stream_pitnn_cohort_ds005620.py --export-spatial."
                    if pitnn_cohort_spatial["status"] == "available"
                    else "Run tools/stream_pitnn_cohort_ds005620.py --export-spatial to populate this."
                ),
            },
            {
                "proposal_id": "cross-dataset-replication",
                "label": "Cross-dataset replication candidate",
                "dataset": "ds000245 or a pre-registered EEG replication",
                "status": "candidate",
                "scope": "Compare effect directions and uncertainty with the same proxy definitions and null model.",
                "acceptance": ["dataset provenance recorded", "protocol compatibility reviewed", "effect sizes and confidence intervals reported"],
            },
        ],
        "command_registry": [
            {
                "id": "refresh-empirical-status",
                "label": "Refresh empirical status",
                "endpoint": "/command-center/status",
                "kind": "read_only",
                "execution_allowed": False,
            },
            {
                "id": "open-cortex-viewer",
                "label": "Open cortex playback",
                "endpoint": "/cortex",
                "kind": "viewer",
                "execution_allowed": False,
            },
            {
                "id": "dataset-candidates",
                "label": "Find datasets to verify",
                "endpoint": "/datasets/search",
                "kind": "candidate_discovery",
                "execution_allowed": False,
            },
            {
                "id": "export-osc-replay",
                "label": "Prepare local OSC replay",
                "endpoint": "tools/visualization/osc_broadcaster.py",
                "kind": "local_manual_command",
                "execution_allowed": False,
            },
        ],
        "guardrails": {
            "pipeline_execution": "blocked_from_ui",
            "dataset_discovery": "candidates_to_verify_only",
            "metric_interpretation": results["claim_scope"],
            "spatial_data": results["spatial_artifact"],
            "pitnn_cohort_spatial_data": {"status": pitnn_cohort_spatial["status"]},
        },
    }


def get_downloadable_artifact(artifact_id: str, root: str | Path | None = None) -> Path | None:
    """Resolve an artifact id through the registry rather than a client path."""
    for artifact in build_command_center_registry(root)["artifact_registry"]:
        if artifact["id"] == artifact_id and artifact["downloadable"]:
            path = Path(artifact["path"])
            return path if path.is_file() else None
    return None
