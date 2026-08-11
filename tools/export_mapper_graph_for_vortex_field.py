"""
Export a KeplerMapper topological network graph over the ds005620 PITNN
cohort's real per-window feature vectors, for the /mapper-graph 3D viewer.

Reads `outputs/pitnn_cohort/ds005620/subjects/*.json` (the same real,
already-computed per-window records `tools/export_cohort_vortex_field_data.py`
and `tools/export_vortex_field_clustering_landscape.py` also read) -- 20
subjects x 2 conditions x 3 real 10s analysis windows = up to 120 real
5-dimensional feature vectors:

  [mean_plv, integrated_landscape_area, beta1, filtration_beta1_max, q_spatial]

all genuine per-window scalars already computed by the PITNN cohort streaming
pipeline (`tools/stream_pitnn_cohort_ds005620.py`), not fabricated for this
export. KeplerMapper (github.com/scikit-tda/kepler-mapper, MIT license) then
builds a Mapper graph: a 1D lens (sum of the standardized features), a cover
of overlapping intervals, and DBSCAN clustering within each cover interval.
Each Mapper node is a cluster of real windows; each edge records shared real
window membership between two overlapping clusters.

The exported node/edge JSON carries only real, traceable data per node: which
(subject, condition, window) rows it contains, the real awake/sedated
fraction, and the real per-feature mean -- no synthetic or interpolated
values.

Usage:
  python tools/export_mapper_graph_for_vortex_field.py \\
      --cohort-dir outputs/pitnn_cohort/ds005620 \\
      --out outputs/pitnn_cohort/ds005620/mapper_graph.json
"""
from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Any

import kmapper as km
import numpy as np
from sklearn.cluster import DBSCAN

FEATURES = ["mean_plv", "integrated_landscape_area", "beta1", "filtration_beta1_max", "q_spatial"]


def _load_rows(cohort_dir: Path) -> list[dict[str, Any]]:
    files = sorted(glob.glob(str(cohort_dir / "subjects" / "sub-*.json")))
    if not files:
        raise FileNotFoundError(f"No subject files under {cohort_dir / 'subjects'}")
    rows: list[dict[str, Any]] = []
    for f in files:
        record = json.loads(Path(f).read_text())
        subject = record["subject"]
        for cond in ("awake", "sedated"):
            for w in record["topology_windows"][cond]:
                rows.append(
                    {
                        "subject": subject,
                        "condition": cond,
                        "window": w["window"],
                        "start_s": w["start_s"],
                        "features": [float(w[f]) for f in FEATURES],
                    }
                )
    return rows


def build_mapper_graph(cohort_dir: Path, n_cubes: int = 10, perc_overlap: float = 0.4,
                        eps: float = 0.5, min_samples: int = 2) -> dict[str, Any]:
    rows = _load_rows(cohort_dir)
    X = np.asarray([r["features"] for r in rows], dtype=float)
    X_std = (X - X.mean(axis=0)) / np.where(X.std(axis=0) > 0, X.std(axis=0), 1.0)

    mapper = km.KeplerMapper(verbose=0)
    lens = mapper.project(X_std, projection="sum", scaler=None)
    graph = mapper.map(
        lens, X_std,
        cover=km.Cover(n_cubes=n_cubes, perc_overlap=perc_overlap),
        clusterer=DBSCAN(eps=eps, min_samples=min_samples),
    )

    node_ids = sorted(graph["nodes"].keys())
    node_index = {nid: i for i, nid in enumerate(node_ids)}
    nodes = []
    for nid in node_ids:
        member_idx = graph["nodes"][nid]
        members = [rows[i] for i in member_idx]
        n_awake = sum(1 for m in members if m["condition"] == "awake")
        feat_mean = X[member_idx].mean(axis=0)
        nodes.append(
            {
                "id": nid,
                "size": len(members),
                "awake_fraction": round(n_awake / len(members), 4),
                "feature_mean": {name: round(float(v), 6) for name, v in zip(FEATURES, feat_mean)},
                "members": [
                    {"subject": m["subject"], "condition": m["condition"], "window": m["window"], "start_s": m["start_s"]}
                    for m in members
                ],
            }
        )

    edges = []
    for src, targets in graph["links"].items():
        for dst in targets:
            if node_index[src] < node_index[dst]:
                edges.append({"source": src, "target": dst})

    return {
        "n_windows": len(rows),
        "n_subjects": len({r["subject"] for r in rows}),
        "features": FEATURES,
        "params": {"n_cubes": n_cubes, "perc_overlap": perc_overlap, "eps": eps, "min_samples": min_samples},
        "nodes": nodes,
        "edges": edges,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort-dir", default="outputs/pitnn_cohort/ds005620")
    parser.add_argument("--out", required=True)
    parser.add_argument("--n-cubes", type=int, default=10)
    parser.add_argument("--perc-overlap", type=float, default=0.4)
    parser.add_argument("--eps", type=float, default=0.5)
    parser.add_argument("--min-samples", type=int, default=2)
    args = parser.parse_args()

    result = build_mapper_graph(
        Path(args.cohort_dir), n_cubes=args.n_cubes, perc_overlap=args.perc_overlap,
        eps=args.eps, min_samples=args.min_samples,
    )
    out_path = Path(args.out)
    out_path.write_text(json.dumps(result, separators=(",", ":")))
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes); "
          f"{len(result['nodes'])} nodes, {len(result['edges'])} edges, {result['n_windows']} windows")


if __name__ == "__main__":
    main()
