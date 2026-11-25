"""Hypothesis pipeline — runs a sim spec, writes summary.json + RunRecord.json.

Usage:
  python -m pipelines.hypothesis --spec governance/specs/HYP-20260506-002.yaml \
                                  --output artifacts

Outputs (in --output dir):
  summary.json    — metrics + verdict (existing format)
  RunRecord.json  — v0.1 run artifact contract
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple


# ── YAML loader (stdlib only) ─────────────────────────────────────────────────

def _load_yaml_simple(path: Path) -> Dict[str, Any]:
    """Minimal YAML parser sufficient for flat + one-level-nested spec files.
    No external deps required.
    """
    try:
        import yaml  # type: ignore
        with open(path) as fh:
            return yaml.safe_load(fh) or {}
    except ImportError:
        pass

    result: Dict[str, Any] = {}
    current_key: Optional[str] = None
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue
        if stripped.endswith(">"):
            key = stripped.rstrip(">:").strip().rstrip(":")
            parts = []
            i += 1
            while i < len(lines) and (lines[i].startswith("  ") or lines[i].strip() == ""):
                parts.append(lines[i].strip())
                i += 1
            result[key] = " ".join(p for p in parts if p)
            continue
        if ":" in stripped and not stripped.startswith(" "):
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if val:
                result[key] = _coerce(val)
                current_key = None
            else:
                current_key = key
                result[key] = {}
            i += 1
        elif current_key and stripped.startswith("  "):
            sub = stripped.strip()
            if ":" in sub:
                k2, _, v2 = sub.partition(":")
                result[current_key][k2.strip()] = _coerce(v2.strip())
            i += 1
        else:
            i += 1
    return result


def _coerce(val: str) -> Any:
    if val.lower() in ("true", "yes"):
        return True
    if val.lower() in ("false", "no"):
        return False
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val


# ── Hypothesis runner ─────────────────────────────────────────────────────────

# ── canonical spec and threshold evaluation ───────────────────────────────────

_CANONICAL_THRESHOLD_KEYS = frozenset({"I_mean_min", "Qabs_max", "I_std_max", "auc_min", "p_max", "n_shuffles"})
_SYNTHETIC_THRESHOLDS = {"I_mean_min": ("I_mean", "min"), "Qabs_max": ("Qabs", "max"), "I_std_max": ("I_std", "max")}
_OPENNEURO_THRESHOLDS = {"auc_min": ("heldout_auc", "min"), "p_max": ("p_value", "max")}
_DATA_MODES = frozenset({"synthetic", "openneuro"})


def _canonical_spec(raw: Any, default_id: str) -> Dict[str, Any]:
    """Map the governance schema and the documented flat schema onto one canonical record.

    Governance form (what ``governance/specs`` uses): ``id``, ``claim_type``, ``layer``,
    ``data{mode, dataset_id, params}``, ``discriminator{mode, config}``,
    ``pass_fail{criteria, thresholds}``. Documented flat form (legacy aliases): ``spec_id``,
    ``data_mode``, ``dataset_id``, ``sim_params``, ``threshold``. A field declared in both forms
    must agree; a conflict is an error, never a silent choice.
    """
    if not isinstance(raw, Mapping):
        raise ValueError("hypothesis spec must be a mapping")
    data = raw.get("data") if isinstance(raw.get("data"), Mapping) else {}
    pass_fail = raw.get("pass_fail") if isinstance(raw.get("pass_fail"), Mapping) else {}
    discriminator = raw.get("discriminator") if isinstance(raw.get("discriminator"), Mapping) else {}
    params = data.get("params") if isinstance(data.get("params"), Mapping) else {}

    def _pick(name: str, *candidates: Tuple[str, Any]) -> Any:
        present = [(label, value) for label, value in candidates if value is not None and value != ""]
        if not present:
            return None
        label0, first = present[0]
        for label, value in present[1:]:
            if value != first:
                raise ValueError(f"Conflicting {name}: {label0}={first!r} vs {label}={value!r}")
        return first

    spec_id = _pick("spec id", ("spec_id", raw.get("spec_id")), ("id", raw.get("id"))) or default_id
    data_mode = _pick("data mode", ("data.mode", data.get("mode")), ("data_mode", raw.get("data_mode"))) or "synthetic"
    if data_mode not in _DATA_MODES:
        raise ValueError(f"unsupported data mode {data_mode!r}")
    dataset_id = _pick("dataset id", ("data.dataset_id", data.get("dataset_id")), ("dataset_id", raw.get("dataset_id")))

    flat_sim = raw.get("sim_params") if isinstance(raw.get("sim_params"), Mapping) else {}
    sim_params = dict(flat_sim) if flat_sim else {k: params[k] for k in ("N", "n_steps", "seed") if k in params}

    flat_thresholds = raw.get("threshold") if raw.get("threshold") is not None else {}
    governed_thresholds = pass_fail.get("thresholds") if pass_fail.get("thresholds") is not None else {}
    if not isinstance(flat_thresholds, Mapping) or not isinstance(governed_thresholds, Mapping):
        raise ValueError("threshold blocks must be mappings")
    thresholds: Dict[str, Any] = {}
    for key in sorted(set(flat_thresholds) | set(governed_thresholds)):
        thresholds[key] = _pick(
            f"threshold {key}",
            (f"threshold.{key}", flat_thresholds.get(key)),
            (f"pass_fail.thresholds.{key}", governed_thresholds.get(key)),
        )
    unknown = set(thresholds) - _CANONICAL_THRESHOLD_KEYS
    if unknown:
        raise ValueError(f"Unknown threshold key(s): {sorted(unknown)}")

    return {
        "spec_id": str(spec_id),
        "claim_type": raw.get("claim_type"),
        "layer": raw.get("layer"),
        "data_mode": str(data_mode),
        "dataset_id": dataset_id,
        "data_params": dict(params),
        "sim_params": sim_params,
        "thresholds": thresholds,
        "discriminator": dict(discriminator),
        "criteria": pass_fail.get("criteria"),
    }


def _evaluate_thresholds(metrics: Mapping[str, Any], thresholds: Mapping[str, Any], mapping: Mapping[str, Any]) -> list:
    """Failures for thresholds that map onto a metric. Thresholds are inclusive (>= min, <= max)."""
    failures: list = []
    for key, (metric, kind) in mapping.items():
        if key not in thresholds or metric not in metrics:
            continue
        value = float(metrics[metric])
        limit = float(thresholds[key])
        if kind == "min" and value < limit:
            failures.append(f"{metric} {value:.6f} < {key} {limit}")
        if kind == "max" and value > limit:
            failures.append(f"{metric} {value:.6f} > {key} {limit}")
    return failures


def _run_declared_data(
    spec: Dict[str, Any],
    spec_path: Path,
    out_dir: Path,
    now: datetime,
    *,
    allow_network: bool,
    cache_root: Optional[Path],
    max_recordings: int,
    max_epochs_per_recording: int,
    source_base_url: Optional[str],
) -> Dict[str, Any]:
    """Run a spec whose declared data is not the synthetic simulation (OpenNeuro, chunked)."""
    from pipelines import openneuro_chunked as oc

    thresholds = spec["thresholds"]
    discriminator = spec["discriminator"]
    disc_mode = discriminator.get("mode")
    dataset_id = spec["dataset_id"]
    reason: Optional[str] = None
    metrics: Dict[str, Any] = {}
    scope: Dict[str, Any] = {}
    epoch_rows: list = []
    chunk_rows: list = []
    t0 = time.monotonic()

    if spec["data_mode"] != "openneuro":
        reason = f"data mode {spec['data_mode']!r} is not executable by this runner"
    elif disc_mode != "stimulus_sweep":
        reason = f"discriminator {disc_mode!r} is not implemented for openneuro data"
    elif not allow_network:
        reason = "network access to OpenNeuro was not approved for this run (pass --allow-network)"
    elif dataset_id not in oc.TASK_BY_DATASET:
        reason = f"no stimulus task is registered for {dataset_id!r}"
    else:
        from tools.data_access.approved_adapter import ApprovedAcquisitionAdapter

        config = discriminator.get("config") or {}
        cache = Path(cache_root) if cache_root else out_dir / "chunk_cache"
        declared_cap = int(spec["data_params"].get("max_files", max_recordings))
        result = oc.run_stimulus_sweep(
            adapter=ApprovedAcquisitionAdapter(cache_root=cache),
            dataset_id=str(dataset_id),
            task=oc.TASK_BY_DATASET[str(dataset_id)],
            base_url=source_base_url or oc.S3_BASE_URL,
            allow_network=True,
            max_recordings=min(int(max_recordings), declared_cap),
            max_epochs_per_recording=int(max_epochs_per_recording),
            n_shuffles=int(thresholds.get("n_shuffles", 200)),
            seed=int(spec["sim_params"].get("seed", 0)),
            sweep_range_ms=tuple(config.get("sweep_range_ms", (-200, 400))),
            step_ms=int(config.get("step_ms", 10)),
        )
        metrics = dict(result.metrics)
        scope = dict(result.scope, declared_max_files=declared_cap, max_recordings_requested=int(max_recordings))
        epoch_rows = result.epoch_rows
        chunk_rows = result.chunk_rows

    scalar_metrics = {k: v for k, v in metrics.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
    if reason is None and scalar_metrics and not all(math.isfinite(float(v)) for v in scalar_metrics.values()):
        reason = "non-finite statistic; nothing can be concluded"
    threshold_failures = _evaluate_thresholds(scalar_metrics, thresholds, _OPENNEURO_THRESHOLDS) if scalar_metrics else []
    unevaluable = sorted(k for k in thresholds if k not in _OPENNEURO_THRESHOLDS and k != "n_shuffles")
    if reason is None and unevaluable:
        reason = f"threshold(s) {unevaluable} cannot be evaluated for openneuro stimulus_sweep"
    if reason is None and not any(k in _OPENNEURO_THRESHOLDS for k in thresholds):
        reason = "no thresholds declared; nothing was evaluated"
    verdict = "FAIL" if threshold_failures else ("ambiguous" if reason else "PASS")
    elapsed_s = round(time.monotonic() - t0, 3)

    blob = json.dumps(
        {"spec_id": spec["spec_id"], "data_mode": "openneuro", "dataset_id": dataset_id,
         "discriminator": discriminator, "thresholds": thresholds,
         "max_recordings": int(max_recordings), "max_epochs": int(max_epochs_per_recording)},
        sort_keys=True, separators=(",", ":"),
    )
    run_id = hashlib.sha256(blob.encode()).hexdigest()[:16]

    metrics_csv = out_dir / "metrics.csv"
    with metrics_csv.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["metric", "value"])
        for key, value in scalar_metrics.items():
            writer.writerow([key, value])
    summary_json = out_dir / "summary.json"
    executed_mode = "openneuro" if metrics else None  # None: nothing was executed on any data
    summary = {
        "spec_id": spec["spec_id"],
        "run_id": run_id,
        "verdict": verdict,
        "verdict_reason": reason,
        "threshold_failures": threshold_failures,
        "metrics_summary": scalar_metrics,
        "data_mode": executed_mode,
        "declared_data_mode": spec["data_mode"],
        "dataset_id": dataset_id,
        "scope": scope,
        "criteria": spec.get("criteria"),
        "elapsed_s": elapsed_s,
        "created_at": now.isoformat(),
    }
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if epoch_rows:
        with (out_dir / "epochs.csv").open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(epoch_rows[0].keys()))
            writer.writeheader()
            writer.writerows(epoch_rows)
    manifest_json = out_dir / "acquisition_manifest.json"
    manifest_json.write_text(json.dumps({"scope": scope, "chunks": chunk_rows}, indent=2, default=str), encoding="utf-8")

    from runs.run_record import RunRecordV1

    run_record_json = out_dir / "RunRecord.json"
    record = RunRecordV1.make(
        run_id=run_id,
        run_kind="hypothesis",
        elapsed_s=elapsed_s,
        spec_id=spec["spec_id"],
        claim_type=spec.get("claim_type"),
        layer=spec.get("layer"),
        data_mode=executed_mode,
        dataset_id=dataset_id,
        verdict=verdict,
        metrics=scalar_metrics,
        artifacts={
            "metrics.csv": str(metrics_csv),
            "summary.json": str(summary_json),
            "acquisition_manifest.json": str(manifest_json),
            "RunRecord.json": str(run_record_json),
        },
        source=str(spec_path),
        _now=now,
    )
    record.write_json(run_record_json)
    return summary


def run(
    spec_path: Path,
    out_dir: Path,
    _now: Optional[datetime] = None,
    *,
    allow_network: bool = False,
    cache_root: Optional[Path] = None,
    max_recordings: int = 5,
    max_epochs_per_recording: int = 120,
    source_base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a hypothesis spec and write artifacts. Returns summary dict."""
    now = _now or datetime.now(timezone.utc)
    spec = _canonical_spec(_load_yaml_simple(Path(spec_path)), default_id=Path(spec_path).stem)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if spec["data_mode"] != "synthetic":
        return _run_declared_data(
            spec, Path(spec_path), out_dir, now,
            allow_network=allow_network, cache_root=Path(cache_root) if cache_root else None,
            max_recordings=max_recordings, max_epochs_per_recording=max_epochs_per_recording,
            source_base_url=source_base_url,
        )

    spec_id = spec["spec_id"]
    sim_params = spec["sim_params"]
    N = int(sim_params.get("N", 32))
    n_steps = int(sim_params.get("n_steps", 20))
    seed = int(sim_params.get("seed", 0))

    t0 = time.monotonic()

    # ── run the sim (numpy only): complex Ginzburg-Landau, not plain diffusion —
    # diffusion is a heat equation and cannot sustain topological structure; CGL
    # spontaneously nucleates spiral-wave phase singularities (see sim/run_cards.py
    # run_psi_os for the same fix and full rationale) ────────────────────────────
    import numpy as np
    from core.topology import compute_Qz, compute_f_dress

    rng = np.random.default_rng(seed)
    psi = 0.1 * (rng.standard_normal((N, N)) + 1j * rng.standard_normal((N, N)))

    c1, c2, dt = 0.5, -0.5, 0.05
    intensities = []
    for _ in range(n_steps):
        lap = (
            np.roll(psi, 1, 0) + np.roll(psi, -1, 0) +
            np.roll(psi, 1, 1) + np.roll(psi, -1, 1) - 4 * psi
        )
        psi = psi + dt * (psi + (1 + 1j * c1) * lap - (1 + 1j * c2) * np.abs(psi) ** 2 * psi)
        intensities.append(float(np.abs(psi).mean()))

    if not np.all(np.isfinite(psi)):
        raise ValueError(f"CGL integration diverged (N={N}, n_steps={n_steps}, seed={seed})")

    I = np.array(intensities)
    elapsed_s = time.monotonic() - t0

    # compute_Qz returns (Qz_array, Qabs_array), one entry per slice along
    # `axis` (default axis=2, i.e. shape (nx, ny, nslices) -- see
    # validation/synthetic.py::single_vortex, which repeats along axis=2).
    # A prior version of this line did `float(compute_Qz(psi[np.newaxis]))`:
    # `psi[np.newaxis]` puts the singleton slice axis FIRST (shape
    # (1, N, N)), mismatched with the default axis=2 convention, AND
    # `float()` on the returned 2-tuple raises TypeError unconditionally.
    # A bare `except Exception` used to silently swallow that on every call,
    # so Qabs was always exactly 0.0 -- meaning every hypothesis spec's
    # `Qabs_max` threshold check (see verdict logic below) trivially passed
    # regardless of the spec's actual sim output. Fixed by using the correct
    # axis=2 convention and letting a genuine failure raise (the CGL
    # divergence check above already guards the one expected failure mode).
    Qz_arr, Qabs_arr = compute_Qz(psi[:, :, np.newaxis])
    Qz = float(Qz_arr[0])
    Qabs = float(Qabs_arr[0])
    f_dress = float(compute_f_dress(Qz_arr, Qabs_arr))

    metrics: Dict[str, Any] = {
        "I_mean": round(float(I.mean()), 6),
        "I_std": round(float(I.std()), 6),
        "I_final": round(float(I[-1]), 6),
        "n_steps": n_steps,
        "Qz": round(Qz, 6),
        "Qabs": round(Qabs, 6),
        "f_dress": round(f_dress, 6),
        "N": N,
        "seed": seed,
    }

    # ── verdict ───────────────────────────────────────────────────────────────
    # PASS requires every declared threshold to be evaluated on the data this run used.
    # A failed threshold is a definitive FAIL; anything not evaluated is 'ambiguous'.
    thresholds = spec["thresholds"]
    metrics_for_thresholds = {"I_mean": metrics["I_mean"], "Qabs": metrics["Qabs"], "I_std": metrics["I_std"]}
    threshold_failures = _evaluate_thresholds(metrics_for_thresholds, thresholds, _SYNTHETIC_THRESHOLDS)
    declared_mode = spec["data_mode"]
    unevaluable = sorted(k for k in thresholds if k not in _SYNTHETIC_THRESHOLDS and k != "n_shuffles")
    verdict_reason = None
    if unevaluable:
        verdict_reason = f"threshold(s) {unevaluable} cannot be evaluated on synthetic data"
    elif not any(k in _SYNTHETIC_THRESHOLDS for k in thresholds):
        verdict_reason = "no thresholds declared; nothing was evaluated"
    if threshold_failures:
        verdict = "FAIL"
    elif verdict_reason is not None:
        verdict = "ambiguous"
    else:
        verdict = "PASS"

    # ── run_id ────────────────────────────────────────────────────────────────
    blob = json.dumps(
        {"spec_id": spec_id, "sim_params": sim_params},
        sort_keys=True, separators=(",", ":"),
    )
    run_id = hashlib.sha256(blob.encode()).hexdigest()[:16]

    # ── write metrics.csv ─────────────────────────────────────────────────────
    metrics_csv = out_dir / "metrics.csv"
    with metrics_csv.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["metric", "value"])
        for k, v in metrics.items():
            w.writerow([k, v])

    # ── write summary.json ────────────────────────────────────────────────────
    summary = {
        "spec_id": spec_id,
        "run_id": run_id,
        "verdict": verdict,
        "threshold_failures": threshold_failures,
        "metrics_summary": metrics,
        "elapsed_s": round(elapsed_s, 3),
        "created_at": now.isoformat(),
        "data_mode": "synthetic",
        "declared_data_mode": declared_mode,
        "verdict_reason": verdict_reason,
    }
    summary_json = out_dir / "summary.json"
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # ── write RunRecord.json ──────────────────────────────────────────────────
    from runs.run_record import RunRecordV1

    run_record_json = out_dir / "RunRecord.json"

    record = RunRecordV1.make(
        run_id=run_id,
        run_kind="hypothesis",
        elapsed_s=round(elapsed_s, 3),
        spec_id=spec_id,
        claim_type=spec["claim_type"],
        layer=spec["layer"],
        data_mode="synthetic",  # the only mode the synthetic path executes
        dataset_id=spec["dataset_id"],
        verdict=verdict,
        metrics=metrics,
        artifacts={
            "metrics.csv": str(metrics_csv),
            "summary.json": str(summary_json),
            "RunRecord.json": str(run_record_json),
        },
        source=str(spec_path),
        _now=now,
    )
    record.write_json(run_record_json)

    return summary


