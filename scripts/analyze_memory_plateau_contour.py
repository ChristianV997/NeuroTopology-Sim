"""Derive a paired, prespecified plateau contour from a dephasing/gain scan."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_summary(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["dephasing"]


def analyze(rows: list[dict], coherence_ratio_max: float = 0.70,
            population_ratio_max: float = 1.01) -> dict:
    candidates = [r for r in rows if r.get("control_type") == "candidate"]
    nulls = [r for r in rows if r.get("control_type") == "matched_null_zero_gain"]
    null_by_key = {(r["dephasing_ratio"], r["mu"]): r for r in nulls}
    paired = []
    for candidate in candidates:
        key = (candidate["dephasing_ratio"], candidate["mu"])
        if key not in null_by_key:
            continue
        null = null_by_key[key]
        population_ratio = candidate["integrated_population"] / null["integrated_population"]
        integrated_coherence_ratio = candidate["integrated_coherence"] / null["integrated_coherence"]
        endpoint_coherence_ratio = candidate["final_coherence"] / null["final_coherence"]
        paired.append({
            "mu": candidate["mu"],
            "dephasing_ratio": candidate["dephasing_ratio"],
            "g": candidate["g"],
            "integrated_coherence_ratio_to_null": integrated_coherence_ratio,
            "endpoint_coherence_ratio_to_null": endpoint_coherence_ratio,
            "population_ratio_to_null": population_ratio,
            "integrated_coherence_suppression": 1.0 - integrated_coherence_ratio,
            "endpoint_coherence_suppression": 1.0 - endpoint_coherence_ratio,
            "population_within_one_percent": 0.99 <= population_ratio <= population_ratio_max,
            "plateau": integrated_coherence_ratio <= coherence_ratio_max and 0.99 <= population_ratio <= population_ratio_max,
            "converged": True,
        })

    edge_by_dephasing = []
    for dephasing in sorted({r["dephasing_ratio"] for r in paired}):
        slice_rows = [r for r in paired if r["dephasing_ratio"] == dephasing]
        valid = [r for r in slice_rows if r["plateau"]]
        edge_by_dephasing.append({
            "mu": slice_rows[0]["mu"],
            "dephasing_ratio": dephasing,
            "max_g_in_plateau": max((r["g"] for r in valid), default=None),
            "plateau_count": len(valid),
            "integrated_coherence_ratio_min": min(r["integrated_coherence_ratio_to_null"] for r in slice_rows),
            "integrated_coherence_ratio_max": max(r["integrated_coherence_ratio_to_null"] for r in slice_rows),
            "endpoint_coherence_ratio_min": min(r["endpoint_coherence_ratio_to_null"] for r in slice_rows),
            "endpoint_coherence_ratio_max": max(r["endpoint_coherence_ratio_to_null"] for r in slice_rows),
            "population_ratio_at_max_g": max(slice_rows, key=lambda r: r["g"])["population_ratio_to_null"],
        })

    return {
        "criterion": {
            "coherence_ratio_to_null_max": coherence_ratio_max,
            "population_ratio_to_null_range": [0.99, population_ratio_max],
            "definition": "At least 30% integrated-coherence suppression with integrated population within 1% of the matched g=0 null.",
        },
        "paired_count": len(paired),
        "plateau_count": sum(r["plateau"] for r in paired),
        "paired_rows": paired,
        "edge_by_dephasing": edge_by_dephasing,
        "interpretation": {
            "coherence_boundary_found": any(r["integrated_coherence_ratio_min"] > coherence_ratio_max for r in edge_by_dephasing),
            "endpoint_coherence_boundary_found": any(r["endpoint_coherence_ratio_min"] > coherence_ratio_max for r in edge_by_dephasing),
            "population_boundary_is_active": any(r["max_g_in_plateau"] is not None and r["max_g_in_plateau"] < max(x["g"] for x in paired) for r in edge_by_dephasing),
            "warning": "This contour is a dynamical-model boundary and is not evidence for a biological mechanism.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("summary", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(_load_summary(args.summary))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "plateau_contour.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    lines = [
        "# Paired Memory Plateau Contour",
        "",
        result["criterion"]["definition"],
        "",
        f"Paired rows: {result['paired_count']}; plateau rows: {result['plateau_count']}.",
        "",
        "| dephasing ratio | maximum g in plateau | plateau rows | integrated coherence ratio | endpoint coherence ratio | population ratio at largest g |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for row in result["edge_by_dephasing"]:
        max_g = "none" if row["max_g_in_plateau"] is None else f"{row['max_g_in_plateau']:.6g}"
        lines.append(
            f"| {row['dephasing_ratio']:.6g} | {max_g} | {row['plateau_count']} | "
            f"{row['integrated_coherence_ratio_min']:.4f} to {row['integrated_coherence_ratio_max']:.4f} | "
            f"{row['endpoint_coherence_ratio_min']:.4f} to {row['endpoint_coherence_ratio_max']:.4f} | "
            f"{row['population_ratio_at_max_g']:.5f} |"
        )
    lines += ["", result["interpretation"]["warning"], ""]
    (args.output_dir / "plateau_contour.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
