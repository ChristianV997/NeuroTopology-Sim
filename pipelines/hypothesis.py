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

    # ── run the sim (numpy only) ──────────────────────────────────────────────
    import numpy as np

    rng = np.random.default_rng(seed)
    psi = rng.standard_normal((N, N)) + 1j * rng.standard_normal((N, N))
    psi /= np.abs(psi).mean() + 1e-9

    intensities = []
    for _ in range(n_steps):
        lap = (
            np.roll(psi, 1, 0) + np.roll(psi, -1, 0) +
            np.roll(psi, 1, 1) + np.roll(psi, -1, 1) - 4 * psi
        )
        psi = psi + 0.01 * lap
        intensities.append(float(np.abs(psi).mean()))

    I = np.array(intensities)
    elapsed_s = time.monotonic() - t0

    try:
        from core.topology import compute_Qz, compute_f_dress
        Qz = float(compute_Qz(psi[np.newaxis]))
        Qabs = float(abs(Qz))
        f_dress = float(compute_f_dress(Qz, Qabs))
    except Exception:
        Qz, Qabs, f_dress = 0.0, 0.0, 0.0

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
    I_mean_min = float(thresholds.get("I_mean_min", 0.0))
    Qabs_max = float(thresholds.get("Qabs_max", 1e9))
    verdict = "PASS" if (metrics["I_mean"] >= I_mean_min and metrics["Qabs"] <= Qabs_max) else "FAIL"

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
        "metrics_summary": metrics,
        "elapsed_s": round(elapsed_s, 3),
        "created_at": now.isoformat(),
    }
    summary_json = out_dir / "summary.json"
    summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # ── write RunRecord.json ──────────────────────────────────────────────────
    from runs.run_record import RunRecordV1

    rel = lambda p: str(Path(p).relative_to(Path.cwd())) if Path(p).is_absolute() else str(p)

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
        },
        source=str(spec_path),
        _now=now,
    )
    run_record_json = out_dir / "RunRecord.json"
    record.write_json(run_record_json)
    record.artifacts["RunRecord.json"] = str(run_record_json)

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
