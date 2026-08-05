"""
Export real DBSCAN clustering + persistence-landscape curves for the ds005620
PITNN cohort's /vortex-field viewer.

This must run in the ROOT environment (numpy/scikit-learn/GUDHI available), not
inside Awareness Studio's own process, which intentionally has none of those
heavy scientific deps (see CLAUDE.md's two-environment split). It reads the same
`outputs/pitnn_cohort/ds005620/subjects/*.json` records that
`tools/export_cohort_vortex_field_data.py` reads, and for every real per-triangle
winding-number field (grand-average and each of the 20 subjects, both
awake/sedated conditions) computes:

  - `clustering`: `validation.montage_topology.defect_spatial_clustering()`, the
    real, tested DBSCAN implementation over triangle centroids weighted by signed
    winding number (replaces the page's prior live-JS BFS connected-components
    reimplementation). `min_winding_abs` is set per entry as a fraction of that
    entry's own peak |winding|, since grand-average magnitudes are real but
    ~5-10x smaller than any one subject's (20 subjects' discrete +-1 values
    partly cancel in the mean) -- a fixed absolute threshold would silently
    under-cluster the cohort view.
  - `landscape`: `core.topology.persistence_landscape()` layer-0 curve computed
    from the real H1 birth/death pairs already in the subject records.

Writes a single JSON file keyed by "cohort_average" and each subject id, each
holding {"awake": {...}, "sedated": {...}}, for the Awareness Studio adapter
(`tools/command_center/real_results_adapter.py::build_vortex_field_payload`) to
read at request time with no numpy/sklearn import of its own.

Usage:
  python tools/export_vortex_field_clustering_landscape.py \\
      --cohort-dir outputs/pitnn_cohort/ds005620 \\
      --out outputs/pitnn_cohort/ds005620/vortex_field_clustering_landscape.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from core.topology import persistence_landscape
from tools.export_cohort_vortex_field_data import build_payload
from validation.montage_topology import defect_spatial_clustering


def _centroid_xy(coords: list[list[float]], tri: list[list[int]]) -> np.ndarray:
    coords_arr = np.asarray(coords, dtype=float)
    tri_arr = np.asarray(tri, dtype=int)
    return coords_arr[tri_arr].mean(axis=1)


def _cluster(wind: list[float], tri: list[list[int]], centroid_xy: np.ndarray) -> dict[str, Any]:
    wind_arr = np.asarray(wind, dtype=float)
    peak = float(np.abs(wind_arr).max()) if wind_arr.size else 0.0
    defect_map = {
        "triangle_indices": tri,
        "signed_winding": wind_arr,
        "centroid_xy": centroid_xy,
        "chirality": np.sign(wind_arr).astype(int),
        "n_valid_triangles": len(tri),
    }
    cl = defect_spatial_clustering(defect_map, min_winding_abs=max(0.02, peak * 0.3))
    return {
        "n_clusters": cl["n_clusters"],
        "n_noise": cl["n_noise"],
        "triangle_cluster_label": cl["triangle_cluster_label"].tolist(),
        "eps_used": cl["eps_used"],
    }


def _landscape(h1_pairs: list[list[float]]) -> dict[str, Any]:
    if not h1_pairs:
        return {"grid": [], "curve": []}
    diagram = np.asarray(h1_pairs, dtype=float)
    grid_max = float(diagram.max()) * 1.05 if diagram.size else 1.0
    grid = np.linspace(0.0, grid_max, 60)
    curve = persistence_landscape(diagram, grid, n_layers=1)[0]
    return {"grid": grid.tolist(), "curve": curve.tolist()}


def build_clustering_landscape(cohort_dir: Path) -> dict[str, Any]:
    payload = build_payload(cohort_dir)
    tri = payload["tri"]
    centroid_xy = _centroid_xy(payload["coords"], tri)

    def _enrich(wind_by_cond: dict[str, list[float]], h1_by_cond: dict[str, list]) -> dict[str, Any]:
        return {
            cond: {
                "clustering": _cluster(wind_by_cond[cond], tri, centroid_xy),
                "landscape": _landscape(h1_by_cond[cond]),
            }
            for cond in ("awake", "sedated")
        }

    out: dict[str, Any] = {
        "cohort_average": _enrich(
            {cond: payload["cohort_average"][cond]["wind_mean"] for cond in ("awake", "sedated")},
            {cond: payload["cohort_average"][cond]["h1_pooled"] for cond in ("awake", "sedated")},
        ),
        "subjects": {
            subject["id"]: _enrich(
                {cond: subject["conditions"][cond]["wind"] for cond in ("awake", "sedated")},
                {cond: subject["conditions"][cond]["h1"] for cond in ("awake", "sedated")},
            )
            for subject in payload["subjects"]
        },
    }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort-dir", default="outputs/pitnn_cohort/ds005620")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    result = build_clustering_landscape(Path(args.cohort_dir))
    out_path = Path(args.out)
    out_path.write_text(json.dumps(result, separators=(",", ":")))
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
