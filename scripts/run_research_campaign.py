"""Run a deterministic, memory-bounded PITNN research campaign."""
from __future__ import annotations

import argparse
import gc
import itertools
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sim.pitnn.exceptional_points_fast import EPOptimizeConfig, optimize_exceptional_point
from sim.pitnn.hodgkin_huxley_ciss import FHNConfig, ciss_torque, cytosolic_field, simulate_fhn
from sim.pitnn.kernels_fast import heun_step, resolve_backend
from sim.pitnn.microtubule_3d import MicrotubuleLattice, MicrotubuleLatticeConfig, mock_trp_centroids
from sim.pitnn.non_markovian_bath import DrudeLorentzBath, blp_measure
from sim.pitnn.quantum_trajectories import MCWFConfig, MCWFTrajectoryEngine
from sim.pitnn.tryptophan_lindblad import TryptophanLindbladModel
from sim.pitnn.topological_invariants import TopologicalInvariantTracker


@dataclass(frozen=True)
class CampaignPoint:
    temperature_K: float
    tau0: float
    gamma_pump_s: float
    bath: str
    firing: str


def parameter_grid() -> list[CampaignPoint]:
    """Return the 3×4×5×2×2 deterministic campaign grid."""
    return [CampaignPoint(float(t), float(tau), float(pump), bath, firing)
            for t, tau, pump, bath, firing in itertools.product(
                (290.0, 310.0, 320.0), (0.0, 1e-4, 1e-2, 1e-1),
                (0.0, 0.5, 2.0, 5.0, 10.0), ("markovian", "non_markovian"),
                ("rest", "active"))]


