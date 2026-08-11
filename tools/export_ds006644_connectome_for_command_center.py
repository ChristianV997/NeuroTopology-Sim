"""
Consolidate ds006644's real per-subject graph structure (parcel centroids + real
Schaefer-2018 region names + connectivity matrix, from
`tools/stream_process_ds006644.py --save-graph-structure`) into one JSON artifact
for the /fmri-connectome 3D viewer's labeled-connectome layer.

Unlike ds005917 (raw BOLD, no spatial normalization -- see
`tools/stream_process_ds005917.py`'s docstring for why its parcels stay
anonymous), ds006644 uses fMRIPrep's AROMA-denoised, MNI152NLin6Asym-space
BOLD -- the same template family as the cached Schaefer-100 atlas -- so real
atlas region names are a valid, non-fabricated correspondence here. This
payload carries ONE real session (ses-02) per subject, not a two-condition
morph pair: ds006644's verum/placebo distinction is between-subject (fixed
per subject, from `participants.tsv`), unlike ds005917's within-subject
drug/placebo crossover.

Usage:
  python tools/export_ds006644_connectome_for_command_center.py \\
      --cohort-dir outputs/dual_engine/ds006644_labeled \\
      --out outputs/dual_engine/ds006644_labeled/fmri_connectome_labeled.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

CONNECTIVITY_EDGE_THRESHOLD = 0.3  # |corr| >= this to keep an edge in the exported graph


def _round(x: float, n: int = 5) -> float:
    return round(float(x), n)


def _load_graph_structure(graph_dir: Path, subject: str, group: str) -> dict[str, Any] | None:
    path = graph_dir / f"{subject}_{group}_graph_structure.npz"
    if not path.is_file():
        return None
    with np.load(path, allow_pickle=True) as d:
        centroids = d["centroids"]
        conn = d["connectivity"]
        labels = d["labels"].tolist() if d["labels"].size else None
    edges = []
    n = conn.shape[0]
    for i in range(n):
        for j in range(i + 1, n):
            w = float(conn[i, j])
            if abs(w) >= CONNECTIVITY_EDGE_THRESHOLD:
                edges.append({"source": i, "target": j, "weight": _round(w, 4)})
    return {
        "centroids": [[_round(c) for c in row] for row in centroids.tolist()],
        "labels": labels,
        "edges": edges,
        "n_regions": n,
        "n_edges_shown": len(edges),
        "edge_threshold": CONNECTIVITY_EDGE_THRESHOLD,
    }


def build_payload(cohort_dir: Path) -> dict[str, Any]:
    manifest = json.loads((cohort_dir / "manifest.json").read_text())
    graph_dir = cohort_dir / "graph_structure"

    subjects_out = []
    for subject, record in sorted(manifest.get("processed", {}).items()):
        if record.get("error"):
            continue
        group = record.get("group")
        graph = _load_graph_structure(graph_dir, subject, group)
        if graph is None or graph["labels"] is None:
            continue
        subjects_out.append({
            "id": subject,
            "group": group,
            "scalars": {
                "betti1": record.get("betti1"),
                "modularity": record.get("modularity"),
                "global_efficiency": record.get("global_efficiency"),
                "mean_degree": record.get("mean_degree"),
            },
            "graph": graph,
        })

    return {
        "dataset": "ds006644",
        "atlas": "Schaefer2018_100Parcels_7Networks",
        "session": "ses-02",
        "n_subjects": len(subjects_out),
        "subjects": subjects_out,
        "edge_threshold": CONNECTIVITY_EDGE_THRESHOLD,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort-dir", default="outputs/dual_engine/ds006644_labeled")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    payload = build_payload(Path(args.cohort_dir))
    out_path = Path(args.out)
    out_path.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes); {payload['n_subjects']} subjects with real region names")


if __name__ == "__main__":
    main()
