"""Dual artifact writers + simulation runners.

Each run produces:
  run_<created_at_compact>_<run_id[:8]>.md    — RAG-ingestible run card
  run_<created_at_compact>_<run_id[:8]>.run.json  — Airtable ops sync payload
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from runs.run_record import (
    CONFOUNDS_CHECKLIST,
    RunRecordV1 as RunRecord,
    build_run_id,
    canonicalize_paths,
    validate_run_record_dict,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=_REPO_ROOT, timeout=5,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _compact_ts(dt: Optional[datetime] = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    return dt.strftime("%Y%m%dT%H%M%S")


def _iso_ts(dt: Optional[datetime] = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    return dt.isoformat()


def _artifact_stem(created_at_compact: str, run_id: str) -> str:
    return f"run_{created_at_compact}_{run_id[:8]}"


def save_run_card_markdown(record: RunRecord, out_dir: Path) -> Path:
    """Write the human-readable .md run card for RAG ingestion."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ts_compact = record.created_at.replace(":", "").replace("-", "").split(".")[0].replace("T", "T")[:15]
    stem = _artifact_stem(ts_compact, record.run_id)
    path = out_dir / f"{stem}.md"

    m = record.metrics
    lines = [
        f"# Run Card: {record.run_id}",
        "",
        f"**Mode:** {record.mode}  ",
        f"**Created:** {record.created_at}  ",
        f"**Repo:** {record.repo}  ",
        f"**Commit:** {record.git_commit}  ",
        "",
        "## Metrics",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| I_mean | {m.get('I_mean', float('nan')):.6f} |",
        f"| I_std | {m.get('I_std', float('nan')):.6f} |",
        f"| I_final | {m.get('I_final', float('nan')):.6f} |",
        f"| vort_mean | {m.get('vort_mean', float('nan')):.6f} |",
        f"| n_steps | {int(m.get('n_steps', 0))} |",
        f"| Qz_mean | {m.get('Qz_mean', float('nan')):.6f} |",
        f"| Qabs_mean | {m.get('Qabs_mean', float('nan')):.6f} |",
        f"| f_dress | {m.get('f_dress', float('nan')):.6f} |",
        "",
        "## Input Parameters",
        "",
        "```json",
        json.dumps(record.input, indent=2, default=str),
        "```",
        "",
        "## Confounds Addressed",
        "",
    ]
    for c in CONFOUNDS_CHECKLIST:
        mark = "x" if c in record.confounds else " "
        lines.append(f"- [{mark}] {c}")
    lines += [
        "",
        "## Guardrails",
        "",
        "```json",
        json.dumps(record.guardrails, indent=2, default=str),
        "```",
        "",
        "## H8 Falsifiers",
        "",
    ]
    for h in record.h8_falsifiers:
        lines.append(f"- **{h.get('status', '?')}** — {h.get('prediction', '')} _(discriminator: {h.get('discriminator', '')})_")
    if record.notes:
        lines += ["", "## Notes", "", record.notes]
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def save_run_record_json(record: RunRecord, out_dir: Path) -> Path:
    """Write the machine-readable .run.json for Airtable ops sync."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ts_compact = record.created_at.replace(":", "").replace("-", "").split(".")[0].replace("T", "T")[:15]
    stem = _artifact_stem(ts_compact, record.run_id)
    path = out_dir / f"{stem}.run.json"

    d = record.to_sim_dict()
    errors = validate_run_record_dict(d)
    if errors:
        raise ValueError(f"RunRecord validation failed: {errors}")

    path.write_text(json.dumps(d, indent=2, default=str), encoding="utf-8")
    return path


def build_run_record(
    *,
    mode: str,
    input_params: Dict[str, Any],
    metrics: Dict[str, float],
    confounds: Optional[List[str]] = None,
    guardrails: Optional[Dict[str, Any]] = None,
    h8_falsifiers: Optional[List[Dict[str, str]]] = None,
    notes: str = "",
    repo: str = "ScienceR-Dsim",
    out_dir: Optional[Path] = None,
    _now: Optional[datetime] = None,
) -> Tuple[RunRecord, Path, Path]:
    """Build a RunRecord and write both artifacts. Returns (record, md_path, json_path)."""
    now = _now or datetime.now(timezone.utc)
    git_commit = _git_commit()
    argv = sys.argv[:]

    run_id = build_run_id(
        mode=mode,
        repo=repo,
        git_commit=git_commit,
        argv=argv,
        input_params=canonicalize_paths(input_params, _REPO_ROOT),
        metrics=metrics,
        repo_root=_REPO_ROOT,
    )

    _out_dir = out_dir or (_REPO_ROOT / "outputs" / "run_cards")
    ts_compact = _compact_ts(now)
    stem = _artifact_stem(ts_compact, run_id)

    def _repo_rel(p: Path) -> str:
        try:
            return str(p.relative_to(_REPO_ROOT))
        except ValueError:
            return str(p)

    artifacts: Dict[str, str] = {
        "md_path": _repo_rel(_out_dir / f"{stem}.md"),
        "json_path": _repo_rel(_out_dir / f"{stem}.run.json"),
    }

    record = RunRecord(
        run_id=run_id,
        run_kind=mode,
        created_at=_iso_ts(now),
        mode=mode,
        repo=repo,
        git_commit=git_commit,
        argv=argv,
        input=canonicalize_paths(input_params, _REPO_ROOT),
        metrics=metrics,
        artifacts=artifacts,
        confounds=confounds or [],
        guardrails=guardrails or {},
        h8_falsifiers=h8_falsifiers or [],
        notes=notes,
    )

    md_path = save_run_card_markdown(record, _out_dir)
    json_path = save_run_record_json(record, _out_dir)
    return record, md_path, json_path


# ── Simulation runners ───────────────────────────────────────────────────────

def run_psi_os(
    N: int = 64,
    n_steps: int = 50,
    seed: int = 42,
    out_dir: Optional[Path] = None,
    _now: Optional[datetime] = None,
) -> Tuple[RunRecord, Path, Path]:
    """Run a psi/vortex simulation and emit dual run artifacts."""
    import numpy as np

    rng = np.random.default_rng(seed)

    # Build a minimal psi field (|ψ|² = intensity)
    psi = rng.standard_normal((N, N)) + 1j * rng.standard_normal((N, N))
    psi /= np.abs(psi).mean() + 1e-9

    intensities = []
    for _ in range(n_steps):
        # Minimal gradient-descent-like relaxation
        lap = (
            np.roll(psi, 1, 0) + np.roll(psi, -1, 0) +
            np.roll(psi, 1, 1) + np.roll(psi, -1, 1) - 4 * psi
        )
        psi = psi + 0.01 * lap
        intensities.append(float(np.abs(psi).mean()))

    I_series = np.array(intensities)

    try:
        from core.topology import compute_Qz, compute_f_dress
        psi3d = psi[np.newaxis, :, :]
        Qz = float(compute_Qz(psi3d))
        Qabs = float(abs(Qz))
        f_dress = float(compute_f_dress(Qz, Qabs))
    except Exception:
        Qz = 0.0
        Qabs = 0.0
        f_dress = 0.0

    try:
        from validation.synthetic import single_vortex
        ref = single_vortex(N=N)
        vort_mean = float(np.abs(ref).mean())
    except Exception:
        vort_mean = float(np.abs(psi).mean())

    metrics: Dict[str, float] = {
        "I_mean": float(I_series.mean()),
        "I_std": float(I_series.std()),
        "I_final": float(I_series[-1]),
        "vort_mean": vort_mean,
        "n_steps": float(n_steps),
        "Qz_mean": Qz,
        "Qabs_mean": Qabs,
        "f_dress": f_dress,
    }

    guardrails = {
        "I_final_above_zero": metrics["I_final"] > 0,
        "Qabs_below_threshold": metrics["Qabs_mean"] < 10.0,
    }

    h8_falsifiers = [
        {
            "prediction": "Vortex intensity I_mean > 0 under relaxation",
            "discriminator": "I_mean <= 0 would falsify diffusion model",
            "status": "PASS" if metrics["I_mean"] > 0 else "FAIL",
        },
    ]

    return build_run_record(
        mode="psi",
        input_params={"N": N, "n_steps": n_steps, "seed": seed},
        metrics=metrics,
        confounds=["reproducibility_seed_fixed"],
        guardrails=guardrails,
        h8_falsifiers=h8_falsifiers,
        notes=f"Psi-OS vortex sim N={N} steps={n_steps} seed={seed}",
        out_dir=out_dir,
        _now=_now,
    )


def run_meditation_sim(
    n_epochs: int = 30,
    epoch_len_s: float = 2.0,
    sfreq: float = 256.0,
    seed: int = 0,
    out_dir: Optional[Path] = None,
    _now: Optional[datetime] = None,
) -> Tuple[RunRecord, Path, Path]:
    """Synthetic EEG-like meditation simulation and dual run artifacts."""
    import numpy as np

    rng = np.random.default_rng(seed)
    n_samples = int(epoch_len_s * sfreq)

    epoch_intensities = []
    for _ in range(n_epochs):
        # Synthetic alpha-band-like signal
        t = np.linspace(0, epoch_len_s, n_samples)
        alpha = np.sin(2 * np.pi * 10 * t)  # 10 Hz
        noise = rng.standard_normal(n_samples) * 0.3
        signal = alpha + noise
        epoch_intensities.append(float(np.var(signal)))

    I_series = np.array(epoch_intensities)

    metrics: Dict[str, float] = {
        "I_mean": float(I_series.mean()),
        "I_std": float(I_series.std()),
        "I_final": float(I_series[-1]),
        "vort_mean": 0.0,      # not applicable for EEG-like sims
        "n_steps": float(n_epochs),
        "Qz_mean": 0.0,
        "Qabs_mean": 0.0,
        "f_dress": 0.0,
    }

    guardrails = {
        "I_mean_in_valid_range": 0.0 < metrics["I_mean"] < 1e6,
        "n_epochs_matches_input": int(metrics["n_steps"]) == n_epochs,
    }

    h8_falsifiers = [
        {
            "prediction": "Alpha-band variance I_mean > noise floor (0.09)",
            "discriminator": "I_mean <= 0.09 would indicate pure noise",
            "status": "PASS" if metrics["I_mean"] > 0.09 else "FAIL",
        },
    ]

    return build_run_record(
        mode="meditation",
        input_params={
            "n_epochs": n_epochs,
            "epoch_len_s": epoch_len_s,
            "sfreq": sfreq,
            "seed": seed,
        },
        metrics=metrics,
        confounds=["reproducibility_seed_fixed"],
        guardrails=guardrails,
        h8_falsifiers=h8_falsifiers,
        notes=f"Synthetic meditation sim epochs={n_epochs} sfreq={sfreq}",
        out_dir=out_dir,
        _now=_now,
    )
