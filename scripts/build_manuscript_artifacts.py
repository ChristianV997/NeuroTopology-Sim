"""Build offline, publication-ready PITNN manuscript assets from local artifacts."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path: sys.path.insert(0, str(_ROOT))
from sim.pitnn.exceptional_points_fast import FullSpectrumEPConfig, full_spectrum_diagnostics
from sim.pitnn.microtubule_3d import MicrotubuleLattice, MicrotubuleLatticeConfig
from sim.pitnn.tryptophan_lindblad import LindbladConfig


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}

def _tex_num(value: Any) -> str:
    try: return f"{float(value):.3g}"
    except (TypeError, ValueError): return "n/a"

def build_manuscript_artifacts(artifact_root: str | Path = "artifacts/pitnn", output_dir: str | Path = "artifacts/manuscript") -> dict[str, str]:
    """Generate a LaTeX table and three vector-PDF figures offline."""
    root, out = Path(artifact_root), Path(output_dir)
    figures = out / "figures"; figures.mkdir(parents=True, exist_ok=True)
    insights = _read(root / "research_campaign" / "research_insights_summary.json")
    report = _read(root / "dsim_export" / "empirical_falsification_report.json") or _read(root / "empirical_smoke" / "empirical_falsification_report.json")
    comparison = report.get("comparison", {})
    ep = insights.get("ep_boundary", {})
    cfg, lattice_cfg = LindbladConfig(), MicrotubuleLatticeConfig()
    table = out / "table_parameters.tex"
    table.write_text("""%% Generated offline by NeuroTopology-Sim; computational model parameters only.
\\begin{tabular}{lll}
\\hline
Parameter & Value & Unit \\\\
\\hline
Phonon reorganization energy $\\lambda$ & %s & eV \\\\
Phonon cutoff $\\omega_c$ & %s & s$^{-1}$ \\\\
Phonon dephasing rate & %s & s$^{-1}$ \\\\
DMI/exchange ratio $D/J_\\perp$ & %s & model units \\\\
CISS torque grid maximum & $10^{-1}$ & model units \\\\
EP $\\gamma_{\\rm pump}$ & %s & s$^{-1}$ \\\\
EP $\\Gamma_{\\rm loss}$ & %s & s$^{-1}$ \\\\
PITNN AICc & %s & -- \\\\
Wilson--Cowan AICc & %s & -- \\\\
$\\Delta$AICc & %s & -- \\\\
Bayes factor $K$ & %s & -- \\\\
Verdict & %s & -- \\\\
\\hline
\\end{tabular}
""" % (_tex_num(cfg.phonon_reorganization_eV), _tex_num(cfg.phonon_cutoff_s), _tex_num(cfg.phonon_rate_s), _tex_num(lattice_cfg.dmi_strength/lattice_cfg.j_perpendicular), _tex_num(ep.get("pump_s")), _tex_num(ep.get("loss_s")), _tex_num(comparison.get("pitnn",{}).get("aicc")), _tex_num(comparison.get("classical_wilson_cowan",{}).get("aicc")), _tex_num(report.get("delta_aicc")), _tex_num(report.get("bayes_factor")), str(report.get("verdict","NOT_SUPPORTED"))), encoding="utf-8")
    lattice = MicrotubuleLattice(MicrotubuleLatticeConfig(n_layers=8, periodic_z=True))
    fig = plt.figure(figsize=(7,6)); ax = fig.add_subplot(projection="3d")
    p = lattice.positions * 1e9; ax.scatter(p[:,0],p[:,1],p[:,2],s=8,c=lattice.layer,cmap="viridis")
    for edge, kind in zip(lattice.edges, lattice.edge_kind):
        if kind == "parallel": ax.plot(p[edge,0],p[edge,1],p[edge,2],color="black",alpha=.25,lw=.5)
    ax.set(xlabel="x (nm)",ylabel="y (nm)",zlabel="z (nm)",title="Periodic 13-protofilament microtubule lattice")
    fig.tight_layout(); fig.savefig(figures/"fig1_microtubule_pbc_lattice.pdf"); plt.close(fig)
    config = FullSpectrumEPConfig(n_sites=8)
    pumps, losses = np.linspace(0,4,81), np.linspace(0,4,81)
    gaps = np.empty((len(pumps),len(losses)))
    for i,pump in enumerate(pumps):
        for j,loss in enumerate(losses): gaps[i,j] = full_spectrum_diagnostics(float(pump),float(loss),config)["global_gap"]
    fig,ax=plt.subplots(figsize=(7,5)); image=ax.imshow(np.log10(np.maximum(gaps,1e-15)).T,origin="lower",extent=[pumps[0],pumps[-1],losses[0],losses[-1]],aspect="auto",cmap="magma")
    fig.colorbar(image,ax=ax,label="log10 global spectral gap"); ax.set(xlabel="gamma_pump (s^-1)",ylabel="Gamma_loss (s^-1)",title="Full-spectrum non-Hermitian gap diagnostic")
    fig.tight_layout(); fig.savefig(figures/"fig2_liouvillian_gap_spectrum.pdf"); plt.close(fig)
    fig,ax=plt.subplots(figsize=(7,4.5)); plotted=False
    for label, state in report.get("conditions",{}).items():
        rg=state.get("rg",{}); trace=rg.get("topology_trace",[])
        if trace: ax.plot([entry["beta1_loops"] for entry in trace],label=f"{label} beta1"); plotted=True
    if not plotted:
        for label,state in report.get("conditions",{}).items(): ax.axhline(state.get("topology",{}).get("mean_beta_1",0),label=f"{label} mean beta1")
    ax.set(xlabel="RG coarse-grained frame",ylabel="beta1 proxy",title="RG coarse-grained topological dynamics")
    if plotted: ax.legend()
    ax.grid(alpha=.3); fig.tight_layout(); fig.savefig(figures/"fig3_rg_topological_hysteresis.pdf"); plt.close(fig)
    return {"table":str(table),"fig1":str(figures/"fig1_microtubule_pbc_lattice.pdf"),"fig2":str(figures/"fig2_liouvillian_gap_spectrum.pdf"),"fig3":str(figures/"fig3_rg_topological_hysteresis.pdf")}

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--artifact-root",type=Path,default=Path("artifacts/pitnn")); parser.add_argument("--output-dir",type=Path,default=Path("artifacts/manuscript")); args=parser.parse_args()
    print(json.dumps(build_manuscript_artifacts(args.artifact_root,args.output_dir),sort_keys=True)); return 0
if __name__ == "__main__": raise SystemExit(main())
