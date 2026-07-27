"""Deterministic temperature/pump sweep of the finite Lindblad lattice."""
from __future__ import annotations
import argparse,csv,json,os,sys,tempfile,time
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from physics.open_quantum import LatticeConfig,ThermalBathConfig,LindbladLattice,dense_gap,matrix_free_gap,parse_trp_centroids
from physics.open_quantum.lindblad_lattice import DEBYE

def _json_safe(value:object)->object:
    """Convert non-finite numerical diagnostics to JSON null without altering calculations."""
    if isinstance(value,float) and not np.isfinite(value): return None
    if isinstance(value,dict): return {str(k):_json_safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)): return [_json_safe(v) for v in value]
    return value

def atomic_json(path:Path,payload:dict)->None:
    fd,tmp=tempfile.mkstemp(prefix=path.stem+"_",suffix=".tmp",dir=path.parent); os.close(fd)
    try: Path(tmp).write_text(json.dumps(_json_safe(payload),indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8"); os.replace(tmp,path)
    finally:
        if Path(tmp).exists(): Path(tmp).unlink()
def build_model(args:argparse.Namespace,temperature:float,pump_rate:float)->tuple[LindbladLattice,str]:
    bath=ThermalBathConfig.from_temperature(temperature,args.transition_energy_eV,thermal_relaxation_s=args.thermal_relaxation_s,dephasing_rate_s=args.dephasing_reference_s*temperature/args.reference_temperature_K,radiative_rate_s=args.radiative_rate_s,ciss_dephasing_rate_s=args.ciss_dephasing_s,metabolic_pump_rate_s=pump_rate,pump_sites=tuple(args.pump_sites))
    cfg=LatticeConfig(n_layers=args.n_layers,radius_m=args.radius_nm*1e-9,axial_spacing_m=args.axial_spacing_nm*1e-9,dielectric_constant=args.dielectric_constant,transition_energy_eV=args.transition_energy_eV,dipole_debye=args.dipole_debye,interaction_cutoff_m=args.cutoff_nm*1e-9,bath=bath)
    if args.pdb and args.pdb.is_file():
        centroids=parse_trp_centroids(args.pdb); radial=centroids.copy(); radial[:,2]=0; radial/=np.maximum(np.linalg.norm(radial,axis=1,keepdims=True),np.finfo(float).eps); return LindbladLattice(centroids,args.dipole_debye*DEBYE*radial,cfg),"local_pdb"
    if args.pdb or args.pdb_synthetic_disorder:
        base=LindbladLattice.from_pbc(cfg); rng=np.random.default_rng(args.structural_seed); positions=base.positions+rng.normal(0.,args.structural_disorder_nm*1e-9,base.positions.shape); radial=positions.copy(); radial[:,2]=0; radial/=np.maximum(np.linalg.norm(radial,axis=1,keepdims=True),np.finfo(float).eps); return LindbladLattice(positions,args.dipole_debye*DEBYE*radial,cfg),"pdb_synthetic_disorder"
    return LindbladLattice.from_pbc(cfg),"algorithmic_pbc_demo"
def run_sweep(args:argparse.Namespace)->dict:
    out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True); records=[]; source=""; pump_rates=args.pump_rates if args.pump_rates is not None else [args.pump_rate]
    for pump_rate in pump_rates:
        for temperature in args.temperatures:
            start=time.perf_counter(); model,source=build_model(args,float(temperature),float(pump_rate)); use_dense=not args.force_matrix_free and model.dimension<=args.dense_max_dimension; result=dense_gap(model,max_dimension=args.dense_max_dimension) if use_dense else matrix_free_gap(model,k=args.krylov_k,maxiter=args.maxiter); bath=model.config.bath; status="GAP_ZERO" if result.gap_zero else ("CONVERGED" if result.converged else "FAILED"); ratio=bath.thermal_excitation_s/bath.thermal_relaxation_s if bath.thermal_relaxation_s else 0.
            records.append({"temperature_K":float(temperature),"metabolic_pump_rate_s":float(pump_rate),"pump_sites":list(bath.pump_sites),"dimension":model.dimension,"liouvillian_dimension":model.dimension**2,"gap_s":result.gap_s,"decoherence_time_s":result.decoherence_time_s,"subradiant_gap_s":result.subradiant_gap_s,"superradiant_gap_s":result.superradiant_gap_s,"tau_subradiant_s":result.tau_subradiant_s,"tau_superradiant_s":result.tau_superradiant_s,"chiral_current_s":result.chiral_current_s,"exhibits_chiral_current":result.exhibits_chiral_current,"method":result.method,"status":status,"gap_zero":result.gap_zero,"converged":result.converged,"iteration_count":result.iteration_count,"stationary_residual_s":result.stationary_residual_s,"trace_preservation_residual_s":result.trace_preservation_residual_s,"hermiticity_residual":result.hermiticity_residual,"thermal_relaxation_s":bath.thermal_relaxation_s,"thermal_excitation_s":bath.thermal_excitation_s,"detailed_balance_ratio":ratio,"dephasing_rate_s":bath.dephasing_rate_s,"ciss_dephasing_rate_s":bath.ciss_dephasing_rate_s,"elapsed_s":time.perf_counter()-start,"reference_ratio":result.decoherence_time_s/args.reference_tau_s if np.isfinite(result.decoherence_time_s) else None})
    config={k:(str(v) if isinstance(v,Path) else v) for k,v in vars(args).items()}; payload={"schema":"ScienceR-Dsim.OpenQuantumDecoherenceSweep.v2","source":source,"temperatures_K":[float(x) for x in args.temperatures],"configuration":config,"records":records,"scientific_note":"Finite-dimensional model. Metabolic pumping and CISS are phenomenological; chiral-current detection is a steady-state current heuristic, not biological evidence; reference_tau_s is comparison-only."}; atomic_json(out/"decoherence_sweep.json",payload)
    with (out/"decoherence_sweep.csv").open("w",newline="",encoding="utf-8") as handle: writer=csv.DictWriter(handle,fieldnames=list(records[0])); writer.writeheader(); writer.writerows(records)
    fig,ax=plt.subplots(figsize=(9,5))
    for pump_rate in pump_rates:
        subset=[r for r in records if r["metabolic_pump_rate_s"]==pump_rate and np.isfinite(r["decoherence_time_s"]) and r["decoherence_time_s"]>0]
        if subset:
            ax.semilogy([r["temperature_K"] for r in subset],[r["decoherence_time_s"] for r in subset],"o-",label=f"tau_dec pump={pump_rate:.2g}")
            ax.semilogy([r["temperature_K"] for r in subset],[r["tau_subradiant_s"] for r in subset],"x--",label=f"tau_sub pump={pump_rate:.2g}")
    if args.reference_tau_s>0: ax.axhline(args.reference_tau_s,color="red",linestyle=":",label="comparison reference")
    ax.set(xlabel="Temperature (K)",ylabel="Time (s)",title="Finite Lindblad decoherence and subradiant lifetimes"); ax.grid(True,which="both",alpha=.3); ax.legend(); fig.tight_layout(); fig.savefig(out/"decoherence_sweep.png",dpi=200); plt.close(fig); return payload
def make_parser()->argparse.ArgumentParser:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--temperatures",nargs="+",type=float,default=np.linspace(10,310,16).tolist()); p.add_argument("--n-layers",type=int,default=1); p.add_argument("--radius-nm",type=float,default=12); p.add_argument("--axial-spacing-nm",type=float,default=.923); p.add_argument("--dielectric-constant",type=float,default=7); p.add_argument("--dipole-debye",type=float,default=2.1); p.add_argument("--cutoff-nm",type=float,default=8); p.add_argument("--transition-energy-eV",type=float,default=4.43); p.add_argument("--thermal-relaxation-s",type=float,default=1e9); p.add_argument("--dephasing-reference-s",type=float,default=1e9); p.add_argument("--radiative-rate-s",type=float,default=.1e9); p.add_argument("--ciss-dephasing-s",type=float,default=0); p.add_argument("--pump-rate",type=float,default=0,help="localized phenomenological excitation rate in s^-1"); p.add_argument("--pump-rates",nargs="+",type=float,default=None,help="optional pump-rate sweep overriding --pump-rate"); p.add_argument("--pump-sites",nargs="+",type=int,default=[0]); p.add_argument("--reference-temperature-K",type=float,default=310); p.add_argument("--reference-tau-s",type=float,default=1e-13); p.add_argument("--dense-max-dimension",type=int,default=32); p.add_argument("--force-matrix-free",action="store_true"); p.add_argument("--krylov-k",type=int,default=6); p.add_argument("--maxiter",type=int,default=2000); p.add_argument("--pdb",type=Path); p.add_argument("--pdb-synthetic-disorder",action="store_true"); p.add_argument("--structural-disorder-nm",type=float,default=.15); p.add_argument("--structural-seed",type=int,default=20260725); p.add_argument("--output-dir",type=Path,default=Path("artifacts/open_quantum/decoherence_sweep")); return p
def main()->int: print(json.dumps({"records":len(run_sweep(make_parser().parse_args())["records"])})); return 0
if __name__=="__main__": raise SystemExit(main())
