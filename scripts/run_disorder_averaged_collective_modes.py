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
from runs.run_record import RunRecordV1, build_run_id

CAMPAIGN_SCHEMA = "NeuroTopologySim.DisorderAveragedCollectiveModes.v1"
CAMPAIGN_FILENAME = "disorder_averaged_collective_modes.json"
RUN_RECORD_SIDECAR_FILENAME = "RunRecord.json"
SIDECAR_RUN_KIND = "disorder_averaged_collective_modes"
SIDECAR_REPO = "NeuroTopology-Sim"
SIDECAR_GIT_COMMIT = "working-tree"
SIDECAR_ARGV = ["scripts/run_disorder_averaged_collective_modes.py"]
_IO_AND_SIDECAR_FLAGS = frozenset(
    {"output_dir", "checkpoint", "resume", "workers", "progress_every", "write_run_record"}
)
_ALLOWED_SIDECAR_VERDICTS = frozenset({"NOT_SUPPORTED", "INCONCLUSIVE"})


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
    values = {key: _safe(value) for key, value in vars(args).items() if key not in _IO_AND_SIDECAR_FLAGS}
    encoded = json.dumps(values, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _campaign_configuration(args: argparse.Namespace) -> dict[str, Any]:
    """Campaign configuration omits the sidecar flag so v1 JSON shape stays stable."""
    return {key: value for key, value in vars(args).items() if key != "write_run_record"}


def _sidecar_input_params(payload: dict[str, Any]) -> dict[str, Any]:
    config = payload.get("configuration")
    if not isinstance(config, dict):
        return {}
    return {
        str(key): _safe(value)
        for key, value in config.items()
        if key not in _IO_AND_SIDECAR_FLAGS
    }


def _finite_float(value: Any) -> float | None:
    if isinstance(value, (bool, np.bool_)):
        return None
    if not isinstance(value, (int, float, np.integer, np.floating)):
        return None
    number = float(value)
    return number if np.isfinite(number) else None


def _as_int(value: Any) -> int | None:
    if isinstance(value, (bool, np.bool_)):
        return None
    if isinstance(value, (int, np.integer)):
        return int(value)
    return None


def _sidecar_metrics(payload: dict[str, Any]) -> dict[str, float]:
    """Sidecar metric floats used for provenance and ``build_run_id``.

    Copies existing per-summary campaign floats when finite, then adds
    derived counts ``n_summaries``, ``n_pre_registered_effect_candidate``,
    and ``n_pre_registered_not_supported`` from already-written campaign
    labels. Does not rescore or change campaign thresholds.
    """
    metrics: dict[str, float] = {}
    summaries = payload.get("summaries")
    if not isinstance(summaries, list):
        return metrics
    n_effect_candidate = 0.0
    n_not_supported = 0.0
    for index, summary in enumerate(summaries):
        if not isinstance(summary, dict):
            continue
        prefix = f"summary_{index}"
        for key in (
            "paired_disorder_samples",
            "invalid_disorder_samples",
            "mean_log_short_vs_long_null_adjusted_contrast",
            "standard_error",
            "exact_sign_flip_pvalue",
        ):
            number = _finite_float(summary.get(key))
            if number is not None:
                metrics[f"{prefix}_{key}"] = number
        decision = summary.get("pre_registered_decision")
        if decision == "EFFECT_CANDIDATE":
            n_effect_candidate += 1.0
        elif decision == "NOT_SUPPORTED":
            n_not_supported += 1.0
    metrics["n_summaries"] = float(len(summaries))
    metrics["n_pre_registered_effect_candidate"] = n_effect_candidate
    metrics["n_pre_registered_not_supported"] = n_not_supported
    return metrics


def _sidecar_verdict(payload: dict[str, Any]) -> str:
    """Envelope only: never PASS. K > 100 remains the only PASS elsewhere.

    Missing or invalid campaign material is INCONCLUSIVE. A completed
    synthetic lattice campaign cannot emit PASS and maps to NOT_SUPPORTED.
    Campaign ``pre_registered_decision`` is left on the v1 JSON unchanged.
    """
    if not isinstance(payload, dict) or payload.get("schema") != CAMPAIGN_SCHEMA:
        return "INCONCLUSIVE"
    summaries = payload.get("summaries")
    if not isinstance(summaries, list) or not summaries:
        return "INCONCLUSIVE"
    for summary in summaries:
        if not isinstance(summary, dict):
            return "INCONCLUSIVE"
        decision = summary.get("pre_registered_decision")
        if decision not in {"EFFECT_CANDIDATE", "NOT_SUPPORTED"}:
            return "INCONCLUSIVE"
        paired = _as_int(summary.get("paired_disorder_samples"))
        invalid = _as_int(summary.get("invalid_disorder_samples"))
        effect = summary.get("mean_log_short_vs_long_null_adjusted_contrast")
        if paired is None or paired < 1:
            return "NOT_SUPPORTED" if decision == "NOT_SUPPORTED" else "INCONCLUSIVE"
        if invalid is None or invalid > 0:
            return "NOT_SUPPORTED" if decision == "NOT_SUPPORTED" else "INCONCLUSIVE"
        if effect is None or _finite_float(effect) is None:
            return "NOT_SUPPORTED" if decision == "NOT_SUPPORTED" else "INCONCLUSIVE"
    return "NOT_SUPPORTED"


def _campaign_sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_run_record_sidecar(
    payload: dict[str, Any],
    campaign_path: Path,
    *,
    fingerprint: str | None = None,
    _now: Any = None,
) -> RunRecordV1:
    """Build a deterministic RunRecordV1 sidecar from campaign inputs and provenance."""
    campaign_path = Path(campaign_path)
    inputs = _sidecar_input_params(payload)
    if fingerprint:
        inputs = {**inputs, "run_fingerprint": fingerprint}
    metrics = _sidecar_metrics(payload)
    run_id = build_run_id(
        SIDECAR_RUN_KIND,
        SIDECAR_REPO,
        SIDECAR_GIT_COMMIT,
        list(SIDECAR_ARGV),
        inputs,
        metrics,
        repo_root=ROOT,
    )
    verdict = _sidecar_verdict(payload)
    if verdict not in _ALLOWED_SIDECAR_VERDICTS:
        verdict = "INCONCLUSIVE"
    record = RunRecordV1.make(
        run_id,
        SIDECAR_RUN_KIND,
        data_mode="synthetic",
        verdict=verdict,
        metrics=metrics,
        artifacts={
            "campaign_json": campaign_path.name,
            "campaign_schema": CAMPAIGN_SCHEMA,
            "campaign_sha256": _campaign_sha256(campaign_path),
        },
        source="scripts/run_disorder_averaged_collective_modes.py",
        _now=_now,
    )
    record.input = inputs
    if isinstance(payload, dict):
        note = payload.get("scientific_note")
        if isinstance(note, str):
            record.notes = note
    record.guardrails = {
        "pass_reserved_for_bayes_factor_k_gt_100": True,
        "synthetic_lattice_is_not_empirical_biology": True,
        "campaign_schema": CAMPAIGN_SCHEMA,
        "sidecar_does_not_replace_campaign_json": True,
    }
    return record


def sidecar_to_dict(record: RunRecordV1) -> dict[str, Any]:
    """General RunRecordV1 JSON plus sidecar provenance.

    ``to_dict()`` is the canonical v0.1 shape and omits ``input`` / ``notes`` /
    ``guardrails``. Those fields are set on the dataclass and must be written
    explicitly so they are not dropped. ``schema_version`` stays ``0.1``.
    """
    payload = record.to_dict()
    payload["schema_version"] = "0.1"
    payload["input"] = record.input if record.input is not None else {}
    payload["notes"] = record.notes
    payload["guardrails"] = record.guardrails if record.guardrails is not None else {}
    return payload


def write_run_record_sidecar(record: RunRecordV1, path: Path) -> Path:
    """Atomically write the sidecar the same way the campaign JSON is written."""
    path = Path(path)
    _atomic_json(path, sidecar_to_dict(record))
    return path


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
    task_base = _campaign_configuration(args)
    tasks = [
        {**task_base, "spacing_nm": spacing, "collective_rate_s": rate, "disorder_seed": args.seed + sample,
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
        "schema": CAMPAIGN_SCHEMA,
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
        "configuration": _safe(_campaign_configuration(args)),
        "records": _safe(records),
        "summaries": _safe(summaries),
        "scientific_note": "Finite dipolar lattice calculations test model sensitivity only. They do not establish biological subradiance or quantum coherence.",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    campaign_path = args.output_dir / CAMPAIGN_FILENAME
    _atomic_json(campaign_path, payload)
    if getattr(args, "write_run_record", False):
        record = build_run_record_sidecar(payload, campaign_path, fingerprint=fingerprint)
        write_run_record_sidecar(record, args.output_dir / RUN_RECORD_SIDECAR_FILENAME)
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
    result.add_argument(
        "--write-run-record",
        action="store_true",
        help="Write a RunRecordV1 sidecar next to the campaign JSON. Does not replace NeuroTopologySim.DisorderAveragedCollectiveModes.v1.",
    )
    return result


if __name__ == "__main__":
    payload = run(parser().parse_args())
    print(json.dumps({"records": len(payload["records"]), "summaries": payload["summaries"]}, sort_keys=True))