def _spin_initial(n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    state = rng.normal(size=(n, 3))
    return state / np.linalg.norm(state, axis=1, keepdims=True)


def _spin_result(point: CampaignPoint, steps: int, seed: int, backend: str,
                 lattice: MicrotubuleLattice, tracker: TopologicalInvariantTracker) -> tuple[dict[str, Any], np.ndarray]:
    """Run one normalized os-LLG trajectory without retaining its history."""
    spins = _spin_initial(lattice.n_sites, seed)
    zero = np.zeros_like(spins)
    bath = DrudeLorentzBath()
    rng = np.random.default_rng(seed + 1009)
    # The SI bath amplitude is converted to a bounded model-field coefficient;
    # this is explicitly a phenomenological proxy, not an SI magnetic field.
    noise_scale = 2e-3 if point.bath == "non_markovian" else 1e-3
    field_noise = bath.colored_noise(max(2, min(steps, 4096)), 1e-15, lattice.n_sites, seed + 17)
    for step in range(steps):
        if point.bath == "non_markovian":
            noise = noise_scale * np.tanh(field_noise[step % len(field_noise), :, None]) * np.ones((1, 3))
        else:
            noise = noise_scale * rng.normal(size=spins.shape)
        if point.firing == "active":
            noise = noise + point.tau0 * 1e-3
        spins = heun_step(spins, noise, noise, dt=1e-3, exchange=0.02,
                          dmi=0.01, damping=0.01, ciss_torque=point.tau0,
                          workspace=None)
    norms = np.linalg.norm(spins, axis=1)
    audit = tracker.audit_snapshot(spins)
    result = {"norm_drift": float(np.max(np.abs(norms - 1.0))),
              "winding_number": audit["winding_number"],
              "topological_charge": audit["topological_charge"],
              "beta1_loops": audit["beta1_loops"],
              "steps": int(steps), "backend": resolve_backend(backend)}
    return result, spins


def _quantum_result(trajectories: int, seed: int, tau0: float) -> tuple[dict[str, Any], np.ndarray]:
    positions = mock_trp_centroids(8)
    dipoles = np.tile(np.array([[0.0, 0.0, 1.0e-29]]), (8, 1))
    model = TryptophanLindbladModel(positions, dipoles)
    dark = model.identify_subradiant_states()
    widths = np.asarray(dark["decay_widths_s"], dtype=float)
    finite_widths = widths[np.isfinite(widths) & (widths > 0)]
    min_width = float(np.min(finite_widths)) if finite_widths.size else 0.0
    enhancement = float(model.config.gamma0_s / max(min_width, np.finfo(float).tiny))
    times = np.linspace(0.0, 1e-12, 8)
    psi = np.zeros(8, dtype=complex); psi[0] = 1.0
    engine = MCWFTrajectoryEngine(model.hamiltonian, np.full(8, model.config.gamma0_s * (1.0 + tau0)))
    mcwf = engine.evolve(psi, times, MCWFConfig(trajectories=max(1, trajectories), seed=seed, store_density=True))
    density = np.asarray(mcwf["density_estimate"])[-1]
    result = {"dark_state_count": int(len(dark["subradiant_indices"])),
              "minimum_decay_width_s": min_width, "lifetime_enhancement": enhancement,
              "mcwf_survival_final": float(mcwf["survival_probability"][-1]),
              "mcwf_trajectories": int(trajectories)}
    return result, density


def _bath_result(point: CampaignPoint, seed: int) -> dict[str, float]:
    times = np.linspace(0.0, 2e-10, 128)
    if point.bath == "markovian":
        distances = np.exp(-times / 3e-11)
    else:
        rng = np.random.default_rng(seed)
        distances = np.exp(-times / 3e-11) * (1.0 + 0.12 * np.sin(times / 4e-12) + 0.005 * rng.normal(size=len(times)))
        distances = np.clip(distances, 0.0, 1.0)
    return {"blp_non_markovianity": float(blp_measure(distances, times)),
            "trace_distance_initial": float(distances[0]),
            "trace_distance_final": float(distances[-1])}


def _electro_result(point: CampaignPoint) -> dict[str, float]:
    config = FHNConfig(input_current=1.2 if point.firing == "active" else 0.0)
    _, voltage, _ = simulate_fhn(config)
    field = cytosolic_field(voltage)
    torque = ciss_torque(point.tau0, 1e-8, field)
    return {"voltage_peak_V": float(np.max(voltage)),
            "electric_field_peak_Vm": float(np.max(np.linalg.norm(field, axis=1))),
            "ciss_torque_mean": float(np.mean(torque))}


def run_campaign(output_dir: str | Path = "artifacts/pitnn/research_campaign",
                 steps: int = 100_000, seed: int = 0, backend: str = "auto",
                 fast_tda: bool = False, fast_ep: bool = False,
                 mcwf_trajectories: int = 32, max_nodes: int | None = None) -> dict[str, Any]:
    """Execute the grid and write JSONL plus compact NPZ final-state arrays."""
    if steps < 1 or mcwf_trajectories < 1:
        raise ValueError("steps and mcwf_trajectories must be positive")
    destination = Path(output_dir); destination.mkdir(parents=True, exist_ok=True)
    points = parameter_grid()[:max_nodes] if max_nodes else parameter_grid()
    lattice = MicrotubuleLattice(MicrotubuleLatticeConfig(n_layers=2))
    tracker = TopologicalInvariantTracker(lattice.n_sites)
    ep = optimize_exceptional_point(EPOptimizeConfig()) if fast_ep else optimize_exceptional_point()
    records: list[dict[str, Any]] = []
    spin_states = np.empty((len(points), lattice.n_sites, 3), dtype=np.float64)
    densities = np.empty((len(points), 8, 8), dtype=np.complex128)
    # Spin dynamics do not depend on gamma_pump in this reduced model; cache by
    # the actual spin-control tuple while retaining one record per grid node.
    spin_cache: dict[tuple[float, float, str, str], tuple[dict[str, Any], np.ndarray]] = {}
    jsonl = destination / "campaign_records.jsonl"
    with jsonl.open("w", encoding="utf-8") as handle:
        for index, point in enumerate(points):
            key = (point.temperature_K, point.tau0, point.bath, point.firing)
            if key not in spin_cache:
                spin_cache[key] = _spin_result(point, steps, seed + index, backend, lattice, tracker)
            spin, spin_state = spin_cache[key]
            quantum, density = _quantum_result(mcwf_trajectories, seed + index, point.tau0)
            record = {"index": index, "parameters": asdict(point), "spin": spin,
                      "quantum": quantum, "bath": _bath_result(point, seed + index),
                      "electrophysiology": _electro_result(point), "ep": ep,
                      "fast_tda": bool(fast_tda)}
            handle.write(json.dumps(record, sort_keys=True, default=lambda value: value.tolist() if isinstance(value, np.ndarray) else str(value)) + "\n")
            records.append(record); spin_states[index] = spin_state; densities[index] = density
            if index % 8 == 0:
                gc.collect()
    np.savez_compressed(destination / "campaign_arrays.npz", spin_final=spin_states, density_final=densities)
    summary = {"schema": "PITNN.ResearchCampaign.v1", "n_nodes": len(records),
               "steps_per_spin_node": steps, "seed": seed, "backend": resolve_backend(backend),
               "output_dir": str(destination), "records_file": str(jsonl),
               "arrays_file": str(destination / "campaign_arrays.npz")}
    (destination / "campaign_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/pitnn/research_campaign"))
    parser.add_argument("--steps", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--fast-backend", action="store_true")
    parser.add_argument("--fast-tda", action="store_true")
    parser.add_argument("--fast-ep", action="store_true")
    parser.add_argument("--mcwf-trajectories", type=int, default=32)
    parser.add_argument("--max-nodes", type=int)
    args = parser.parse_args()
    summary = run_campaign(output_dir=args.output_dir, steps=args.steps, seed=args.seed,
                           backend="numba" if args.fast_backend else "auto",
                           fast_tda=args.fast_tda, fast_ep=args.fast_ep,
                           mcwf_trajectories=args.mcwf_trajectories, max_nodes=args.max_nodes)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
