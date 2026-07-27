"""Aggregate campaign JSONL/NPZ artifacts into reproducible summaries."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load_records(directory: Path) -> list[dict[str, Any]]:
    path = directory / "campaign_records.jsonl"
    if not path.is_file():
        raise FileNotFoundError(path)
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not records:
        raise ValueError("campaign_records.jsonl is empty")
    return records


def analyze_campaign(input_dir: str | Path = "artifacts/pitnn/research_campaign",
                     output_dir: str | Path | None = None) -> dict[str, Any]:
    """Create matrix, correlations, phase plots, and an insight report."""
    source = Path(input_dir); destination = Path(output_dir) if output_dir else source
    destination.mkdir(parents=True, exist_ok=True)
    records = _load_records(source)
    arrays_path = source / "campaign_arrays.npz"
    with np.load(arrays_path, allow_pickle=False) as arrays:
        spin_final = np.asarray(arrays["spin_final"])
        density_final = np.asarray(arrays["density_final"])
    if spin_final.shape[0] != len(records) or density_final.shape[0] != len(records):
        raise ValueError("campaign arrays and records have different node counts")
    np.savez_compressed(destination / "full_campaign_matrix.npz", spin_final=spin_final,
                        density_final=density_final)
    tau = np.asarray([r["parameters"]["tau0"] for r in records], float)
    pump = np.asarray([r["parameters"]["gamma_pump_s"] for r in records], float)
    temp = np.asarray([r["parameters"]["temperature_K"] for r in records], float)
    q = np.asarray([r["spin"]["topological_charge"] for r in records], float)
    winding = np.asarray([r["spin"]["winding_number"] for r in records], float)
    beta = np.asarray([r["spin"]["beta1_loops"] for r in records], float)
    blp = np.asarray([r["bath"]["blp_non_markovianity"] for r in records], float)
    lifetime = np.asarray([r["quantum"]["lifetime_enhancement"] for r in records], float)
    matrix = np.column_stack((tau, pump, temp, q, winding, beta, blp, lifetime))
    corr = np.corrcoef(matrix, rowvar=False)
    names = ["tau0", "gamma_pump_s", "temperature_K", "Q", "W", "beta1", "BLP_N", "F_sub"]
    finite_corr = np.nan_to_num(corr, nan=0.0, posinf=0.0, neginf=0.0)
    best_lifetime = int(np.argmax(np.nan_to_num(lifetime, nan=-np.inf)))
    physiological = np.where(temp == 310.0)[0]
    max_blp_index = int(physiological[np.argmax(blp[physiological])]) if physiological.size else int(np.argmax(blp))
    critical = None
    stable = np.where((temp == 310.0) & (tau > 0) & (np.abs(q) <= np.percentile(np.abs(q), 75)))[0]
    if stable.size:
        critical = float(np.min(pump[stable]))
    # Phase diagram: median absolute Q over tau and temperature.
    fig, ax = plt.subplots(figsize=(7, 5))
    for temperature in sorted(set(temp)):
        points = np.where(temp == temperature)[0]
        order = np.argsort(tau[points])
        ax.plot(tau[points][order], np.abs(q[points][order]), marker="o", label=f"{temperature:.0f} K")
    ax.set_xlabel("CISS torque $\\tau_0$"); ax.set_ylabel("$|Q|$"); ax.set_title("CISS vs temperature")
    ax.grid(alpha=.3); ax.legend(); fig.tight_layout(); fig.savefig(destination / "phase_diagram_ciss_vs_temperature.png", dpi=180); plt.close(fig)
    # EP map from node-level scalar values.
    ep_gap = np.asarray([r["ep"]["gap"] for r in records], float)
    ep_fidelity = np.asarray([r["ep"]["fidelity"] for r in records], float)
    fig, ax = plt.subplots(figsize=(7, 5)); scatter = ax.scatter(pump, temp, c=np.log10(np.maximum(ep_gap, 1e-300)), cmap="viridis")
    fig.colorbar(scatter, ax=ax, label="$\\log_{10}$ EP gap"); ax.set_xlabel("pump $s^{-1}$"); ax.set_ylabel("temperature K")
    ax.set_title("EP parameter-space map"); fig.tight_layout(); fig.savefig(destination / "ep_parameter_space_map.png", dpi=180); plt.close(fig)
    # Lifetime scaling from the available fixed 8-site network; report per node.
    fig, ax = plt.subplots(figsize=(7, 5)); ax.plot(np.arange(1, len(lifetime) + 1), lifetime, ".", alpha=.7)
    ax.set_xlabel("campaign node"); ax.set_ylabel("$\\mathcal{F}_{sub}$"); ax.set_title("Subradiant lifetime scaling")
    ax.grid(alpha=.3); fig.tight_layout(); fig.savefig(destination / "subradiant_lifetime_scaling.png", dpi=180); plt.close(fig)
    report = {
        "schema": "PITNN.ResearchInsights.v1", "n_nodes": len(records),
        "correlation_order": names, "correlation_matrix": finite_corr.tolist(),
        "optimal_lifetime": {"index": best_lifetime, "parameters": records[best_lifetime]["parameters"], "F_sub": float(lifetime[best_lifetime])},
        "ep_boundary": records[best_lifetime]["ep"],
        "maximum_physiological_blp": {"index": max_blp_index, "value": float(blp[max_blp_index]), "parameters": records[max_blp_index]["parameters"]},
        "critical_pumping_rate_heuristic_s": critical,
        "scientific_note": "Critical rate is a descriptive grid heuristic, not a proof of decoherence suppression.",
        "artifacts": {"matrix": str(destination / "full_campaign_matrix.npz"),
                      "phase_diagram": str(destination / "phase_diagram_ciss_vs_temperature.png"),
                      "ep_map": str(destination / "ep_parameter_space_map.png"),
                      "lifetime_plot": str(destination / "subradiant_lifetime_scaling.png")},
    }
    (destination / "research_insights_summary.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("artifacts/pitnn/research_campaign"))
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    report = analyze_campaign(args.input_dir, args.output_dir)
    print(json.dumps({"n_nodes": report["n_nodes"], "max_blp": report["maximum_physiological_blp"]["value"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
