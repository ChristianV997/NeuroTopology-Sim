"""Run conservative theory-development scans for long-memory and dephasing regimes."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
import sys
from typing import Iterable

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sim.pitnn.non_markovian_bath import DrudeLorentzBath, MultiExponentialMemoryBath, OscillatoryMemoryBath


def _json_safe(value: object) -> object:
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_safe(payload), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _adaptive_grid(tau_b_s: float, decay_rate_s: float, duration_s: float, min_points: int = 200) -> np.ndarray:
    dt = min(tau_b_s / 20.0, 1.0 / (50.0 * decay_rate_s))
    dt = max(dt, duration_s / max(min_points - 1, 1))
    n_steps = int(np.ceil(duration_s / dt))
    return np.linspace(0.0, duration_s, n_steps + 1)


def _dimensionless(mu: float, g: float) -> tuple[float, float]:
    if mu <= 0 or g < 0:
        raise ValueError("mu must be positive and g non-negative")
    return mu, g


def _effective_observables(times: np.ndarray, decay_rate_s: float, gain: float, dephasing_rate_s: float) -> dict[str, float]:
    times = np.asarray(times, dtype=float)
    if times.ndim != 1 or len(times) < 2 or np.any(np.diff(times) <= 0):
        raise ValueError("times must be a strictly increasing 1D grid")
    gain = float(max(gain, 0.0))
    effective_decay = decay_rate_s / (1.0 + gain)
    effective_dephasing = dephasing_rate_s + 0.35 * decay_rate_s / (1.0 + 0.5 * gain)
    population = np.exp(-effective_decay * times)
    coherence = np.exp(-(0.5 * effective_decay + effective_dephasing) * times)
    return {
        "integrated_population": float(np.trapezoid(population, times)),
        "integrated_coherence": float(np.trapezoid(coherence, times)),
        "final_population": float(population[-1]),
        "final_coherence": float(coherence[-1]),
        "effective_decay_s": float(effective_decay),
        "effective_dephasing_s": float(effective_dephasing),
    }


def _single_exp_scan(mu_values: Iterable[float], g_values: Iterable[float], *, decay_rate_s: float,
                     duration_s: float, dephasing_ratio: float, refinement_factor: int = 2) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for mu in mu_values:
        tau_b_s = mu / decay_rate_s
        for g in g_values:
            if g <= 0:
                continue
            times = _adaptive_grid(tau_b_s, decay_rate_s, duration_s)
            gain = g * mu / (1.0 + mu)
            observables = _effective_observables(times, decay_rate_s, gain, dephasing_rate_s=dephasing_ratio * decay_rate_s)
            refined_times = _adaptive_grid(tau_b_s, decay_rate_s, duration_s, min_points=len(times) * refinement_factor)
            refined = _effective_observables(refined_times, decay_rate_s, gain, dephasing_rate_s=dephasing_ratio * decay_rate_s)
            records.append({
                "kernel_family": "single_exponential",
                "mu": mu,
                "g": g,
                "tau_B_s": tau_b_s,
                "dimensionless_gain": gain,
                "time_step_s": float(np.min(np.diff(times))) if len(times) > 1 else None,
                "n_steps": int(len(times)),
                "integrated_population": observables["integrated_population"],
                "integrated_coherence": observables["integrated_coherence"],
                "final_population": observables["final_population"],
                "final_coherence": observables["final_coherence"],
                "refined_integrated_population": refined["integrated_population"],
                "refined_integrated_coherence": refined["integrated_coherence"],
                "population_rel_change": abs(refined["integrated_population"] - observables["integrated_population"]) / max(abs(refined["integrated_population"]), 1e-15),
                "coherence_rel_change": abs(refined["integrated_coherence"] - observables["integrated_coherence"]) / max(abs(refined["integrated_coherence"]), 1e-15),
                "dephasing_rate_s": dephasing_ratio * decay_rate_s,
                "dephasing_ratio": dephasing_ratio,
                "converged": abs(refined["integrated_population"] - observables["integrated_population"]) <= 1e-4 * max(1.0, abs(refined["integrated_population"])),
            })
    return records


def _multi_exp_scan(mu_values: Iterable[float], g_values: Iterable[float], *, decay_rate_s: float,
                    duration_s: float) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for mu in mu_values:
        tau_b_s = mu / decay_rate_s
        bath = MultiExponentialMemoryBath(
            amplitudes_s2=(0.65, 0.35),
            memory_times_s=(tau_b_s / 3.0, tau_b_s * 2.5),
        )
        for g in g_values:
            if g <= 0:
                continue
            scale = g / sum(a * t * t for a, t in zip(bath.amplitudes_s2, bath.memory_times_s))
            amplitudes = tuple(a * scale for a in bath.amplitudes_s2)
            scaled_bath = MultiExponentialMemoryBath(amplitudes_s2=amplitudes, memory_times_s=bath.memory_times_s)
            times = _adaptive_grid(tau_b_s, decay_rate_s, duration_s)
            gain = g * (0.35 + 0.65 * np.tanh(mu))
            observables = _effective_observables(times, decay_rate_s, gain, dephasing_rate_s=0.0)
            records.append({
                "kernel_family": "multi_exponential",
                "mu": mu,
                "g": g,
                "tau_B_s": tau_b_s,
                "amplitudes_s2": list(amplitudes),
                "memory_times_s": list(scaled_bath.memory_times_s),
                "dimensionless_gain": gain,
                **observables,
            })
    return records


def _oscillatory_scan(mu_values: Iterable[float], g_values: Iterable[float], *, decay_rate_s: float,
                      duration_s: float) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for mu in mu_values:
        tau_b_s = mu / decay_rate_s
        for g in g_values:
            if g <= 0:
                continue
            bath = OscillatoryMemoryBath(amplitude_s2=g / (tau_b_s ** 2), memory_time_s=tau_b_s, angular_frequency_s=np.pi / tau_b_s)
            times = _adaptive_grid(tau_b_s, decay_rate_s, duration_s)
            gain = g * mu / (1.0 + mu) * (0.8 - 0.25 * np.exp(-mu))
            observables = _effective_observables(times, decay_rate_s, gain, dephasing_rate_s=0.05 * decay_rate_s)
            records.append({
                "kernel_family": "oscillatory",
                "mu": mu,
                "g": g,
                "tau_B_s": tau_b_s,
                "angular_frequency_s": bath.angular_frequency_s,
                "dimensionless_gain": gain,
                **observables,
            })
    return records


def _dephasing_scan(mu_values: Iterable[float], g_values: Iterable[float], *, decay_rate_s: float,
                    duration_s: float, dephasing_values: Iterable[float], include_null_control: bool = False) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for mu in mu_values:
        tau_b_s = mu / decay_rate_s
        times = _adaptive_grid(tau_b_s, decay_rate_s, duration_s)
        for g in g_values:
            if g <= 0:
                continue
            gain = g * mu / (1.0 + mu)
            for dephasing_ratio in dephasing_values:
                observables = _effective_observables(times, decay_rate_s, gain, dephasing_rate_s=dephasing_ratio * decay_rate_s)
                population_ratio = observables["integrated_population"] / max(float(np.trapezoid(np.exp(-decay_rate_s * times), times)), 1e-15)
                coherence_ratio = observables["integrated_coherence"] / max(float(np.trapezoid(np.exp(-(0.5 * decay_rate_s + dephasing_ratio * decay_rate_s) * times), times)), 1e-15)
                records.append({
                    "kernel_family": "single_exponential_dephasing",
                    "mu": mu,
                    "g": g,
                    "tau_B_s": tau_b_s,
                    "dimensionless_gain": gain,
                    "dephasing_ratio": dephasing_ratio,
                    "control_type": "candidate",
                    "population_ratio_to_null": population_ratio,
                    "coherence_ratio_to_null": coherence_ratio,
                    **observables,
                })
                if include_null_control:
                    null_observables = _effective_observables(times, decay_rate_s, 0.0, dephasing_rate_s=dephasing_ratio * decay_rate_s)
                    records.append({
                        "kernel_family": "single_exponential_dephasing",
                        "mu": mu,
                        "g": 0.0,
                        "tau_B_s": tau_b_s,
                        "dimensionless_gain": 0.0,
                        "dephasing_ratio": dephasing_ratio,
                        "control_type": "matched_null_zero_gain",
                        "paired_candidate_gain": gain,
                        "population_ratio_to_null": 1.0,
                        "coherence_ratio_to_null": 1.0,
                        **null_observables,
                    })
    return records


def _summarize(records: list[dict[str, object]]) -> dict[str, object]:
    if not records:
        return {"count": 0, "moderate_retention_count": 0}
    population = np.array([float(r["integrated_population"]) for r in records], dtype=float)
    coherence = np.array([float(r["integrated_coherence"]) for r in records], dtype=float)
    moderate = [r for r in records if 1.2 <= float(r["integrated_population"]) / max(float(r["final_population"]), 1e-15) <= 5.0
                and 1.2 <= float(r["integrated_coherence"]) / max(float(r["final_coherence"]), 1e-15) <= 5.0]
    return {
        "count": len(records),
        "moderate_retention_count": len(moderate),
        "population_span": [float(np.min(population)), float(np.max(population))],
        "coherence_span": [float(np.min(coherence)), float(np.max(coherence))],
    }


def _compare_to_meditation_pattern(records: list[dict[str, object]]) -> dict[str, object]:
    if not records:
        return {"conclusion": "no_records"}
    population = np.array([float(r["integrated_population"]) for r in records], dtype=float)
    coherence = np.array([float(r["integrated_coherence"]) for r in records], dtype=float)
    return {
        "conclusion": "qualitative_only",
        "pattern": "retention can rise without any topology signal in this surrogate model",
        "stable_signature": {
            "population_median": float(np.median(population)),
            "coherence_median": float(np.median(coherence)),
        },
        "empirical_constraint": "advanced meditation shows reduced classical complexity while winding/topology metrics remain null; this model comparison intentionally does not require increased winding",
    }


def run_campaign(args: argparse.Namespace) -> dict[str, object]:
    decay_rate_s = float(args.decay_rate_s)
    duration_s = float(args.duration_s)
    mu_values = [float(v) for v in args.mu_values]
    g_values = [float(v) for v in args.g_values]
    dephasing_values = [float(v) for v in (args.dephasing_ratios if args.dephasing_ratios is not None else [0.02, 0.05, 0.1, 0.15, 0.25])]

    single = _single_exp_scan(mu_values, g_values, decay_rate_s=decay_rate_s, duration_s=duration_s, dephasing_ratio=args.dephasing_ratio)
    multi = _multi_exp_scan(mu_values, g_values, decay_rate_s=decay_rate_s, duration_s=duration_s)
    oscillatory = _oscillatory_scan(mu_values, g_values, decay_rate_s=decay_rate_s, duration_s=duration_s)
    dephasing = _dephasing_scan(mu_values, g_values, decay_rate_s=decay_rate_s, duration_s=duration_s, dephasing_values=dephasing_values, include_null_control=args.include_null_control)

    payload = {
        "schema": "ScienceR-Dsim.TheoryMemoryCampaign.v1",
        "configuration": {
            "decay_rate_s": decay_rate_s,
            "duration_s": duration_s,
            "mu_values": mu_values,
            "g_values": g_values,
            "dephasing_ratio": args.dephasing_ratio,
            "dephasing_ratios": dephasing_values,
            "include_null_control": bool(args.include_null_control),
        },
        "single_exponential": single,
        "multi_exponential": multi,
        "oscillatory": oscillatory,
        "dephasing": dephasing,
        "single_summary": _summarize(single),
        "multi_summary": _summarize(multi),
        "oscillatory_summary": _summarize(oscillatory),
        "dephasing_summary": _summarize(dephasing),
        "meditation_comparison": _compare_to_meditation_pattern(single + multi + oscillatory + dephasing),
        "scientific_note": "This campaign is theory development only. It records stable surrogate observables and does not claim biological mechanism confirmation.",
    }
    _write_json(args.output_dir / "phase_diagram_summary.json", payload)

    markdown = [
        "# Theory Memory Campaign",
        "",
        f"- decay_rate_s: {decay_rate_s:.6g}",
        f"- duration_s: {duration_s:.6g}",
        f"- mu_values: {mu_values}",
        f"- g_values: {g_values}",
        f"- dephasing_ratio: {args.dephasing_ratio}",
        "",
        "## Results",
        "",
        f"- single_exponential records: {len(single)}",
        f"- multi_exponential records: {len(multi)}",
        f"- oscillatory records: {len(oscillatory)}",
        f"- dephasing records: {len(dephasing)}",
        f"- moderate_retention_count: {payload['single_summary']['moderate_retention_count'] + payload['multi_summary']['moderate_retention_count'] + payload['oscillatory_summary']['moderate_retention_count'] + payload['dephasing_summary']['moderate_retention_count']}",
        "",
        "## Qualitative Comparison",
        "",
        payload["meditation_comparison"]["empirical_constraint"],
    ]
    (args.output_dir / "theory_regime_report.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    (args.output_dir / "records.jsonl").write_text("\n".join(json.dumps(_json_safe(record), sort_keys=True, allow_nan=False) for record in single + multi + oscillatory + dephasing) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/theory_campaign/latest"))
    parser.add_argument("--decay-rate-s", type=float, default=1e8)
    parser.add_argument("--duration-s", type=float, default=2e-7)
    parser.add_argument("--mu-values", nargs="+", type=float, default=[0.1, 0.3, 1.0, 3.0, 10.0])
    parser.add_argument("--g-values", nargs="+", type=float, default=[1e-5, 3e-5, 1e-4, 3e-4, 1e-3, 3e-3, 1e-2])
    parser.add_argument("--dephasing-ratio", type=float, default=0.15)
    parser.add_argument("--dephasing-ratios", nargs="+", type=float, default=None)
    parser.add_argument("--include-null-control", action="store_true")
    args = parser.parse_args()
    if args.decay_rate_s <= 0 or args.duration_s <= 0 or args.dephasing_ratio < 0:
        parser.error("rates and duration must be positive")
    run_campaign(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
