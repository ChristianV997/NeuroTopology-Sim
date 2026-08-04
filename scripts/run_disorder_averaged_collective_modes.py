"""Test separation-dependent collective modes with matched disorder nulls.

This is a finite phenomenological lattice study.  It makes no biological
claim: an accepted effect means only that the stated model parameterization is
separation sensitive after averaging the declared structural-disorder draws.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
import hashlib
import itertools
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from physics.open_quantum import (
    LatticeConfig,
    LindbladLattice,
    MultiLatticeConfig,
    ThermalBathConfig,
    coupled_lattice,
    solve_gap,
)


def _safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_safe(item) for item in value]
    return value


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    os.close(descriptor)
    try:
        Path(temporary).write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_text(path, json.dumps(_safe(payload), indent=2, sort_keys=True, allow_nan=False) + "\n")


def _run_fingerprint(args: argparse.Namespace) -> str:
    excluded = {"output_dir", "checkpoint", "resume", "workers", "progress_every"}
    values = {key: _safe(value) for key, value in vars(args).items() if key not in excluded}
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _checkpoint_header(fingerprint: str) -> dict[str, str]:
    return {"schema": "NeuroTopologySim.DisorderAveragedCollectiveModesCheckpoint.v1", "fingerprint": fingerprint}


def _load_checkpoint(path: Path, fingerprint: str) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    if path.is_symlink() or not path.is_file():
        raise ValueError("checkpoint must be a regular file")
    records: dict[str, dict[str, Any]] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError("checkpoint is empty and cannot be resumed")
    header = json.loads(lines[0])
    if header != _checkpoint_header(fingerprint):
        raise ValueError("checkpoint fingerprint or schema does not match this configuration")
    for line in lines[1:]:
        if not line.strip():
            continue
        record = json.loads(line)
        point_id = record.get("point_id")
        if not isinstance(point_id, str) or not point_id:
            raise ValueError("checkpoint record is missing point_id")
        records[point_id] = record
    return records


def _initialize_checkpoint(path: Path, fingerprint: str) -> None:
    if path.exists():
        raise FileExistsError(f"checkpoint already exists; use --resume to continue: {path}")
    _atomic_text(path, json.dumps(_checkpoint_header(fingerprint), sort_keys=True) + "\n")


def _append_checkpoint(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(_safe(record), sort_keys=True, allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _point_id(spacing_nm: float, collective_rate_s: float, disorder_seed: int) -> str:
    return f"spacing={spacing_nm:.17g};collective_rate={collective_rate_s:.17g};seed={disorder_seed}"


def _signed_permutation_pvalue(values: np.ndarray) -> float:
    """Two-sided exact sign-flip p-value for paired disorder contrasts."""
    if values.ndim != 1 or values.size == 0 or not np.all(np.isfinite(values)):
        raise ValueError("sign-flip values must be a finite, non-empty vector")
    if values.size > 20:
        raise ValueError("exact sign-flip testing is limited to 20 paired samples")
    observed = abs(float(np.mean(values)))
    null_means = [abs(float(np.mean(values * np.asarray(signs))))
                  for signs in itertools.product((-1.0, 1.0), repeat=len(values))]
    return float(np.mean(np.asarray(null_means) >= observed - 1e-15))


def _evaluate(task: dict[str, Any]) -> dict[str, Any]:
    model = None
    try:
        bath = ThermalBathConfig.from_temperature(
            task["temperature_K"], task["transition_energy_eV"],
            thermal_relaxation_s=task["thermal_relaxation_s"],
            dephasing_rate_s=task["dephasing_rate_s"],
            radiative_rate_s=task["radiative_rate_s"],
        )
        bath = replace(
            bath,
            collective_radiative_rate_s=task["collective_rate_s"],
            collective_correlation_length_m=task["correlation_length_nm"] * 1e-9,
        )
        config = LatticeConfig(
            n_layers=task["n_layers"], interaction_cutoff_m=task["cutoff_nm"] * 1e-9,
            dielectric_constant=task["dielectric_constant"],
            transition_energy_eV=task["transition_energy_eV"], bath=bath,
        )
        pristine = coupled_lattice(config, MultiLatticeConfig(task["spacing_nm"] * 1e-9))
        rng = np.random.default_rng(task["disorder_seed"])
        positions = pristine.positions + rng.normal(
            0.0, task["disorder_sigma_nm"] * 1e-9, size=pristine.positions.shape,
        )
        model = LindbladLattice(positions, pristine.dipoles, config)
        result = solve_gap(
            model, dense_max_dimension=task["dense_max_dimension"],
            k=task["krylov_k"], maxiter=task["maxiter"],
        )
        failure = None
    except Exception as exc:  # retain failed points in the registered record
        result, failure = None, f"{type(exc).__name__}: {exc}"
    return {
        **task,
        "dimension": None if model is None else model.dimension,
        "method": None if result is None else result.method,
        "converged": bool(result and result.converged),
        "tau_subradiant_s": None if result is None else result.tau_subradiant_s,
        "gap_s": None if result is None else result.gap_s,
        "trace_preservation_residual_s": None if result is None else result.trace_preservation_residual_s,
        "failure": failure,
    }


def _summarize(records: list[dict[str, Any]], spacings_nm: list[float], rates_s: list[float]) -> list[dict[str, Any]]:
    null_rate = rates_s[0]
    by_key = {(row["spacing_nm"], row["collective_rate_s"], row["disorder_seed"]): row for row in records}
    summaries: list[dict[str, Any]] = []
    for rate in rates_s[1:]:
        paired: list[float] = []
        invalid_pairs = 0
        for seed in sorted({row["disorder_seed"] for row in records}):
            endpoint_values = []
            valid = True
            for spacing in (spacings_nm[0], spacings_nm[-1]):
                candidate = by_key.get((spacing, rate, seed))
                null = by_key.get((spacing, null_rate, seed))
                if not candidate or not null or not candidate["converged"] or not null["converged"]:
                    valid = False
                    break
                candidate_tau = candidate["tau_subradiant_s"]
                null_tau = null["tau_subradiant_s"]
                if (
                    not isinstance(candidate_tau, (int, float))
                    or not isinstance(null_tau, (int, float))
                    or not np.isfinite(candidate_tau)
                    or not np.isfinite(null_tau)
                    or candidate_tau <= 0
                    or null_tau <= 0
                ):
                    valid = False
                    break
                endpoint_values.append(np.log(candidate_tau / null_tau))
            if valid:
                paired.append(float(endpoint_values[0] - endpoint_values[1]))
            else:
                invalid_pairs += 1
        values = np.asarray(paired, dtype=float)
        summaries.append({
            "collective_rate_s": rate,
            "paired_disorder_samples": int(values.size),
            "invalid_disorder_samples": invalid_pairs,
            "mean_log_short_vs_long_null_adjusted_contrast": None if not values.size else float(values.mean()),
            "standard_error": None if values.size < 2 else float(values.std(ddof=1) / np.sqrt(values.size)),
            "exact_sign_flip_pvalue": None if not values.size else _signed_permutation_pvalue(values),
        })
    return summaries


def run(args: argparse.Namespace) -> dict[str, Any]:
    if (args.workers < 1 or args.disorder_samples < 2 or args.disorder_samples > 20
            or args.progress_every < 0 or not np.isfinite(args.disorder_sigma_nm)
            or args.disorder_sigma_nm < 0):
        raise ValueError("workers, disorder sample count, and disorder sigma are invalid")
    if len(args.spacings_nm) < 2 or len(set(args.spacings_nm)) != len(args.spacings_nm) or args.collective_rates_s[0] != 0.0 or len(set(args.collective_rates_s)) != len(args.collective_rates_s):
        raise ValueError("provide at least two spacings and list 0 as the first collective rate")
    if any(value <= 0 or not np.isfinite(value) for value in args.spacings_nm + args.collective_rates_s[1:]):
        raise ValueError("spacings and non-null collective rates must be finite and positive")
    scalar_parameters = (
        args.correlation_length_nm, args.temperature_K, args.cutoff_nm,
        args.transition_energy_eV, args.thermal_relaxation_s, args.radiative_rate_s,
        args.dephasing_rate_s, args.dielectric_constant, args.min_abs_log_contrast,
        args.alpha,
    )
    if (not all(np.isfinite(value) for value in scalar_parameters)
            or args.correlation_length_nm <= 0 or args.temperature_K <= 0 or args.cutoff_nm <= 0
            or args.n_layers < 1 or args.dense_max_dimension < 2 or args.krylov_k < 2
            or args.maxiter < 1 or args.min_abs_log_contrast < 0 or not 0 < args.alpha <= 1):
        raise ValueError("physical parameters and decision thresholds are invalid")
    output_dir = args.output_dir
    checkpoint = args.checkpoint or output_dir / "records.jsonl"
    fingerprint = _run_fingerprint(args)
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    if args.resume:
        completed = _load_checkpoint(checkpoint, fingerprint)
    else:
        _initialize_checkpoint(checkpoint, fingerprint)
        completed = {}
    tasks = [
        {**vars(args), "spacing_nm": spacing, "collective_rate_s": rate, "disorder_seed": args.seed + sample,
         "point_id": _point_id(spacing, rate, args.seed + sample)}
        for spacing in args.spacings_nm
        for rate in args.collective_rates_s
        for sample in range(args.disorder_samples)
    ]
    pending = [task for task in tasks if task["point_id"] not in completed]
    if args.workers == 1:
        iterator = map(_evaluate, pending)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            iterator = pool.map(_evaluate, pending)
            for index, record in enumerate(iterator, start=1):
                completed[record["point_id"]] = record
                _append_checkpoint(checkpoint, record)
                if args.progress_every and index % args.progress_every == 0:
                    print(f"completed {index}/{len(pending)} pending points", flush=True)
            iterator = None
    if iterator is not None:
        for index, record in enumerate(iterator, start=1):
            completed[record["point_id"]] = record
            _append_checkpoint(checkpoint, record)
            if args.progress_every and index % args.progress_every == 0:
                print(f"completed {index}/{len(pending)} pending points", flush=True)
    records = [completed[task["point_id"]] for task in tasks]
    summaries = _summarize(records, args.spacings_nm, args.collective_rates_s)
    for summary in summaries:
        effect = summary["mean_log_short_vs_long_null_adjusted_contrast"]
        summary["pre_registered_decision"] = (
            "EFFECT_CANDIDATE" if effect is not None
            and abs(effect) >= args.min_abs_log_contrast
            and summary["exact_sign_flip_pvalue"] <= args.alpha
            and summary["paired_disorder_samples"] == args.disorder_samples
            and summary["invalid_disorder_samples"] == 0
            else "NOT_SUPPORTED"
        )
    payload = {
        "schema": "NeuroTopologySim.DisorderAveragedCollectiveModes.v1",
        "pre_registered_null": {
            "collective_radiative_rate_s": 0.0,
            "claim": "No disorder-averaged separation-dependent lifetime shift beyond the independent-bath model.",
        },
        "primary_endpoint": {
            "definition": "matched-disorder [log(tau_candidate/tau_null) at shortest spacing] minus the same quantity at longest spacing",
            "minimum_absolute_log_contrast": args.min_abs_log_contrast,
            "alpha": args.alpha,
            "test": "two-sided exact paired sign-flip test",
        },
        "configuration": _safe(vars(args)),
        "records": _safe(records),
        "summaries": _safe(summaries),
        "scientific_note": "Finite dipolar lattice calculations test model sensitivity only. They do not establish biological subradiance or quantum coherence.",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _atomic_json(args.output_dir / "disorder_averaged_collective_modes.json", payload)
    return payload


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--spacings-nm", nargs="+", type=float, default=[3.0, 6.0, 10.0, 18.0])
    result.add_argument("--collective-rates-s", nargs="+", type=float, default=[0.0, 1e7, 1e8])
    result.add_argument("--disorder-samples", type=int, default=8)
    result.add_argument("--disorder-sigma-nm", type=float, default=0.15)
    result.add_argument("--seed", type=int, default=20260727)
    result.add_argument("--correlation-length-nm", type=float, default=8.0)
    result.add_argument("--temperature-K", type=float, default=310.0)
    result.add_argument("--transition-energy-eV", type=float, default=4.43)
    result.add_argument("--thermal-relaxation-s", type=float, default=1e9)
    result.add_argument("--radiative-rate-s", type=float, default=1e8)
    result.add_argument("--dephasing-rate-s", type=float, default=1e8)
    result.add_argument("--dielectric-constant", type=float, default=7.0)
    result.add_argument("--cutoff-nm", type=float, default=30.0)
    result.add_argument("--n-layers", type=int, default=1)
    result.add_argument("--dense-max-dimension", type=int, default=32)
    result.add_argument("--krylov-k", type=int, default=6)
    result.add_argument("--maxiter", type=int, default=2000)
    result.add_argument("--min-abs-log-contrast", type=float, default=np.log(1.25))
    result.add_argument("--alpha", type=float, default=0.05)
    result.add_argument("--workers", type=int, default=1)
    result.add_argument("--checkpoint", type=Path, default=None)
    result.add_argument("--resume", action="store_true")
    result.add_argument("--progress-every", type=int, default=1)
    result.add_argument("--output-dir", type=Path, default=Path("artifacts/campaign/disorder_averaged_collective_modes"))
    return result


if __name__ == "__main__":
    payload = run(parser().parse_args())
    print(json.dumps({"records": len(payload["records"]), "summaries": payload["summaries"]}, sort_keys=True))
