"""Single deterministic entrypoint for the exploratory PITNN pipeline."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np

from runs.run_record import RunRecordV1, build_run_id
from sim.pitnn.bayesian_falsification import compare_models
from sim.pitnn.mumax3_macro_tda import invert_macro_signal, load_signal, synthetic_signal
from sim.pitnn.microtubule_3d import MicrotubuleLattice, MicrotubuleLatticeConfig, mock_trp_centroids
from sim.pitnn.tryptophan_lindblad import LindbladConfig, TryptophanLindbladModel
from sim.pitnn.non_markovian_bath import DrudeLorentzBath, blp_measure
from sim.pitnn.hodgkin_huxley_ciss import FHNConfig, ciss_torque, cytosolic_field, simulate_fhn, stark_shift
from sim.pitnn.exceptional_points import EPScanConfig, scan_exceptional_points
from sim.pitnn.exceptional_points_fast import optimize_exceptional_point
from sim.pitnn.ingest_empirical import empirical_to_macro_signal, ingest_empirical
from sim.pitnn.quantum_trajectories import MCWFConfig, MCWFTrajectoryEngine
from sim.pitnn.spirit_gneb_well import GNEBConfig, calculate_gneb_well
from sim.pitnn.state_exporter import PITNNStateExporter
from sim.pitnn.vampire_os_llg import LLGConfig, simulate_os_llg

try:
    from sim.pitnn.visualization import PITNNVisualizer
    HAS_VISUALIZATION = True
except ImportError:
    HAS_VISUALIZATION = False


def run_advanced_biophysics(*, output_dir: str | Path, seed: int = 0, n_layers: int = 4,
                            lindblad_steps: int = 12, ep_grid_size: int = 21,
                            mcwf_trajectories: int = 0, fast_ep: bool = False) -> tuple[dict, dict]:
    """Run deterministic 3D/excitonic/bath/electrophysiology/EP diagnostics."""
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    advanced = out / "advanced"; advanced.mkdir(parents=True, exist_ok=True)
    lattice = MicrotubuleLattice(MicrotubuleLatticeConfig(n_layers=n_layers))
    trp = mock_trp_centroids(8)
    dipoles = np.tile(np.array([1.0e-29, 0.0, 0.0]), (len(trp), 1))
    model = TryptophanLindbladModel(trp, dipoles, LindbladConfig())
    rho0 = np.zeros((len(trp), len(trp)), complex); rho0[0, 0] = 1.0
    times = np.linspace(0.0, 2e-13, lindblad_steps)
    rho_history = model.propagate(rho0, times)
    dark = model.identify_subradiant_states()
    bath = DrudeLorentzBath(); noise = bath.colored_noise(128, 1e-15, channels=3, seed=seed)
    distances = np.exp(-times / max(times[-1], 1e-30)); blp = blp_measure(distances, times)
    membrane_t, voltage, _ = simulate_fhn(FHNConfig())
    field = cytosolic_field(voltage)
    shifts = stark_shift(np.tile(np.array([1e-29, 0.0, 0.0]), (len(field), 1)), field)
    torque = ciss_torque(1.0, 1e-7, field)
    grid = np.linspace(0.0, 4.0, ep_grid_size)
    ep = scan_exceptional_points(EPScanConfig(grid, grid, coupling_s=1.0, epsilon_threshold=0.1))
    mcwf = None
    if mcwf_trajectories > 0:
        engine = MCWFTrajectoryEngine(model.hamiltonian, np.diag(model.gamma_rad))
        mcwf = engine.evolve(np.eye(len(trp), dtype=complex)[0], times,
                             MCWFConfig(trajectories=mcwf_trajectories, seed=seed, store_density=False))
    optimized_ep = optimize_exceptional_point() if fast_ep else None
    exporter = PITNNStateExporter(advanced / "artifacts")
    density_path = exporter.export_array_bundle("lindblad_density.npz", {"rho_history": rho_history, "times_s": times}, {"units": "SI", "seed": seed})
    field_path = exporter.export_array_bundle("field_coupling.npz", {"times_s": membrane_t, "voltage_V": voltage, "electric_field_Vm": field, "stark_shift_J": shifts, "ciss_torque": torque}, {"units": "SI"})
    ep_path = exporter.export_array_bundle("ep_scan.npz", {"spectra": ep["spectra"], "gaps": ep["gaps"], "fidelities": ep["fidelities"]}, {"pump_values": ep["pump_values"], "loss_values": ep["loss_values"]})

    if HAS_VISUALIZATION:
        visualizer = PITNNVisualizer(advanced / "artifacts" / "plots")
        ep_plot = visualizer.plot_ep_scan(ep["gaps"], np.asarray(ep["pump_values"]), np.asarray(ep["loss_values"]))
    else:
        ep_plot = str(advanced / "artifacts" / "plots" / "ep_scan.png")
    summary = {"lattice": {"n_sites": lattice.n_sites, "n_edges": len(lattice.edges), "n_trp": len(trp)},
               "lindblad": {"trace_final": float(np.trace(rho_history[-1]).real), "dark_states": dark["subradiant_indices"]},
               "bath": {"blp_measure": blp, "noise_shape": list(noise.shape)},
               "field_coupling": {"peak_field_Vm": float(np.max(np.linalg.norm(field, axis=1))), "peak_torque": float(np.max(torque))},
               "exceptional_points": {"best": ep["best"], "candidate_count": len(ep["candidates"]), "curvature_proxy": ep["curvature_proxy"]}}
    if mcwf is not None:
        summary["mcwf"] = {"trajectories": mcwf["trajectories"], "final_survival": float(mcwf["survival_probability"][-1])}
    if optimized_ep is not None:
        summary["exceptional_points"]["optimized"] = optimized_ep
    summary_path = exporter.export_json("advanced_summary.json", summary)
    def rel(path: str) -> str: return Path(path).relative_to(out).as_posix()
    return summary, {"lindblad_density": rel(density_path), "field_coupling": rel(field_path), "ep_scan": rel(ep_path), "ep_plot": rel(ep_plot), "advanced_summary": rel(summary_path)}


def run_pipeline(*, output_dir: str | Path = "results/pitnn", input_path: str | Path | None = None,
                 seed: int = 0, n_samples: int = 256, n_spins: int = 32, steps: int = 500,
                 advanced_biophysics: bool = False, empirical: bool = False,
                 sample_rate_hz: float | None = None, fast_backend: bool = False,
                 fast_tda: bool = False, mcwf_trajectories: int = 0, fast_ep: bool = False) -> dict:
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    if input_path is None:
        signal = synthetic_signal(n_samples, seed); data_mode = "synthetic_demo"
    elif empirical:
        empirical_signal = ingest_empirical(input_path, sample_rate_hz=sample_rate_hz)
        signal = empirical_to_macro_signal(empirical_signal); data_mode = "empirical_local"
    else:
        signal, data_mode = load_signal(input_path)
    if fast_tda:
        from sim.pitnn.mumax3_macro_tda import invert_macro_signal_accelerated
        inversion = invert_macro_signal_accelerated(signal)
    else:
        inversion = invert_macro_signal(signal)
    llg = simulate_os_llg(LLGConfig(n_spins=n_spins, steps=steps, ciss_torque=0.02 + inversion["ciss_spin_orbit_strength"]), record_states=True, backend="fast" if fast_backend else "numpy")
    gneb = calculate_gneb_well(GNEBConfig(defect_charge=max(1, inversion["beta_1"]), metabolic_scale_W=1e-12 * (1 + inversion["gamma_pump_hz"] / 100.0)))
    bayes = compare_models(signal, inversion)
    llg_metrics = {k: v for k, v in llg.items() if k not in {"trace_magnetization", "spins_history", "time_stamps"}}
    metrics = {"inversion": inversion, "llg": llg_metrics, "gneb": {k: v for k, v in gneb.items() if k != "energy_path_J"}, "bayesian": bayes}
    inputs = {"seed": seed, "n_samples": int(signal.size), "n_spins": n_spins, "steps": steps, "data_mode": data_mode}
    run_id = build_run_id("pitnn", "NeuroTopology-Sim", "working-tree", ["run_pitnn.py"], inputs, {"bayes_factor": bayes["bayes_factor"]})
    exporter = PITNNStateExporter(out / "artifacts")
    artifact_metadata = {"run_id": run_id, "data_mode": data_mode, "n_spins": n_spins, "steps": steps}
    trajectory_path = exporter.export_npz("spinor_trajectory.npz", llg["spins_history"], llg["time_stamps"], metadata=artifact_metadata)
    trace_path = exporter.export_json("topological_trace.json", {"run_id": run_id, "trace": llg["topology_trace"]})

    if HAS_VISUALIZATION:
        visualizer = PITNNVisualizer(out / "artifacts" / "plots")
        plot_trace = visualizer.plot_topological_trace(llg["time_stamps"], llg["topology_trace"])
        plot_heatmap = visualizer.plot_spinor_field_heatmap(llg["spins_history"])
        plot_s2 = visualizer.plot_s2_phase_space(llg["spins_history"][-1])
    else:
        plot_trace = str(out / "artifacts" / "plots" / "topological_trace.png")
        plot_heatmap = str(out / "artifacts" / "plots" / "spinor_field_heatmap.png")
        plot_s2 = str(out / "artifacts" / "plots" / "s2_phase_space.png")
    def relative_artifact(path: str) -> str:
        return Path(path).relative_to(out).as_posix()

    artifacts = {"spinor_trajectory": relative_artifact(trajectory_path),
                 "topological_trace": relative_artifact(trace_path),
                 "topological_plot": relative_artifact(plot_trace),
                 "field_heatmap": relative_artifact(plot_heatmap),
                 "s2_phase_space": relative_artifact(plot_s2)}
    advanced_metrics = None
    if advanced_biophysics:
        advanced_metrics, advanced_artifacts = run_advanced_biophysics(output_dir=out, seed=seed,
                                                                         mcwf_trajectories=mcwf_trajectories,
                                                                         fast_ep=fast_ep)
        artifacts.update(advanced_artifacts)
        metrics["advanced_biophysics"] = advanced_metrics
    record = RunRecordV1.make(run_id, "pitnn", claim_type="C", layer="speculative", data_mode=data_mode,
                              dataset_id="synthetic" if data_mode == "synthetic_demo" else "user_input",
                              verdict=bayes["verdict"], metrics=metrics, source="run_pitnn.py")
    record.input = inputs; record.notes = "Exploratory model outputs; no biological or physical proof is asserted."
    payload = {"run_id": run_id, "data_mode": data_mode, "metrics": metrics, "verdict": bayes["verdict"], "input": inputs, "artifacts": artifacts}
    (out / "pitnn_results.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    record.artifacts = artifacts
    record.write_json(out / "RunRecord.json")
    np.savetxt(out / "signal.csv", signal, delimiter=",")
    (out / "verdict.log").write_text(f"verdict={bayes['verdict']}\nbayes_factor={bayes['bayes_factor']:.8g}\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=None, help="optional CSV/NPY signal; omitted uses deterministic synthetic data")
    parser.add_argument("--output-dir", type=Path, default=Path("results/pitnn"))
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--n-samples", type=int, default=256)
    parser.add_argument("--n-spins", type=int, default=32)
    parser.add_argument("--steps", type=int, default=500)
    parser.add_argument("--advanced-biophysics", action="store_true", help="run opt-in offline frontier modules")
    parser.add_argument("--empirical", action="store_true", help="ingest a local CSV/NPY/FIF/EDF through Hilbert phase extraction")
    parser.add_argument("--sample-rate-hz", type=float, default=None)
    parser.add_argument("--fast-backend", action="store_true", help="use preallocated local LLG kernel")
    parser.add_argument("--fast-tda", action="store_true", help="add bounded sparse TDA proxy")
    parser.add_argument("--mcwf-trajectories", type=int, default=0, help="stream MCWF trajectories in advanced mode")
    parser.add_argument("--fast-ep", action="store_true", help="add optimizer-refined EP diagnostic in advanced mode")
    args = parser.parse_args(argv)
    result = run_pipeline(output_dir=args.output_dir, input_path=args.input, seed=args.seed,
                          n_samples=args.n_samples, n_spins=args.n_spins, steps=args.steps,
                          advanced_biophysics=args.advanced_biophysics, empirical=args.empirical,
                          sample_rate_hz=args.sample_rate_hz, fast_backend=args.fast_backend,
                          fast_tda=args.fast_tda, mcwf_trajectories=args.mcwf_trajectories,
                          fast_ep=args.fast_ep)
    print(json.dumps({"run_id": result["run_id"], "data_mode": result["data_mode"], "verdict": result["verdict"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
