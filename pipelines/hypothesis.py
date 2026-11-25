"""Hypothesis pipeline — runs a sim spec, writes summary.json + RunRecord.json.

Usage:
  python -m pipelines.hypothesis --spec governance/specs/HYP-20260506-002.yaml \
                                  --output artifacts

Outputs (in --output dir):
  summary.json    — metrics + verdict (existing format)
  RunRecord.json  — v0.1 run artifact contract

Reliability contract (fail-closed):
  - Topology metrics come from a real CGL integration, never rng.normal fabrication.
  - Synthetic / scaffold / seed-imputed runs stamp evidence watermarks and set
    metrics_are_empirical=False and scientific_pass=False.
  - Threshold engineering verdicts ("PASS"/"pass") never imply scientific_pass.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


# ── Evidence watermarks ───────────────────────────────────────────────────────

_EVIDENCE_SYNTHETIC = "synthetic_hypothesis_demonstration"
_EVIDENCE_SCAFFOLD = "governance_hypothesis_scaffold"
_METRIC_KIND_CGL = "cgl_topology_metrics"
_METRIC_KIND_BLOCKED = "scaffold_metrics_unavailable"
_EMPIRICAL_DATA_MODES = frozenset(
    {"empirical", "openneuro", "external", "real", "descriptive_empirical"}
)
_MOCK_DATA_MODES = frozenset({"mock", "dry_run", "offline_fixture", "scaffold"})


def _normalize_data_mode(raw: Optional[str]) -> str:
    if raw is None or str(raw).strip() == "":
        return "synthetic"
    return str(raw).strip().lower()


def _watermarks_for(
    data_mode: str,
    *,
    seed_imputed: bool,
    metrics_finite: bool,
    metric_kind: str,
) -> Dict[str, Any]:
    """Fail-closed provenance stamps for hypothesis artifacts.

    This pipeline only integrates synthetic CGL fields. Declaring
    ``data_mode=openneuro`` / ``empirical`` without an empirical adapter still
    yields non-empirical metrics — never flip ``metrics_are_empirical`` or
    ``scientific_pass`` true from CGL-only output.
    """
    del metrics_finite  # reserved for future non-CGL adapters; CGL path already gates NaNs
    mode = _normalize_data_mode(data_mode)
    is_mock = mode in _MOCK_DATA_MODES
    is_empirical_claim = mode in _EMPIRICAL_DATA_MODES
    # CGL / blocked scaffold metrics are never empirical evidence.
    metrics_are_empirical = False
    scientific_pass = False
    if is_mock or metric_kind == _METRIC_KIND_BLOCKED or is_empirical_claim:
        # Empirical claim without empirical adapter → scaffold watermark.
        evidence_class = _EVIDENCE_SCAFFOLD
    else:
        evidence_class = _EVIDENCE_SYNTHETIC
    if is_mock:
        run_mode = "mock"
    elif is_empirical_claim:
        # Actual compute mode remains synthetic CGL despite the claimed data_mode.
        run_mode = "synthetic"
    else:
        run_mode = "synthetic"
    _ = seed_imputed  # surfaced on metrics; blocks any future empirical promotion
    return {
        "evidence_class": evidence_class,
        "run_mode": run_mode,
        "metrics_are_empirical": metrics_are_empirical,
        "scientific_pass": scientific_pass,
        "metric_kind": metric_kind,
    }


def _coerce_sim_params(raw: Optional[Dict[str, Any]]) -> Tuple[Dict[str, Any], bool, bool, bool]:
    """Return (sim_params, seed_imputed, n_imputed, steps_imputed)."""
    src = dict(raw or {})
    seed_imputed = "seed" not in src
    n_imputed = "N" not in src
    steps_imputed = "n_steps" not in src
    return (
        {
            "N": int(src.get("N", 32)),
            "n_steps": int(src.get("n_steps", 20)),
            "seed": int(src.get("seed", 0)),
        },
        seed_imputed,
        n_imputed,
        steps_imputed,
    )


def _run_cgl_topology(sim_params: Dict[str, Any]) -> Dict[str, Any]:
    """Integrate complex Ginzburg-Landau and compute real topology metrics.

    Raises ValueError on non-finite divergence. Never fabricates Q/Qabs/f_dress.
    """
    import numpy as np
    from core.topology import compute_Qz, compute_f_dress

    N = int(sim_params["N"])
    n_steps = int(sim_params["n_steps"])
    seed = int(sim_params["seed"])

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
    # compute_Qz returns (Qz_array, Qabs_array); use axis=2 convention.
    Qz_arr, Qabs_arr = compute_Qz(psi[:, :, np.newaxis])
    Qz = float(Qz_arr[0])
    Qabs = float(Qabs_arr[0])
    f_dress = float(compute_f_dress(Qz_arr, Qabs_arr))
    if not all(np.isfinite([Qz, Qabs, f_dress, float(I.mean())])):
        raise ValueError("Non-finite topology metrics after CGL integration")

    return {
        "I_mean": round(float(I.mean()), 6),
        "I_std": round(float(I.std()), 6),
        "I_final": round(float(I[-1]), 6),
        "n_steps": n_steps,
        "Qz": round(Qz, 6),
        "Qabs": round(Qabs, 6),
        "f_dress": round(f_dress, 6),
        # Governance threshold aliases (Q_mean / Qabs_mean / f_dress_mean).
        "Q_mean": round(Qz, 6),
        "Qabs_mean": round(Qabs, 6),
        "f_dress_mean": round(f_dress, 6),
        "n_samples": n_steps,
        "N": N,
        "seed": seed,
        "metric_kind": _METRIC_KIND_CGL,
    }


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

def run(spec_path: Path, out_dir: Path, _now: Optional[datetime] = None) -> Dict[str, Any]:
    """Execute a hypothesis spec and write artifacts. Returns summary dict."""
    now = _now or datetime.now(timezone.utc)
    spec = _load_yaml_simple(Path(spec_path))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    spec_id = spec.get("spec_id", Path(spec_path).stem)
    sim_params_raw = spec.get("sim_params", {})
    sim_params, seed_imputed, n_imputed, steps_imputed = _coerce_sim_params(sim_params_raw)
    data_mode = _normalize_data_mode(spec.get("data_mode"))

    t0 = time.monotonic()
    metrics = _run_cgl_topology(sim_params)
    elapsed_s = time.monotonic() - t0
    metrics["seed_imputed"] = seed_imputed
    metrics["N_imputed"] = n_imputed
    metrics["n_steps_imputed"] = steps_imputed

    # ── verdict ───────────────────────────────────────────────────────────────
    thresholds = spec.get("threshold", {})
    _KNOWN_THRESHOLD_KEYS = frozenset({"I_mean_min", "Qabs_max", "I_std_max"})
    unknown_keys = set(thresholds.keys()) - _KNOWN_THRESHOLD_KEYS
    if unknown_keys:
        raise ValueError(f"Unknown threshold key(s): {sorted(unknown_keys)}")

    threshold_failures: list = []
    if "I_mean_min" in thresholds and metrics["I_mean"] < float(thresholds["I_mean_min"]):
        threshold_failures.append(f"I_mean {metrics['I_mean']:.6f} < I_mean_min {thresholds['I_mean_min']}")
    if "Qabs_max" in thresholds and metrics["Qabs"] > float(thresholds["Qabs_max"]):
        threshold_failures.append(f"Qabs {metrics['Qabs']:.6f} > Qabs_max {thresholds['Qabs_max']}")
    if "I_std_max" in thresholds and metrics["I_std"] > float(thresholds["I_std_max"]):
        threshold_failures.append(f"I_std {metrics['I_std']:.6f} > I_std_max {thresholds['I_std_max']}")
    verdict = "PASS" if not threshold_failures else "FAIL"

    marks = _watermarks_for(
        data_mode,
        seed_imputed=seed_imputed,
        metrics_finite=True,
        metric_kind=_METRIC_KIND_CGL,
    )
    # Engineering PASS on imputed seed / synthetic must not flip scientific_pass.
    if marks["scientific_pass"] is False and verdict == "PASS":
        # Keep engineering verdict; scientific_pass stays false (already).
        pass

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
        "data_mode": data_mode,
        **marks,
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
        claim_type=spec.get("claim_type"),
        layer=spec.get("layer"),
        data_mode=data_mode,
        dataset_id=spec.get("dataset_id"),
        verdict=verdict,
        metrics=metrics,
        artifacts={
            "metrics.csv": str(metrics_csv),
            "summary.json": str(summary_json),
            "RunRecord.json": str(run_record_json),
        },
        source=str(spec_path),
        evidence_class=marks["evidence_class"],
        run_mode=marks["run_mode"],
        metrics_are_empirical=marks["metrics_are_empirical"],
        scientific_pass=marks["scientific_pass"],
        metric_kind=marks["metric_kind"],
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

    Never fabricates Q/Qabs/f_dress from rng.normal. Metrics come from CGL
    topology (or are blocked as unavailable). Threshold "pass" is engineering-
    only; scientific_pass stays false for synthetic/scaffold/seed-imputed runs.
    """
    from governance.validate import validate_spec

    validate_spec(spec)

    data_mode = _normalize_data_mode(spec.data.mode if spec.data else "synthetic")
    raw_params = dict(spec.data.params) if spec.data and spec.data.params else {}
    sim_params, seed_imputed, n_imputed, steps_imputed = _coerce_sim_params(raw_params)

    blob = json.dumps(
        {
            "spec_id": spec.id,
            "claim_type": spec.claim_type,
            "sim_params": sim_params,
            "data_mode": data_mode,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    run_id = hashlib.sha256(blob.encode()).hexdigest()[:16]
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

    metrics = _run_cgl_topology(sim_params)
    metrics["seed_imputed"] = seed_imputed
    metrics["N_imputed"] = n_imputed
    metrics["n_steps_imputed"] = steps_imputed

    marks = _watermarks_for(
        data_mode,
        seed_imputed=seed_imputed,
        metrics_finite=True,
        metric_kind=_METRIC_KIND_CGL,
    )

    thresholds = spec.pass_fail.thresholds if spec.pass_fail else {}
    if not thresholds:
        verdict = "ambiguous"
    else:
        results = []
        for key, min_val in thresholds.items():
            metric_key = f"{key}_mean" if f"{key}_mean" in metrics else key
            if metric_key in metrics:
                results.append(metrics[metric_key] >= min_val)
        engineering = "pass" if results and all(results) else ("fail" if results else "ambiguous")
        # Fail-closed: never emit engineering "pass" when metrics are not empirical
        # AND the caller asked for an empirical-sounding data mode without a real
        # empirical pipeline — synthetic pass is allowed as engineering-only.
        if engineering == "pass" and marks["metrics_are_empirical"] is False and data_mode in _EMPIRICAL_DATA_MODES:
            verdict = "blocked_non_empirical"
        else:
            verdict = engineering

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
        "data_mode": data_mode,
        "metrics_summary": metrics,
        "verdict": verdict,
        "artifacts": {
            "metrics_csv": str(metrics_csv),
            "summary_json": str(out_dir / "summary.json"),
            "RunRecord.json": str(out_dir / "RunRecord.json"),
        },
        **marks,
    }

    summary_json = out_dir / "summary.json"
    with open(summary_json, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)

    from runs.run_record import RunRecordV1

    run_record_json = out_dir / "RunRecord.json"
    record = RunRecordV1.make(
        run_id=run_id,
        run_kind="hypothesis",
        elapsed_s=round(time.monotonic() - t0, 3),
        spec_id=spec.id,
        claim_type=spec.claim_type,
        layer=spec.layer,
        data_mode=data_mode,
        dataset_id=(spec.data.dataset_id if spec.data else None) or None,
        verdict=verdict,
        metrics=metrics,
        artifacts={
            "metrics.csv": str(metrics_csv),
            "summary.json": str(summary_json),
            "RunRecord.json": str(run_record_json),
        },
        source=f"governance:{spec.id}",
        evidence_class=marks["evidence_class"],
        run_mode=marks["run_mode"],
        metrics_are_empirical=marks["metrics_are_empirical"],
        scientific_pass=marks["scientific_pass"],
        metric_kind=marks["metric_kind"],
    )
    record.write_json(run_record_json)

    if db_conn and db_run_id is not None:
        for name, value in metrics.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                add_metric(db_conn, db_run_id, name, float(value), source=spec.id)
        add_artifact(db_conn, db_run_id, str(summary_json), kind="summary_json")
        add_artifact(db_conn, db_run_id, str(metrics_csv), kind="metrics_csv")
        finish_run(db_conn, db_run_id, status="finished")
        db_conn.close()

    return summary


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Run a hypothesis spec")
    parser.add_argument("--spec", required=True, help="Path to .yaml spec file")
    parser.add_argument("--output", required=True, help="Output directory")
    args = parser.parse_args()
    summary = run(Path(args.spec), Path(args.output))
    print(f"[hypothesis] spec={summary['spec_id']} run_id={summary['run_id']} "
          f"verdict={summary['verdict']} I_mean={summary['metrics_summary']['I_mean']} "
          f"scientific_pass={summary.get('scientific_pass')} "
          f"metrics_are_empirical={summary.get('metrics_are_empirical')}")


if __name__ == "__main__":
    main()
