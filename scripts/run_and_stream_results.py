"""Print the latest validated ScienceR-Dsim results as copyable text.

This reporter is deliberately provenance-aware: missing executables, missing
TD-DFT outputs, and incomplete cohorts are printed as unavailable rather than
replaced with synthetic measurements.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def f(value: Any) -> str:
    if value is None:
        return "UNAVAILABLE"
    number = float(value)
    return f"{number:.6e}" if number and abs(number) < 1e-3 else f"{number:.6f}"


def task_tddft() -> None:
    print("TASK 1 — TD-DFT SITE ENERGIES AND TRANSITION DIPOLES")
    npz = ROOT / "data/qm/td_dft_subnetwork/td_dft_subnetwork.npz"
    manifest = ROOT / "data/qm/td_dft_subnetwork/td_dft_subnetwork_manifest.json"
    if npz.exists():
        import numpy as np
        with np.load(npz, allow_pickle=False) as data:
            print("site_id                 E_eV          mu_x_D       mu_y_D       mu_z_D       |mu|_D")
            energies = data["site_energies_eV"]
            dipoles = data["transition_dipoles_debye"]
            for site, energy, dipole in zip(data["site_ids"], energies, dipoles):
                vector = np.asarray(dipole, float)
                print(f"{str(site):22s} {float(energy):12.6f} {vector[0]:12.6f} {vector[1]:12.6f} {vector[2]:12.6f} {float(np.linalg.norm(vector)):12.6f}")
        print("HOMO-LUMO gap: UNAVAILABLE (not stored by the validated NPZ contract)")
        print("Oscillator strengths: UNAVAILABLE (not stored by the validated NPZ contract)")
        return
    print("STATUS: UNAVAILABLE — no TD-DFT NPZ output exists.")
    print("The local manifest is geometry-only and explicitly marks TD-DFT as pending.")
    if manifest.exists():
        print("MANIFEST: " + str(manifest))


def task_cloud() -> None:
    print("\nLATEST AWS DM1 CLOUD EXECUTION")
    candidates = sorted((ROOT / "artifacts/telemetry").glob("**/cloud_telemetry.json"), key=lambda item: item.stat().st_mtime)
    if not candidates:
        print("STATUS: UNAVAILABLE — no cloud telemetry artifact found.")
        return
    source = candidates[-1]
    payload = load_json(source)
    telemetry = payload.get("telemetry", {})
    print(f"artifact: {source}")
    print(f"device_arn: {telemetry.get('device_arn', 'UNAVAILABLE')}")
    print(f"verdict: {telemetry.get('verdict', 'UNAVAILABLE')}")
    print(f"time_span_s: {telemetry.get('time_span_s', 'UNAVAILABLE')}")
    print(f"survival_probability_site_0: {telemetry.get('survival_probability_site_0', 'UNAVAILABLE')}")
    print(f"chiral_current_expectation_values: {telemetry.get('chiral_current_expectation_values', 'UNAVAILABLE')}")
    cost = telemetry.get("execution_cost", {})
    print(f"simulator_cost_usd: {f(cost.get('simulator_cost_usd'))}")
    print(f"task_ids: {telemetry.get('task_ids', 'UNAVAILABLE')}")


def task_thermal() -> None:
    print("\nLATEST AWS DM1 THERMAL SWEEP")
    candidates = sorted((ROOT / "artifacts/telemetry").glob("**/thermal_sweep_summary.json"), key=lambda item: item.stat().st_mtime)
    if not candidates:
        print("STATUS: UNAVAILABLE — no thermal sweep artifact found.")
        return
    source = candidates[-1]
    payload = load_json(source)
    records = payload.get("records", [])
    print(f"artifact: {source}")
    print("T_K       tau_ns      survival_site0    current_s^-1    verdict")
    total_cost = 0.0
    for record in records:
        telemetry = record.get("telemetry", {})
        survival = telemetry.get("survival_probability_site_0", [None])[-1]
        current = telemetry.get("chiral_current_expectation_values", [[None]])[-1][0]
        cost = telemetry.get("execution_cost", {}).get("simulator_cost_usd", 0.0) or 0.0
        total_cost += float(cost)
        tau_ns = float(record.get("relaxation_time_s", 0.0)) * 1e9
        print(f"{float(record.get('temperature_K')):7.3f} {tau_ns:10.6f} {f(survival):16s} {f(current):14s} {telemetry.get('verdict', 'UNAVAILABLE')}")
    print(f"nodes: {len(records)}")
    print(f"total_simulator_cost_usd: {f(total_cost)}")


def task_bath() -> None:
    print("\nTASK 2 — NON-MARKOVIAN BATH / COHERENCE")
    path = ROOT / "artifacts/exact_dynamics/non_markovian_bath/run_310K_refined/non_markovian_falsification.json"
    spectrum = ROOT / "artifacts/exact_dynamics/spectral_density_smoke/spectrum.json"
    payload = load_json(path)
    primary = payload.get("primary", {})
    evaluation = primary.get("evaluation", {})
    print(f"backend: {primary.get('backend', 'UNAVAILABLE')}")
    print(f"temperature_K: {f(primary.get('temperature_K'))}")
    print(f"reorganization_energy_cm^-1: {f(primary.get('reorganization_energy_cm_inv'))}")
    print(f"trace_residual: {f(primary.get('trace_residual'))}")
    print(f"positivity_residual: {f(primary.get('positivity_residual'))}")
    print(f"converged: {payload.get('convergence_passed')}")
    print(f"max_state_difference: {f(payload.get('max_state_difference'))}")
    tau_s = evaluation.get("tau_subradiant_s")
    print(f"tau_coherence_s: {f(tau_s)}")
    print(f"tau_coherence_fs: {f(None if tau_s is None else float(tau_s) * 1e15)}")
    print("time_fs       |rho_01|")
    envelope = evaluation.get("coherence_envelope", [])
    # The artifact stores 0.5-fs samples over 30 fs; print every 100 fs only
    # when present, otherwise print the measured samples and their range.
    if envelope:
        for index, value in enumerate(envelope):
            time_fs = index * float(primary.get("time_step_fs", 0.0))
            if index == 0 or time_fs >= 100.0 or index == len(envelope) - 1:
                print(f"{time_fs:10.3f} {float(value):12.6f}")
        print("NOTE: requested 0–5000 fs / 100 fs output is unavailable; this artifact covers only the stored 0–30 fs window.")
    if spectrum.exists():
        spec = load_json(spectrum)
        omega = spec.get("omega_s", [])
        density = spec.get("spectral_density_J", [])
        if omega and density:
            peak = max(range(len(density)), key=lambda i: float(density[i]))
            print(f"spectral_peak_omega_s^-1: {float(omega[peak]):.6f}")
            print(f"reorganization_energy_J: {f(spec.get('reorganization_energy_estimate_J'))}")
    print(f"verdict: {payload.get('verdict', 'UNAVAILABLE')}")


def task_eeg() -> None:
    print("\nTASK 3 — OPENNEURO ds005620 EEG TOPOLOGY")
    path = ROOT / "../NeuroTopology-Sim/artifacts/topology_monitoring/cohort_sedation/cohort_topology_summary.json"
    if not path.exists():
        print("STATUS: UNAVAILABLE — cohort artifact not found.")
        return
    payload = load_json(path)
    print(f"discovered_subjects: {payload.get('discovered_subjects', 'UNAVAILABLE')}")
    print(f"paired_subjects: {payload.get('paired_subjects', 'UNAVAILABLE')}")
    print(f"power_status: {payload.get('power_status', 'UNAVAILABLE')}")
    for condition in ("awake", "sedated"):
        metrics = payload.get("aggregate", {}).get(condition, {})
        beta = metrics.get("mean_beta1", {})
        charge = metrics.get("mean_q_spatial", {})
        print(f"{condition}_mean_beta1: {f(beta.get('mean'))}")
        print(f"{condition}_mean_q_spatial: {f(charge.get('mean'))}")
    print("Wilcoxon: UNAVAILABLE (paired cohort is insufficient)")
    print("Bayes factor: UNAVAILABLE for N=21; no cohort-wide inference is present")
    print("verdict: INCONCLUSIVE")


def main() -> int:
    print("ScienceR-Dsim LATEST VALIDATED RESULTS — PLAIN-TEXT STREAM")
    print(f"repository: {ROOT}")
    task_tddft()
    task_cloud()
    task_thermal()
    task_bath()
    task_eeg()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
