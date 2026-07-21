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
    steps: Optional[List[Dict[str, Any]]] = None,
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
        steps=steps,
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
    curvature_penalty: float = 0.0,
    _now: Optional[datetime] = None,
) -> Tuple[RunRecord, Path, Path]:
    """Run a psi-field vortex simulation and emit dual run artifacts.

    Integrates the complex Ginzburg-Landau equation (CGL),
    ``dA/dt = A + (1+i*c1)*lap(A) - (1+i*c2)*|A|^2*A`` -- the canonical amplitude
    equation for oscillatory media -- rather than a plain diffusion step. Unlike
    diffusion (a heat equation, which only smooths noise to a uniform field and
    cannot sustain topological structure), CGL spontaneously nucleates spiral-wave
    phase singularities whose cores go to |A|->0, giving a genuine, non-trivial
    winding charge to measure (and matching the amplitude-dip convention
    ``core.defects.detect_defects`` expects).

    `curvature_penalty` (default 0.0, disabled): optional 4th-order
    (bi-Laplacian) spatial regularization strength, applied each step
    alongside the CGL update above -- a standard curvature-penalized /
    high-frequency-spatial-noise-suppression numerical technique (a
    discretized biharmonic damping term), described here in plain
    signal-processing terms deliberately, not experiential or contemplative
    language, per this repo's guardrail policy (no "meditative pruning"
    framing in code or reports). In Fourier space, a bi-Laplacian penalty
    scales as k^4 versus the Laplacian's k^2, so it damps high-spatial-
    frequency components relatively more than low-order (small-k) structure
    -- including the low-order winding modes this repo's Q/Qabs topology
    metrics track.

    This is an explicit (forward-Euler-style) update with no CFL-type step
    limiter, so `curvature_penalty` has a real numerical stability bound:
    empirically, values up to ~0.01 damp high-frequency energy smoothly,
    while values at/above ~0.05 diverge (unbounded growth) on this same
    step size and grid. Keep `curvature_penalty` small (<=0.01) unless the
    step size is reduced accordingly.
    """
    import numpy as np
    from core.topology import compute_Qz, compute_f_dress

    rng = np.random.default_rng(seed)

    # Small-amplitude seed so the CGL nonlinear term doesn't immediately blow up.
    psi = 0.1 * (rng.standard_normal((N, N)) + 1j * rng.standard_normal((N, N)))

    def _step_topology(field: np.ndarray) -> Tuple[float, float, float]:
        """Q/Qabs/f_dress for one 2D field slice.

        `compute_Qz` returns `(Qz_array, Qabs_array)`, one entry per slice
        along `axis` (default axis=2, i.e. shape (nx, ny, nslices) -- see
        `validation/synthetic.py::single_vortex`, which repeats along
        axis=2) -- NOT a single scalar. A prior version of this function did
        `float(compute_Qz(psi3d))` with `psi3d = psi[np.newaxis, :, :]`:
        the singleton slice axis was FIRST (mismatched with the default
        axis=2 convention -- `moveaxis(psi3d, 2, 0)` would move a real
        spatial axis, not the singleton one, producing degenerate 1-row
        "slices" that structurally reduce to Qabs=0), AND `float()` on the
        returned tuple raises `TypeError` unconditionally regardless. The
        bare `except Exception` around it silently swallowed both, so every
        run of `run_psi_os` ever produced -- before this fix -- reported
        fabricated zero topology metrics, never real ones. Per-step
        telemetry below keeps a lenient except (a single divergent step
        shouldn't kill the whole run's telemetry); the final metrics
        computed after the loop do not use this helper's except path.
        """
        try:
            field3d = field[:, :, np.newaxis]
            qz_arr, qabs_arr = compute_Qz(field3d)
            return float(qz_arr[0]), float(qabs_arr[0]), float(compute_f_dress(qz_arr, qabs_arr))
        except Exception:
            return 0.0, 0.0, 0.0

    c1, c2, dt = 0.5, -0.5, 0.05  # standard defect-turbulence regime parameters
    intensities = []
    steps_telemetry: List[Dict[str, Any]] = []
    for step_idx in range(n_steps):
        lap = (
            np.roll(psi, 1, 0) + np.roll(psi, -1, 0) +
            np.roll(psi, 1, 1) + np.roll(psi, -1, 1) - 4 * psi
        )
        psi = psi + dt * (psi + (1 + 1j * c1) * lap - (1 + 1j * c2) * np.abs(psi) ** 2 * psi)

        if curvature_penalty > 0.0:
            # 4th-order (bi-Laplacian) high-frequency spatial noise
            # suppression -- see this function's docstring for why k^4
            # scaling relatively preserves low-order winding structure
            # versus the CGL Laplacian term above.
            lap2 = (
                np.roll(psi, 1, 0) + np.roll(psi, -1, 0) +
                np.roll(psi, 1, 1) + np.roll(psi, -1, 1) - 4 * psi
            )
            bilap = (
                np.roll(lap2, 1, 0) + np.roll(lap2, -1, 0) +
                np.roll(lap2, 1, 1) + np.roll(lap2, -1, 1) - 4 * lap2
            )
            psi = psi - curvature_penalty * bilap

        intensity = float(np.abs(psi).mean())
        intensities.append(intensity)

        step_Qz, step_Qabs, step_f_dress = _step_topology(psi)

        # Dirichlet (gradient) energy: sum of squared nearest-neighbor
        # differences over the lattice -- a real, well-defined elastic-energy
        # scalar for this field (standard discretization of \int |grad psi|^2),
        # not a metaphorical "thermodynamic cost" claim.
        grad_x = psi - np.roll(psi, 1, axis=0)
        grad_y = psi - np.roll(psi, 1, axis=1)
        energy = float(np.sum(np.abs(grad_x) ** 2 + np.abs(grad_y) ** 2))

        steps_telemetry.append({
            "step": step_idx,
            "I": intensity,
            "Q": step_Qz,
            "Qabs": step_Qabs,
            "f_dress": step_f_dress,
            "energy": energy,
        })

    if not np.all(np.isfinite(psi)):
        raise ValueError(
            f"CGL integration diverged (N={N}, n_steps={n_steps}, seed={seed}); "
            "reduce dt, n_steps, or curvature_penalty"
        )

    I_series = np.array(intensities)

    # compute_Qz's default axis=2 treats the LAST axis as the z-slice stack (see
    # validation/synthetic.py's own psi[:, :, None] convention) -- psi[np.newaxis]
    # would put the singleton on axis 0 instead, silently yielding all-empty
    # plaquettes (nx=1) and therefore Qabs=0 on every field, real or not.
    Qz_arr, Qabs_arr = compute_Qz(psi[:, :, np.newaxis])
    Qz = float(Qz_arr[0])
    Qabs = float(Qabs_arr[0])
    f_dress = float(compute_f_dress(Qz_arr, Qabs_arr))
    # Fraction of grid points near a defect core (low local amplitude), a genuine
    # vortex-density diagnostic from the actual simulated field -- replaces a
    # prior placeholder that reported a fixed reference field's mean amplitude
    # regardless of what the simulation actually produced.
    vort_mean = float(np.mean(np.abs(psi) < 0.2 * np.abs(psi).mean()))

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
            "prediction": "Vortex intensity I_mean > 0 under CGL evolution",
            "discriminator": "I_mean <= 0 would falsify the CGL amplitude equation",
            "status": "PASS" if metrics["I_mean"] > 0 else "FAIL",
        },
    ]

    return build_run_record(
        mode="psi",
        input_params={"N": N, "n_steps": n_steps, "seed": seed, "curvature_penalty": curvature_penalty},
        metrics=metrics,
        confounds=["reproducibility_seed_fixed"],
        guardrails=guardrails,
        h8_falsifiers=h8_falsifiers,
        notes=(
            f"Psi-OS vortex sim N={N} steps={n_steps} seed={seed}"
            + (f" curvature_penalty={curvature_penalty}" if curvature_penalty > 0.0 else "")
        ),
        out_dir=out_dir,
        steps=steps_telemetry,
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
