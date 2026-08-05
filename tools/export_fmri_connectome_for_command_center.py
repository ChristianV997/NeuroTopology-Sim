"""
Consolidate the ds005917 ketamine fMRI cohort's real per-subject graph structure
(parcel centroids + connectivity matrix, from `--save-graph-structure`) with its
existing real scalar topology/graph metrics (`cohort_result.json`) and paired
drug-vs-placebo statistics (`paired_stats.json`) into one JSON artifact for the
/fmri-connectome 3D viewer.

Reads numpy .npz graph-structure files (needs numpy, root environment only --
the Awareness Studio adapter that serves this data at request time has no numpy
dependency of its own, matching `tools/export_vortex_field_clustering_landscape.py`'s
and `tools/export_mapper_graph_for_vortex_field.py`'s precompute-then-read-as-JSON
pattern).

Usage:
  python tools/export_fmri_connectome_for_command_center.py \\
      --cohort-dir outputs/dual_engine/ds005917 \\
      --out outputs/dual_engine/ds005917/fmri_connectome.json
"""
from __future__ import annotations

import argparse
import glob
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

CONNECTIVITY_EDGE_THRESHOLD = 0.3  # |corr| >= this to keep an edge in the exported graph


def _round(x: float, n: int = 5) -> float:
    return round(float(x), n)


def _sanitize_nan(obj: Any) -> Any:
    """Replace NaN/Infinity with None so the payload is strict-JSON-compliant.

    `paired_stats.json` can contain real NaN statistics (e.g. a paired t-test is
    undefined when a metric has zero within-subject variance) -- an honest
    real result, not a bug, but Python's `json` module writes literal `NaN`
    (not standard JSON), which downstream strict encoders (e.g. FastAPI's
    response renderer) reject. `None` is the correct strict-JSON representation
    of "undefined here", not a fabricated substitute value.
    """
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nan(v) for v in obj]
    return obj


def _load_graph_structure(graph_dir: Path, subject: str, condition: str) -> dict[str, Any] | None:
    path = graph_dir / f"{subject}_{condition}_graph_structure.npz"
    if not path.is_file():
        return None
    with np.load(path) as d:
        centroids = d["centroids"]
        conn = d["connectivity"]
    edges = []
    n = conn.shape[0]
    for i in range(n):
        for j in range(i + 1, n):
            w = float(conn[i, j])
            if abs(w) >= CONNECTIVITY_EDGE_THRESHOLD:
                edges.append({"source": i, "target": j, "weight": _round(w, 4)})
    return {
        "centroids": [[_round(c) for c in row] for row in centroids.tolist()],
        "edges": edges,
        "n_regions": n,
        "n_edges_shown": len(edges),
        "edge_threshold": CONNECTIVITY_EDGE_THRESHOLD,
    }


def build_payload(cohort_dir: Path) -> dict[str, Any]:
    cohort_result = json.loads((cohort_dir / "cohort_result.json").read_text())
    paired_stats_path = cohort_dir / "paired_stats.json"
    paired_stats = json.loads(paired_stats_path.read_text()) if paired_stats_path.is_file() else None
    graph_dir = cohort_dir / "graph_structure"

    subjects_out = []
    for subject, conds in sorted(cohort_result.items()):
        entry: dict[str, Any] = {"id": subject, "conditions": {}}
        for cond in ("drug", "placebo"):
            scalars = conds.get(cond, {})
            struct = _load_graph_structure(graph_dir, subject, cond)
            entry["conditions"][cond] = {"scalars": scalars, "graph": struct}
        subjects_out.append(entry)

    n_with_graph = sum(
        1 for s in subjects_out
        if s["conditions"]["drug"]["graph"] is not None and s["conditions"]["placebo"]["graph"] is not None
    )

    return _sanitize_nan({
        "dataset": "ds005917",
        "n_subjects": len(subjects_out),
        "n_subjects_with_graph_structure": n_with_graph,
        "subjects": subjects_out,
        "paired_stats": paired_stats,
        "edge_threshold": CONNECTIVITY_EDGE_THRESHOLD,
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort-dir", default="outputs/dual_engine/ds005917")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    payload = build_payload(Path(args.cohort_dir))
    out_path = Path(args.out)
    out_path.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes); "
          f"{payload['n_subjects']} subjects, {payload['n_subjects_with_graph_structure']} with graph structure")


if __name__ == "__main__":
    main()
