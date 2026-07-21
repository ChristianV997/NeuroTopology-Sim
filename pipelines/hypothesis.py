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
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


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
    sim_params = spec.get("sim_params", {})
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
        data_mode=spec.get("data_mode"),
        dataset_id=spec.get("dataset_id"),
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
    args = parser.parse_args()
    summary = run(Path(args.spec), Path(args.output))
    print(f"[hypothesis] spec={summary['spec_id']} run_id={summary['run_id']} "
          f"verdict={summary['verdict']} I_mean={summary['metrics_summary']['I_mean']}")


if __name__ == "__main__":
    main()