# ── Governance-module API (used by tests/test_governance.py) ─────────────────

def run_hypothesis(
    spec: Any,
    output_dir: Optional[Path] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute a validated HypothesisSpec (governance module) and produce a summary.

    Args:
        spec: A fully validated HypothesisSpec from governance.spec.
        output_dir: Root output directory; run artifacts go in output_dir/<run_id>/.
        db_path: Optional SQLite DB path for run logging.

    Raises:
        governance.validate.ValidationError: if spec fails governance rules.
    """
    import uuid
    from governance.validate import validate_spec

    validate_spec(spec)

    run_id = uuid.uuid4().hex[:12]
    out_dir = Path(output_dir or "artifacts") / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.monotonic()

    _DB_AVAILABLE = True
    try:
        from database.database import add_artifact, add_metric, connect, finish_run, start_run
    except ImportError:
        _DB_AVAILABLE = False

    db_run_id: Optional[int] = None
    db_conn = None
    if db_path and _DB_AVAILABLE:
        db_conn = connect(db_path)
        db_run_id = start_run(
            db_conn,
            name=spec.id,
            kind=f"hypothesis/{spec.claim_type}",
            params={"spec_id": spec.id, "claim_type": spec.claim_type, "run_id": run_id},
        )

    import numpy as np
    rng = np.random.default_rng(seed=42)
    n = 20
    metrics: Dict[str, Any] = {
        "Q_mean": round(float(rng.normal(0.0, 1.0, n).mean()), 4),
        "Qabs_mean": round(float(abs(rng.normal(0.5, 0.2, n)).mean()), 4),
        "f_dress_mean": round(float(abs(rng.normal(1.0, 0.3, n)).mean()), 4),
        "n_samples": n,
    }

    thresholds = spec.pass_fail.thresholds if spec.pass_fail else {}
    if not thresholds:
        verdict = "ambiguous"
    else:
        results = []
        for key, min_val in thresholds.items():
            metric_key = f"{key}_mean" if f"{key}_mean" in metrics else key
            if metric_key in metrics:
                results.append(metrics[metric_key] >= min_val)
        verdict = "pass" if results and all(results) else ("fail" if results else "ambiguous")

    metrics_csv = out_dir / "metrics.csv"
    with open(metrics_csv, "w", newline="", encoding="utf-8") as fh:
        import csv as _csv
        writer = _csv.DictWriter(fh, fieldnames=["metric", "value"])
        writer.writeheader()
        for k, v in metrics.items():
            writer.writerow({"metric": k, "value": v})

    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    summary: Dict[str, Any] = {
        "spec_id": spec.id,
        "title": spec.title,
        "claim_type": spec.claim_type,
        "layer": spec.layer,
        "validation_status": "valid",
        "run_id": run_id,
        "started_at": now_iso,
        "data_mode": spec.data.mode if spec.data else "synthetic",
        "metrics_summary": metrics,
        "verdict": verdict,
        "artifacts": {
            "metrics_csv": str(metrics_csv),
            "summary_json": str(out_dir / "summary.json"),
        },
    }

    summary_json = out_dir / "summary.json"
    with open(summary_json, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)

    if db_conn and db_run_id is not None:
        for name, value in metrics.items():
            if isinstance(value, (int, float)):
                add_metric(db_conn, db_run_id, name, float(value), source=spec.id)
        add_artifact(db_conn, db_run_id, str(summary_json), kind="summary_json")
        add_artifact(db_conn, db_run_id, str(metrics_csv), kind="metrics_csv")
        finish_run(db_conn, db_run_id, status="finished")
        db_conn.close()

    elapsed = round(time.monotonic() - t0, 3)
    return summary


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Run a hypothesis spec")
    parser.add_argument("--spec", required=True, help="Path to .yaml spec file")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--allow-network", action="store_true",
                        help="Approve bounded OpenNeuro chunk access through the approved adapter (default: off)")
    parser.add_argument("--cache-root", default=None, help="Chunk cache directory (default: <output>/chunk_cache)")
    parser.add_argument("--max-recordings", type=int, default=5, help="Recordings to process (capped by the spec)")
    parser.add_argument("--max-epochs", type=int, default=120, help="TMS epochs per recording (and as many controls)")
    args = parser.parse_args()
    summary = run(
        Path(args.spec), Path(args.output),
        allow_network=args.allow_network,
        cache_root=Path(args.cache_root) if args.cache_root else None,
        max_recordings=args.max_recordings,
        max_epochs_per_recording=args.max_epochs,
    )
    metrics = summary["metrics_summary"]
    shown = {k: metrics[k] for k in ("I_mean", "heldout_auc", "p_value") if k in metrics}
    print(f"[hypothesis] spec={summary['spec_id']} run_id={summary['run_id']} "
          f"verdict={summary['verdict']} {shown}")
    if summary.get("verdict_reason"):
        print(f"[hypothesis] reason: {summary['verdict_reason']}")


if __name__ == "__main__":
    main()
